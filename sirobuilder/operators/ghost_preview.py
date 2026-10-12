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
from bpy.app.handlers import persistent
from mathutils import Vector

NODEGROUP_NAME = "SiroGhostPreview"
MODIFIER_NAME = "SiroGhostPreview"
GHOST_MAT_NAME = "SiroGhostFantasma"
CUTTER_NAME = "SiroCutter"

_DRIVER_NS_KEY = "siro_ghost_plane_component"
_ADDED_BASE_SLOT_KEY = "siro_ghost_added_base_slot"


def ghost_target():
    """La pieza que tiene el preview puesto. Solo hay una: add_cut_plane llama
    a remove_all_ghost_previews antes de poner el modificador."""
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and MODIFIER_NAME in obj.modifiers:
            return obj
    return None


def _plane_component(kind, axis):
    """Componente (0/1/2) de la co. o normal del plano de corte, en espacio
    MUNDO. La llaman los drivers; con clear_inner=True en _cut_mesh,
    dot(pos - co, normal) < 0 es el lado que se descarta.

    Depende SOLO del plano, nunca de la pieza: un driver que lee la transform
    del objeto que lo lleva no se re-evalúa a tiempo (el depsgraph no puede
    ordenarlo contra sí mismo) y el preview quedaba retrasado o congelado. La
    transform de la pieza la aplica el propio node group con Self Object.

    Tampoco recibe nombres: guardarlos como texto en la expresión mataba el
    preview en silencio en cuanto la pieza se renombraba (o Blender le
    agregaba un .001)."""
    cutter = bpy.data.objects.get(CUTTER_NAME)
    if cutter is None:
        return 0.0
    if kind == 'CO':
        return cutter.matrix_world.translation[axis]
    return (cutter.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()[axis]


@persistent
def _reponer_driver(_archivo):
    """Blender VACÍA `driver_namespace` cada vez que carga un .blend.

    Inyectarla solo en register() no alcanza: register() corre una vez al
    arrancar, y en cuanto se abre un archivo la función desaparece aunque el
    addon siga perfectamente habilitado. Los seis drivers del fantasma quedan
    `is_valid: False`, los sockets del modificador se quedan en cero, y con la
    normal del plano en (0,0,0) el producto punto da 0 — que no es `< 0`, así
    que ninguna cara se marca y el fantasma no aparece. Medido en la sesión de
    Leo con una pieza real: 0 caras fantasma de 250 185.

    Tiene que ser `@persistent`, o el propio handler se borraría en la primera
    carga y solo arreglaría el primer archivo.
    """
    bpy.app.driver_namespace[_DRIVER_NS_KEY] = _plane_component


def register_driver_function():
    bpy.app.driver_namespace[_DRIVER_NS_KEY] = _plane_component
    if _reponer_driver not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_reponer_driver)


def unregister_driver_function():
    bpy.app.driver_namespace.pop(_DRIVER_NS_KEY, None)
    if _reponer_driver in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reponer_driver)


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


# Entradas del modificador de nodos. Blender 5.2 las movió de mod["Socket_N"] (propiedad
# propia del modificador, que ya no acepta) a mod.properties.inputs.Socket_N.value; los
# drivers se cuelgan del objeto con esa ruta. Hasta 5.1, la forma vieja.
def _input_path(mod, socket_id):
    if hasattr(mod, "properties"):
        return f'modifiers["{mod.name}"].properties.inputs.{socket_id}.value'
    return f'modifiers["{mod.name}"]["{socket_id}"]'


def _set_input(mod, socket_id, value):
    if hasattr(mod, "properties"):
        getattr(mod.properties.inputs, socket_id).value = value
    else:
        mod[socket_id] = value


