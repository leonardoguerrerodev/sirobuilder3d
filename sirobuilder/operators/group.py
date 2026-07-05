import bpy
from bpy.app.handlers import persistent

GROUP_KEY = "siro_group"


@persistent
def _sync_selection(scene, depsgraph=None):
    """Si se selecciona una pieza agrupada, selecciona el resto de su grupo"""
    selected = bpy.context.selected_objects
    gids = {o[GROUP_KEY] for o in selected if GROUP_KEY in o.keys()}
    if not gids:
        return
    for obj in scene.objects:
        if obj.name.startswith("Siro"):
            continue
        if obj.get(GROUP_KEY) in gids and not obj.select_get():
            try:
                obj.select_set(True)
            except RuntimeError:
                pass  # objeto fuera del view layer


def register_handler():
    if _sync_selection not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_sync_selection)


def unregister_handler():
    if _sync_selection in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_selection)


class SIRO_OT_group(bpy.types.Operator):
    """Agrupa las piezas seleccionadas: se seleccionan y transforman como una sola, sin fusionar las mallas"""
    bl_idname = "siro.group"
    bl_label = "Agrupar"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        gid = max((o.get(GROUP_KEY, 0) for o in bpy.data.objects), default=0) + 1
        for obj in context.selected_objects:
            obj[GROUP_KEY] = gid
        self.report({'INFO'}, f"Grupo de {len(context.selected_objects)} piezas")
        return {'FINISHED'}


class SIRO_OT_ungroup(bpy.types.Operator):
    """Deshace el grupo de las piezas seleccionadas"""
    bl_idname = "siro.ungroup"
    bl_label = "Desagrupar"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(GROUP_KEY in o.keys() for o in context.selected_objects)

    def execute(self, context):
        gids = {o[GROUP_KEY] for o in context.selected_objects if GROUP_KEY in o.keys()}
        count = 0
        for obj in bpy.data.objects:
            if obj.get(GROUP_KEY) in gids:
                del obj[GROUP_KEY]
                count += 1
        self.report({'INFO'}, f"{count} piezas desagrupadas")
        return {'FINISHED'}
