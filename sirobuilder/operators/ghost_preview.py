"""Vista previa "fantasma" del corte, estilo Microsoft 3D Builder.

El lado que se conserva se ve con el material original de la pieza; el lado
que se descarta se ve como un fantasma blanco translúcido. Todo ocurre en un
modificador de Geometry Nodes: por cada cara calcula en qué lado del plano
cae (mismo cálculo que usa siro.cut al cortar de verdad) y le asigna el slot
de material correspondiente. El modificador NUNCA toca target.data — es 100%
no-destructivo y desaparece sin dejar rastro con remove_ghost_preview().

Fase 1 (v0.26.0): SIN drivers ni Python en el camino. El objeto del plano
(SiroCutter) entra al modificador como un input de tipo Objeto y el propio
node group lee su transform con Object Info. Antes, seis drivers llamaban a
una función propia registrada en `bpy.app.driver_namespace`, y eso dependía
de que *Auto Run Python Scripts* estuviera activo, de que un handler
`load_post` la repusiera al abrir archivos y de la ruta de propiedades de
cada versión de Blender. Ahora el fantasma funciona igual con la
auto-ejecución desactivada, con el addon deshabilitado y al abrir cualquier
.blend.

Qué calcula el node group, todo en espacio MUNDO (igual que cut.py):
    co_plano  = M_plano · (0,0,0)
    no_plano  = normalizar(M_plano · (0,0,1) − M_plano · (0,0,0))
    pos_cara  = M_pieza · centro_de_la_cara
    fantasma  = dot(pos_cara − co_plano, no_plano) < 0
"""

import bpy

NODEGROUP_NAME = "SiroGhostPreview"
MODIFIER_NAME = "SiroGhostPreview"
GHOST_MAT_NAME = "SiroGhostFantasma"
CUTTER_NAME = "SiroCutter"

_ADDED_BASE_SLOT_KEY = "siro_ghost_added_base_slot"

# Alfa del fantasma en Solid y en Material Preview. Subido de 0.12 a 0.25: a
# 0.12 sobre un fondo claro casi no se distinguía del fondo (hipótesis 4 del
# plan). Solo aplica a materiales NUEVOS; si ya existe SiroGhostFantasma en el
# archivo, se respeta el valor que tenga.
GHOST_ALPHA = 0.25


def ghost_target():
    """La pieza que tiene el preview puesto. Solo hay una: add_cut_plane llama
    a remove_all_ghost_previews antes de poner el modificador."""
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and MODIFIER_NAME in obj.modifiers:
            return obj
    return None


def _ghost_material():
    """Blanco translúcido — el "fantasma" del lado que se descarta"""
    mat = bpy.data.materials.get(GHOST_MAT_NAME)
    if mat is None:
        mat = bpy.data.materials.new(GHOST_MAT_NAME)
        mat.diffuse_color = (1.0, 1.0, 1.0, GHOST_ALPHA)  # color en Solid
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            bsdf.inputs["Alpha"].default_value = GHOST_ALPHA
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


# Entradas del modificador de nodos. Blender 5.2 las movió de mod["Socket_N"]
# (propiedad propia del modificador, que ya no acepta) a
# mod.properties.inputs.Socket_N.value. Hasta 5.1, la forma vieja.
def _set_input(mod, socket_id, value):
    if hasattr(mod, "properties"):
        getattr(mod.properties.inputs, socket_id).value = value
    else:
        mod[socket_id] = value