def _build_node_group():
    """Geometry: por cara, dot(pos_mundo - Plane Co, Plane No) < 0 → slot fantasma"""
    group = bpy.data.node_groups.get(NODEGROUP_NAME)
    if group is not None:
        if any(n.bl_idname == 'GeometryNodeSelfObject' for n in group.nodes):
            return group
        # versión vieja (comparaba en espacio local): se reconstruye
        bpy.data.node_groups.remove(group)

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
    n_pos.location = (-680, -260)

    # posición a espacio mundo dentro del propio node group: así el plano llega
    # en coordenadas de mundo y los drivers no necesitan saber nada de la pieza
    n_self = nodes.new('GeometryNodeSelfObject')
    n_self.location = (-680, -420)
    n_info = nodes.new('GeometryNodeObjectInfo')
    n_info.location = (-500, -420)
    links.new(n_self.outputs['Self Object'], n_info.inputs['Object'])

    n_world = nodes.new('FunctionNodeTransformPoint')
    n_world.location = (-300, -300)
    links.new(n_pos.outputs['Position'], n_world.inputs['Vector'])
    links.new(n_info.outputs['Transform'], n_world.inputs['Transform'])

    n_sub = nodes.new('ShaderNodeVectorMath')
    n_sub.operation = 'SUBTRACT'
    n_sub.location = (-120, -120)
    links.new(n_world.outputs['Vector'], n_sub.inputs[0])
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
    # sin los canales SCALE_*, escalar el plano dejaba el preview congelado
    canales = ('LOC_X', 'LOC_Y', 'LOC_Z', 'ROT_X', 'ROT_Y', 'ROT_Z',
               'SCALE_X', 'SCALE_Y', 'SCALE_Z')
    for i, chan in enumerate(canales):
        var = driver.variables.new()
        var.name = f"{prefix}{i}"
        var.type = 'TRANSFORMS'
        tgt = var.targets[0]
        tgt.id = obj
        tgt.transform_type = chan
        tgt.transform_space = 'WORLD_SPACE'


def _make_driver(mod, socket_id, axis, cutter, kind):
    fcurve = mod.id_data.driver_add(_input_path(mod, socket_id), axis)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    drv.expression = f"{_DRIVER_NS_KEY}('{kind}', {axis})"
    # solo el plano: depender también de la pieza es lo que rompía el preview
    # (el driver vive en un modificador de la pieza, no puede depender de ella)
    _add_transform_dep(drv, cutter, "c")


def add_ghost_modifier(target, cutter):
    """Crea (o recrea) el modificador fantasma en `target`, en vivo según la
    transform de `cutter`. No toca target.data en ningún momento."""
    remove_ghost_preview(target)

    # sin esto, el shading Solid (el modo normal de trabajo) ignora el alfa
    # del material fantasma y lo pinta opaco — el "fantasma" no se ve
    target.show_transparent = True

    added_base_slot = len(target.data.materials) == 0
    if added_base_slot:
        target.data.materials.append(None)  # slot vacío = gris por defecto de Blender
    target.data.materials.append(_ghost_material())
    ghost_index = len(target.data.materials) - 1

    group = _build_node_group()
    mod = target.modifiers.new(MODIFIER_NAME, 'NODES')
    mod.node_group = group
    # en el objeto, no en el modificador: Blender 5.2 ya no acepta propiedades
    # propias en modificadores (TypeError: id properties not supported)
    target[_ADDED_BASE_SLOT_KEY] = added_base_slot

    co_id = _socket_identifier(group, "Plane Co")
    no_id = _socket_identifier(group, "Plane No")
    slot_id = _socket_identifier(group, "Ghost Slot")

    _set_input(mod, co_id, (0.0, 0.0, 0.0))
    _set_input(mod, no_id, (0.0, 0.0, 1.0))
    _set_input(mod, slot_id, ghost_index)

    for axis in range(3):
        _make_driver(mod, co_id, axis, cutter, 'CO')
        _make_driver(mod, no_id, axis, cutter, 'NO')


def remove_ghost_preview(obj):
    """Quita el modificador fantasma y el/los slot(s) de material que se
    agregaron solo para esto; deja la pieza exactamente como estaba."""
    mod = obj.modifiers.get(MODIFIER_NAME)
    added_base_slot = False
    if mod is not None:
        added_base_slot = bool(obj.get(_ADDED_BASE_SLOT_KEY, False))
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
                    obj.driver_remove(_input_path(mod, co_id), axis)
                    obj.driver_remove(_input_path(mod, no_id), axis)
            except KeyError:
                pass
        obj.modifiers.remove(mod)
    if _ADDED_BASE_SLOT_KEY in obj:
        del obj[_ADDED_BASE_SLOT_KEY]

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
