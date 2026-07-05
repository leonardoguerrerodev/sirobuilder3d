import bpy

from ..operators import snap_dock


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
        obj = context.active_object

        layout.operator("siro.scene_mm", icon='SNAP_INCREMENT')

        box = layout.box()
        box.label(text="Corte", icon='MOD_MULTIRES')
        col = box.column(align=True)
        col.scale_y = 1.6  # botones grandes, estilo 3D Builder
        col.operator("siro.add_cut_plane", icon='MESH_PLANE')
        col.operator("siro.cut", icon='UV_EDGESEL')
        col.operator("siro.free_cut", icon='GREASEPENCIL')

        box = layout.box()
        box.label(text="Malla", icon='TOOL_SETTINGS')
        col = box.column(align=True)
        col.scale_y = 1.6
        col.operator("siro.repair", icon='CHECKMARK')
        col.operator("siro.simplify", icon='MOD_DECIM')

        box = layout.box()
        box.label(text="Espejo", icon='MOD_MIRROR')
        row = box.row(align=True)
        row.scale_y = 1.6
        for axis in ('X', 'Y', 'Z'):
            row.operator("siro.mirror", text=axis).axis = axis

        active = snap_dock.dock_active(context.scene.tool_settings)
        col = layout.column()
        col.scale_y = 1.6
        col.operator(
            "siro.snap_dock",
            icon='SNAP_ON' if active else 'SNAP_OFF',
            depress=active,
        )

        if obj is not None:
            box = layout.box()
            box.label(text="Transformar", icon='OBJECT_ORIGIN')
            col = box.column()
            col.prop(obj, "location")
            col.prop(obj, "rotation_euler", text="Rotación")
            col.prop(obj, "dimensions", text="Dimensiones")

        box = layout.box()
        box.label(text="Relieve desde imagen", icon='IMAGE_DATA')
        col = box.column(align=True)
        col.scale_y = 1.6
        col.operator("siro.depthmap_relief", icon='IMPORT')
        if obj is not None and obj.type == 'MESH':
            disp = obj.modifiers.get("SiroRelieve")
            sub = obj.modifiers.get("SiroResolucion")
            if disp is not None:
                if disp.texture is not None:
                    box.prop(disp.texture, "filter_size", text="Suavizado")
                if sub is not None:
                    box.prop(sub, "levels", text="Resolución")
                box.prop(disp, "strength", text="Profundidad (mm)")
                col = box.column()
                col.scale_y = 1.6
                col.operator("siro.apply_relief", icon='CHECKMARK')
