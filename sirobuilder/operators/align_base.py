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
            if obj.type != 'MESH' or not obj.data.vertices:
                continue
            # sobre los vértices reales, no sobre `bound_box`: esa caja es LOCAL,
            # y al rotarla sus esquinas caen más abajo que la malla. Medido: un
            # toro rotado quedaba apoyado sobre la caja imaginaria, con 4,30 mm
            # de aire debajo de la pieza.
            min_z = min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
            obj.location.z -= min_z
        return {'FINISHED'}
