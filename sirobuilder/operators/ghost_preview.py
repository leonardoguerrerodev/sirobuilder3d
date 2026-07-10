"""Vista previa "fantasma" del corte, estilo Microsoft 3D Builder.

El lado que se conserva se ve con el material original de la pieza; el lado
que se descarta se ve como un fantasma blanco translúcido. Todo ocurre en la
GPU vía un modificador de Geometry Nodes: por cada cara calcula en qué lado
del plano cae (mismo cálculo que usa siro.cut al cortar de verdad, en espacio
local de la pieza) y le asigna el slot de material correspondiente. El
modificador NUNCA toca target.data — es 100% no-destructivo y desaparece sin
dejar rastro con remove_ghost_preview().

La transform del plano llega al modificador vía drivers (no un handler de
Python corriendo cada frame): los drivers solo se re-evalúan cuando el plano o
la pieza se mueven/rotan, y la función que llaman recalcula la co/normal del
plano en espacio local de la pieza igual que _cut_mesh en cut.py.

Nota: los drivers dependen de que el addon esté registrado (register()
inyecta la función en bpy.app.driver_namespace). Si se abre un .blend con el
addon deshabilitado, el modificador queda ahí pero sin efecto hasta reactivarlo.
"""

import bpy
from mathutils import Vector

NODEGROUP_NAME = "SiroGhostPreview"
MODIFIER_NAME = "SiroGhostPreview"
GHOST_MAT_NAME = "SiroGhostFantasma"

_DRIVER_NS_KEY = "siro_ghost_plane_component"
_ADDED_BASE_SLOT_KEY = "siro_ghost_added_base_slot"


