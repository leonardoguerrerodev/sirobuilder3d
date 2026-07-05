import bpy


class SIRO_OT_free_cut(bpy.types.Operator):
    """Recorta la pieza proyectando el contorno seleccionado desde la vista actual (Knife Project).
Uso: dibuja el contorno (curva o malla) frente a la pieza, selecciónalo, Shift+clic en la pieza, y ejecuta — idealmente en vista ortográfica"""
    bl_idname = "siro.free_cut"
    bl_label = "Corte de forma libre"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('INSIDE', "Interior del contorno", "Borra lo que queda fuera del contorno"),
            ('OUTSIDE', "Exterior del contorno", "Borra lo que queda dentro del contorno"),
            ('MARK', "Solo marcar el corte", "Corta las aristas sin borrar nada"),
        ),
        default='INSIDE',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        target = context.active_object
        cutters = [o for o in context.selected_objects if o is not target]
        if len(cutters) != 1 or cutters[0].type not in {'CURVE', 'MESH'}:
            self.report({'ERROR'}, "Selecciona el contorno (curva o malla) y luego Shift+clic en la pieza")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        try:
            # proyecta el contorno desde la vista y corta a través; deja
            # seleccionadas las caras dentro de la silueta
            bpy.ops.mesh.knife_project(cut_through=True)
            if self.mode == 'INSIDE':
                bpy.ops.mesh.select_all(action='INVERT')
            if self.mode != 'MARK':
                bpy.ops.mesh.delete(type='FACE')
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}
