import bpy

from ..operators import camera_nav, cut, select_mark
from . import overlay


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
    """Cabecera: modos y acciones siempre visibles; el resto son secciones retráctiles"""
    bl_label = "SiroBuilder"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroBuilder"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("siro.scene_mm", icon='SNAP_INCREMENT')
        col.operator("siro.toggle_dims", icon='DRIVER_DISTANCE', depress=overlay.handler_active())
        col.operator("siro.cam_mode", icon='VIEW_PAN', depress=camera_nav.nav_active())
        col.operator("siro.select_mark", icon='RESTRICT_SELECT_OFF', depress=select_mark.mark_active())

        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("siro.group", icon='GROUP')
        row.operator("siro.ungroup", icon='X')


class _SiroSection:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroBuilder"
    bl_parent_id = "SIRO_PT_main"


class SIRO_PT_add(_SiroSection, bpy.types.Panel):
    bl_label = "Añadir"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        grid = self.layout.grid_flow(columns=3, align=True)
        grid.scale_y = 1.4
        grid.operator("mesh.primitive_cube_add", text="Cubo", icon='MESH_CUBE')
        grid.operator("mesh.primitive_uv_sphere_add", text="Esfera", icon='MESH_UVSPHERE')
        grid.operator("mesh.primitive_cylinder_add", text="Cilindro", icon='MESH_CYLINDER')
        grid.operator("mesh.primitive_cone_add", text="Cono", icon='MESH_CONE')
        grid.operator("mesh.primitive_torus_add", text="Toro", icon='MESH_TORUS')
        grid.operator("mesh.primitive_plane_add", text="Plano", icon='MESH_PLANE')


class SIRO_PT_cut(_SiroSection, bpy.types.Panel):
    bl_label = "Corte"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = 1.6  # botones grandes, estilo 3D Builder
        col.operator("siro.add_cut_plane", icon='MESH_PLANE')
        col.operator("siro.cut", icon='UV_EDGESEL')
        col.separator()
        col.operator("siro.draw_contour", icon='GREASEPENCIL')
        col.operator("siro.free_cut", icon='SELECT_INTERSECT')

        cutter = context.scene.objects.get(cut.CUTTER_NAME)
        contour = context.scene.objects.get(cut.CONTOUR_NAME)
        if cutter is not None:
            layout.label(text="Sólido = se conserva · rejilla = se descarta", icon='INFO')
        if contour is not None:
            layout.label(text="Dibuja sobre la pieza y pulsa Recortar", icon='INFO')
        if cutter is not None or contour is not None:
            col = layout.column()
            col.scale_y = 1.3
            col.operator("siro.cancel_cut", icon='X')


class SIRO_PT_mesh(_SiroSection, bpy.types.Panel):
    bl_label = "Malla"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.scale_y = 1.6
        col.operator("siro.repair", icon='CHECKMARK')
        col.operator("siro.simplify", icon='MOD_DECIM')


class SIRO_PT_place(_SiroSection, bpy.types.Panel):
    bl_label = "Espejo y Acople"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_y = 1.6
        for axis in ('X', 'Y', 'Z'):
            row.operator("siro.mirror", text=f"Espejo {axis}").axis = axis
        from ..operators import snap_dock
        active = snap_dock.dock_active(context.scene.tool_settings)
        col = layout.column()
        col.scale_y = 1.6
        col.operator("siro.snap_dock", icon='SNAP_ON' if active else 'SNAP_OFF', depress=active)


class SIRO_PT_transform(_SiroSection, bpy.types.Panel):
    bl_label = "Transformar"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None:
            layout.label(text="Selecciona una pieza", icon='INFO')
            return
        col = layout.column()
        col.prop(obj, "location")
        col.prop(obj, "rotation_euler", text="Rotación")
        col.prop(obj, "dimensions", text="Dimensiones")
        col = layout.column()
        col.scale_y = 1.6
        col.operator("siro.align_base", icon='TRIA_DOWN_BAR')


class SIRO_PT_relief(_SiroSection, bpy.types.Panel):
    bl_label = "Relieve desde imagen"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = 1.6
        col.operator("siro.depthmap_relief", icon='IMPORT')
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return
        disp = obj.modifiers.get("SiroRelieve")
        sub = obj.modifiers.get("SiroResolucion")
        if disp is None:
            return
        if disp.texture is not None:
            layout.prop(disp.texture, "filter_size", text="Suavizado")
        if sub is not None:
            layout.prop(sub, "levels", text="Resolución")
        layout.prop(disp, "strength", text="Profundidad (mm)")
        col = layout.column()
        col.scale_y = 1.6
        col.operator("siro.apply_relief", icon='CHECKMARK')
