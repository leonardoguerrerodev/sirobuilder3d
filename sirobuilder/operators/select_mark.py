import bpy

# colores de Siro3D: seleccionado #a84a42, resto #a0a6ae
COLOR_SEL = (0.659, 0.290, 0.259, 1.0)
COLOR_OTHER = (0.628, 0.651, 0.682, 1.0)

_active = False


def mark_active():
    return _active


def _tint(scene):
    selected = {o.name for o in bpy.context.selected_objects}
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.name.startswith("Siro"):
            continue
        color = COLOR_SEL if obj.name in selected else COLOR_OTHER
        if tuple(obj.color) != color:  # escribir solo si cambia, evita re-disparar el handler
            obj.color = color


def _on_depsgraph(scene, depsgraph):
    _tint(scene)


def disable(context=None):
    global _active
    if not _active:
        return
    _active = False
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            obj.color = (1.0, 1.0, 1.0, 1.0)
    if context is not None:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.color_type = 'MATERIAL'


class SIRO_OT_select_mark(bpy.types.Operator):
    """Marca en color la pieza seleccionada y agrisa el resto — útil con varias piezas en la escena"""
    bl_idname = "siro.select_mark"
    bl_label = "Marcar selección"

    def execute(self, context):
        global _active
        if _active:
            disable(context)
        else:
            _active = True
            bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.color_type = 'OBJECT'
            _tint(context.scene)
        return {'FINISHED'}