def _build_node_group():
    """Geometry: por cara, dot(pos_mundo − co_plano, no_plano) < 0 → slot fantasma"""
    group = bpy.data.node_groups.get(NODEGROUP_NAME)
    if group is not None:
        # versión actual = tiene el input "Cutter" (objeto). Las anteriores
        # recibían Plane Co / Plane No por drivers: se reconstruye.
        try:
            _socket_identifier(group, "Cutter")
            return group
        except KeyError:
            bpy.data.node_groups.remove(group)

    group = bpy.data.node_groups.new(NODEGROUP_NAME, 'GeometryNodeTree')
    iface = group.interface
    iface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    iface.new_socket(name="Cutter", in_out='INPUT', socket_type='NodeSocketObject')
    iface.new_socket(name="Ghost Slot", in_out='INPUT', socket_type='NodeSocketInt')
    iface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    nodes = group.nodes
    links = group.links

    n_in = nodes.new('NodeGroupInput')
    n_in.location = (-1100, 0)
    n_out = nodes.new('NodeGroupOutput')
    n_out.location = (500, 0)

    # --- transform del PLANO (el objeto que llega por el input "Cutter") ---
    n_cut_info = nodes.new('GeometryNodeObjectInfo')
    n_cut_info.location = (-900, 400)
    n_cut_info.transform_space = 'ORIGINAL'  # matrix_world del objeto
    links.new(n_in.outputs['Cutter'], n_cut_info.inputs['Object'])

    # punto del plano: M · (0,0,0)
    n_co = nodes.new('FunctionNodeTransformPoint')
    n_co.location = (-640, 480)
    n_co.inputs['Vector'].default_value = (0.0, 0.0, 0.0)
    links.new(n_cut_info.outputs['Transform'], n_co.inputs['Transform'])

    # normal del plano: M · (0,0,1) − M · (0,0,0), normalizada. Es lo mismo que
    # `matrix_world.to_3x3() @ (0,0,1)` normalizado de siro.cut.
    n_tip = nodes.new('FunctionNodeTransformPoint')
    n_tip.location = (-640, 300)
    n_tip.inputs['Vector'].default_value = (0.0, 0.0, 1.0)
    links.new(n_cut_info.outputs['Transform'], n_tip.inputs['Transform'])

    n_dir = nodes.new('ShaderNodeVectorMath')
    n_dir.operation = 'SUBTRACT'
    n_dir.location = (-420, 400)
    links.new(n_tip.outputs['Vector'], n_dir.inputs[0])
    links.new(n_co.outputs['Vector'], n_dir.inputs[1])

    n_no = nodes.new('ShaderNodeVectorMath')
    n_no.operation = 'NORMALIZE'
    n_no.location = (-220, 400)
    links.new(n_dir.outputs['Vector'], n_no.inputs[0])

    # --- posición de cada cara en espacio MUNDO (transform de la pieza) ---
    n_pos = nodes.new('GeometryNodeInputPosition')
    n_pos.location = (-900, -140)
    n_self = nodes.new('GeometryNodeSelfObject')
    n_self.location = (-900, -300)
    n_self_info = nodes.new('GeometryNodeObjectInfo')
    n_self_info.location = (-720, -300)
    n_self_info.transform_space = 'ORIGINAL'
    links.new(n_self.outputs['Self Object'], n_self_info.inputs['Object'])

    n_world = nodes.new('FunctionNodeTransformPoint')
    n_world.location = (-500, -180)
    links.new(n_pos.outputs['Position'], n_world.inputs['Vector'])
    links.new(n_self_info.outputs['Transform'], n_world.inputs['Transform'])

    # --- dot(pos − co, no) < 0 ---
    n_sub = nodes.new('ShaderNodeVectorMath')
    n_sub.operation = 'SUBTRACT'
    n_sub.location = (-260, -100)
    links.new(n_world.outputs['Vector'], n_sub.inputs[0])
    links.new(n_co.outputs['Vector'], n_sub.inputs[1])

    n_dot = nodes.new('ShaderNodeVectorMath')
    n_dot.operation = 'DOT_PRODUCT'
    n_dot.location = (-60, -100)
    links.new(n_sub.outputs['Vector'], n_dot.inputs[0])
    links.new(n_no.outputs['Vector'], n_dot.inputs[1])

    n_lt = nodes.new('ShaderNodeMath')
    n_lt.operation = 'LESS_THAN'
    n_lt.location = (140, -100)
    n_lt.inputs[1].default_value = 0.0
    links.new(n_dot.outputs['Value'], n_lt.inputs[0])

    n_setmat = nodes.new('GeometryNodeSetMaterialIndex')
    n_setmat.location = (320, 60)
    links.new(n_in.outputs['Geometry'], n_setmat.inputs['Geometry'])
    links.new(n_lt.outputs['Value'], n_setmat.inputs['Selection'])
    links.new(n_in.outputs['Ghost Slot'], n_setmat.inputs['Material Index'])
    links.new(n_setmat.outputs['Geometry'], n_out.inputs['Geometry'])

    return group


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

    _set_input(mod, _socket_identifier(group, "Cutter"), cutter)
    _set_input(mod, _socket_identifier(group, "Ghost Slot"), ghost_index)


def _quitar_drivers_viejos(obj):
    """Archivos guardados con versiones <= 0.25.1 traen seis drivers sobre las
    entradas del modificador fantasma. Se borran por ruta, sin depender de que
    el node group viejo siga existiendo."""
    ad = obj.animation_data
    if ad is None:
        return
    for fc in list(ad.drivers):
        if MODIFIER_NAME in fc.data_path:
            ad.drivers.remove(fc)


def remove_ghost_preview(obj):
    """Quita el modificador fantasma y el/los slot(s) de material que se
    agregaron solo para esto; deja la pieza exactamente como estaba."""
    mod = obj.modifiers.get(MODIFIER_NAME)
    added_base_slot = False
    if mod is not None:
        added_base_slot = bool(obj.get(_ADDED_BASE_SLOT_KEY, False))
        obj.modifiers.remove(mod)
    _quitar_drivers_viejos(obj)
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