def _plane_component(target_name, cutter_name, kind, axis):
    """Componente (0/1/2) de la co. o normal del plano de corte, en espacio
    LOCAL de la pieza objetivo. La llaman los drivers; con clear_inner=True en
    _cut_mesh, dot(pos_local - co, normal) < 0 es el lado que se descarta."""
    target = bpy.data.objects.get(target_name)
    cutter = bpy.data.objects.get(cutter_name)
    if target is None or cutter is None:
        return 0.0
    no_world = (cutter.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    co_local = target.matrix_world.inverted() @ cutter.matrix_world.translation
    no_local = (target.matrix_world.to_3x3().transposed() @ no_world).normalized()
    return (co_local if kind == 'CO' else no_local)[axis]


def register_driver_function():
    bpy.app.driver_namespace[_DRIVER_NS_KEY] = _plane_component


def unregister_driver_function():
    bpy.app.driver_namespace.pop(_DRIVER_NS_KEY, None)


def _ghost_material():
    """Blanco translúcido — el "fantasma" del lado que se descarta"""
    mat = bpy.data.materials.get(GHOST_MAT_NAME)
    if mat is None:
        mat = bpy.data.materials.new(GHOST_MAT_NAME)
        mat.diffuse_color = (1.0, 1.0, 1.0, 0.12)
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            bsdf.inputs["Alpha"].default_value = 0.12
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.6
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = 'BLENDED'
    return mat


def _socket_identifier(group, name, in_out='INPUT'):
    for item in group.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == in_out and item.name == name:
            return item.identifier
    raise KeyError(f"Socket '{name}' no encontrado en {group.name}")


def _build_node_group():
    """Geometry: por cara, dot(Position - Plane Co, Plane No) < 0 → slot fantasma"""
    group = bpy.data.node_groups.get(NODEGROUP_NAME)
    if group is not None:
        return group

    group = bpy.data.node_groups.new(NODEGROUP_NAME, 'GeometryNodeTree')
    iface = group.interface
    iface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    iface.new_socket(name="Plane Co", in_out='INPUT', socket_type='NodeSocketVector')
    iface.new_socket(name="Plane No", in_out='INPUT', socket_type='NodeSocketVector')
    iface.new_socket(name="Ghost Slot", in_out='INPUT', socket_type='NodeSocketInt')
    iface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    nodes = group.nodes
    links = group.links

    n_in = nodes.new('NodeGroupInput')
    n_in.location = (-680, 0)
    n_out = nodes.new('NodeGroupOutput')
    n_out.location = (300, 0)

    n_pos = nodes.new('GeometryNodeInputPosition')
    n_pos.location = (-460, -160)

    n_sub = nodes.new('ShaderNodeVectorMath')
    n_sub.operation = 'SUBTRACT'
    n_sub.location = (-260, -120)
    links.new(n_pos.outputs['Position'], n_sub.inputs[0])
    links.new(n_in.outputs['Plane Co'], n_sub.inputs[1])

    n_dot = nodes.new('ShaderNodeVectorMath')
    n_dot.operation = 'DOT_PRODUCT'
    n_dot.location = (-60, -120)
    links.new(n_sub.outputs['Vector'], n_dot.inputs[0])
    links.new(n_in.outputs['Plane No'], n_dot.inputs[1])

    n_lt = nodes.new('ShaderNodeMath')
    n_lt.operation = 'LESS_THAN'
    n_lt.location = (120, -120)
    n_lt.inputs[1].default_value = 0.0
    links.new(n_dot.outputs['Value'], n_lt.inputs[0])

    n_setmat = nodes.new('GeometryNodeSetMaterialIndex')
    n_setmat.location = (120, 60)
    links.new(n_in.outputs['Geometry'], n_setmat.inputs['Geometry'])
    links.new(n_lt.outputs['Value'], n_setmat.inputs['Selection'])
    links.new(n_in.outputs['Ghost Slot'], n_setmat.inputs['Material Index'])
    links.new(n_setmat.outputs['Geometry'], n_out.inputs['Geometry'])

    return group


def _add_transform_dep(driver, obj, prefix):
    """Variables 'mudas' solo para marcar dependencia: el driver se re-evalúa
    cuando cambian estos canales, aunque la expresión no las nombre — llama
    directo a la función registrada, que relee matrix_world por su cuenta."""
    for i, chan in enumerate(('LOC_X', 'LOC_Y', 'LOC_Z', 'ROT_X', 'ROT_Y', 'ROT_Z')):
        var = driver.variables.new()
        var.name = f"{prefix}{i}"
        var.type = 'TRANSFORMS'
        tgt = var.targets[0]
        tgt.id = obj
        tgt.transform_type = chan
        tgt.transform_space = 'WORLD_SPACE'


def _make_driver(mod, socket_id, axis, target, cutter, kind):
    fcurve = mod.driver_add(f'["{socket_id}"]', axis)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    drv.expression = f"{_DRIVER_NS_KEY}('{target.name}', '{cutter.name}', '{kind}', {axis})"
    _add_transform_dep(drv, cutter, "c")
    _add_transform_dep(drv, target, "t")


def add_ghost_modifier(target, cutter):
    """Crea (o recrea) el modificador fantasma en `target`, en vivo según la
    transform de `cutter`. No toca target.data en ningún momento."""
    remove_ghost_preview(target)

    added_base_slot = len(target.data.materials) == 0
    if added_base_slot:
        target.data.materials.append(None)  # slot vacío = gris por defecto de Blender
    target.data.materials.append(_ghost_material())
    ghost_index = len(target.data.materials) - 1

    group = _build_node_group()
    mod = target.modifiers.new(MODIFIER_NAME, 'NODES')
    mod.node_group = group
    mod[_ADDED_BASE_SLOT_KEY] = added_base_slot

    co_id = _socket_identifier(group, "Plane Co")
    no_id = _socket_identifier(group, "Plane No")
    slot_id = _socket_identifier(group, "Ghost Slot")

    mod[co_id] = (0.0, 0.0, 0.0)
    mod[no_id] = (0.0, 0.0, 1.0)
    mod[slot_id] = ghost_index

    for axis in range(3):
        _make_driver(mod, co_id, axis, target, cutter, 'CO')
        _make_driver(mod, no_id, axis, target, cutter, 'NO')


def remove_ghost_preview(obj):
    """Quita el modificador fantasma y el/los slot(s) de material que se
    agregaron solo para esto; deja la pieza exactamente como estaba."""
    mod = obj.modifiers.get(MODIFIER_NAME)
    added_base_slot = False
    if mod is not None:
        added_base_slot = bool(mod.get(_ADDED_BASE_SLOT_KEY, False))
        group = mod.node_group
        if group is not None:
            # quitar los drivers antes de borrar el modificador: driver_add()
            # los guarda en el animation_data del objeto, no "dentro" del
            # modificador, así que si no los sacamos primero quedan huérfanos
            # apuntando a una ruta que ya no existe
            try:
                co_id = _socket_identifier(group, "Plane Co")
                no_id = _socket_identifier(group, "Plane No")
                for axis in range(3):
                    mod.driver_remove(f'["{co_id}"]', axis)
                    mod.driver_remove(f'["{no_id}"]', axis)
            except KeyError:
                pass
        obj.modifiers.remove(mod)

    mats = obj.data.materials
    ghost = bpy.data.materials.get(GHOST_MAT_NAME)
    if ghost is not None and len(mats) and mats[-1] == ghost:
        mats.pop(index=len(mats) - 1)
        if added_base_slot and len(mats) and mats[-1] is None:
            mats.pop(index=len(mats) - 1)


def remove_all_ghost_previews(context):
    for obj in context.scene.objects:
        if obj.type == 'MESH':
            remove_ghost_preview(obj)
