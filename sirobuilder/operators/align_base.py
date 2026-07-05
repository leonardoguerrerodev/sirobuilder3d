import bpy
from mathutils import Vector


class SIRO_OT_align_base(bpy.types.Operator):
    """Apoya las piezas seleccionadas sobre el suelo (Z mínimo = 0)"""
    bl_idname = "siro.align_base"
    bl_label = "Alinear a la base"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            min_z = min((obj.matrix_world @ Vector(c)).z for c in obj.bound_box)
            obj.location.z -= min_z
        return {'FINISHED'}
