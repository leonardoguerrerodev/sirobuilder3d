import bpy


class SIRO_OT_scene_mm(bpy.types.Operator):
    """Configura la escena en milímetros (unidades y paneles numéricos en mm)"""
    bl_idname = "siro.scene_mm"
    bl_label = "Escena en mm"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        units = context.scene.unit_settings
        units.system = 'METRIC'
        units.scale_length = 0.001
        units.length_unit = 'MILLIMETERS'
        return {'FINISHED'}


class SIRO_PT_main(bpy.types.Panel):
    bl_label = "SiroBuilder"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroBuilder"

    def draw(self, context):
        layout = self.layout
        layout.operator("siro.scene_mm", icon='SNAP_INCREMENT')

        box = layout.box()
        box.label(text="Corte con plano", icon='MOD_MULTIRES')
        col = box.column(align=True)
        col.scale_y = 1.6  # botones grandes, estilo 3D Builder
        col.operator("siro.add_cut_plane", icon='MESH_PLANE')
        col.operator("siro.cut", icon='UV_EDGESEL')
