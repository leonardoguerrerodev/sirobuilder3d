import bpy

from ..operators import camera_nav, cut, select_mark, shape_cut
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


BOTON = 1.5  # alto único para todos los botones de acción


def _aviso(layout, texto, icono='INFO'):
    """Los hints van en caja: leídos como aviso y no como texto suelto"""
    layout.box().label(text=texto, icon=icono)


class SIRO_PT_main(bpy.types.Panel):
    """Cabecera: modos y acciones siempre visibles; el resto son secciones retráctiles"""
    bl_label = "SiroBuilder"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroBuilder"

    def draw_header(self, context):
        self.layout.label(icon='SHADERFX')

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = BOTON
        col.operator("siro.scene_mm", icon='SNAP_INCREMENT')
        col.operator("siro.toggle_dims", icon='DRIVER_DISTANCE', depress=overlay.handler_active())
        col.operator("siro.cam_mode", icon='VIEW_PAN', depress=camera_nav.nav_active())
        col.operator("siro.select_mark", icon='RESTRICT_SELECT_OFF', depress=select_mark.mark_active())

        row = layout.row(align=True)
        row.scale_y = BOTON
        row.operator("siro.group", icon='GROUP')
        row.operator("siro.ungroup", icon='LIBRARY_DATA_BROKEN')


class _SiroSection:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroBuilder"
    bl_parent_id = "SIRO_PT_main"
    bl_icon = 'DOT'

    def draw_header(self, context):
        self.layout.label(icon=self.bl_icon)


# El orden de las secciones sigue el flujo de trabajo:
# añadir → transformar → cortar → arreglar malla → espejo/acople → relieve.
# Blender ordena los subpaneles por orden de registro (ver __init__.py).

# Tamaños en la escala del addon (1 unidad = 1 mm): piezas de ~30 mm, no los
# 2 mm que trae Blender por defecto. Es una tabla y no código suelto para que
# el test headless pueda comprobar las medidas reales que salen de aquí.
PRIMITIVAS = (
    ("mesh.primitive_cube_add", "Cubo", 'MESH_CUBE', {"size": 30.0}),
    ("mesh.primitive_uv_sphere_add", "Esfera", 'MESH_UVSPHERE', {"radius": 15.0}),
    ("mesh.primitive_cylinder_add", "Cilindro", 'MESH_CYLINDER', {"radius": 15.0, "depth": 30.0}),
    ("mesh.primitive_cone_add", "Cono", 'MESH_CONE', {"radius1": 15.0, "depth": 30.0}),
    ("mesh.primitive_torus_add", "Toro", 'MESH_TORUS', {"major_radius": 12.0, "minor_radius": 4.0}),
    ("mesh.primitive_plane_add", "Plano", 'MESH_PLANE', {"size": 30.0}),
)


class SIRO_PT_add(_SiroSection, bpy.types.Panel):
    bl_label = "Añadir"
    bl_icon = 'ADD'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        grid = self.layout.grid_flow(columns=3, align=True)
        grid.scale_y = BOTON
        for idname, texto, icono, props in PRIMITIVAS:
            op = grid.operator(idname, text=texto, icon=icono)
            for prop, valor in props.items():
                setattr(op, prop, valor)


class SIRO_PT_transform(_SiroSection, bpy.types.Panel):
    bl_label = "Transformar"
    bl_icon = 'OBJECT_ORIGIN'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None:
            _aviso(layout, "Selecciona una pieza")
            return
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(obj, "location", text="Posición")
        col.prop(obj, "rotation_euler", text="Rotación")
        col.prop(obj, "dimensions", text="Dimensiones")
        col = layout.column()
        col.scale_y = BOTON
        col.operator("siro.align_base", icon='TRIA_DOWN_BAR')


class SIRO_PT_cut(_SiroSection, bpy.types.Panel):
    bl_label = "Corte"
    bl_icon = 'MOD_BOOLEAN'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = BOTON
        col.operator("siro.add_cut_plane", icon='MESH_PLANE')
        col.operator("siro.cut", icon='UV_EDGESEL')
        col.separator()
        col.operator("siro.draw_contour", icon='GREASEPENCIL')
        col.operator("siro.free_cut", icon='SELECT_INTERSECT')

        cutter = context.scene.objects.get(cut.CUTTER_NAME)
        contour = context.scene.objects.get(cut.CONTOUR_NAME)
        if cutter is not None:
            _aviso(layout, "Sólido = se conserva · fantasma = se descarta", 'GHOST_ENABLED')
        if contour is not None:
            _aviso(layout, "Línea = cuchillo · trazo cerrado = contorno", 'GREASEPENCIL')
        if cutter is not None or contour is not None:
            col = layout.column()
            col.scale_y = BOTON
            col.operator("siro.cancel_cut", icon='CANCEL')


class SIRO_PT_mesh(_SiroSection, bpy.types.Panel):
    bl_label = "Malla"
    bl_icon = 'MESH_DATA'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_y = BOTON
        row.operator("siro.boolean", text="Fusionar", icon='SELECT_EXTEND').operation = 'UNION'
        row.operator("siro.boolean", text="Restar", icon='SELECT_SUBTRACT').operation = 'DIFFERENCE'
        col = layout.column(align=True)
        col.scale_y = BOTON
        col.operator("siro.repair", icon='SHADERFX')
        col.operator("siro.simplify", icon='MOD_DECIM')
        _aviso(layout, "La pieza activa recibe el resultado", 'RESTRICT_SELECT_OFF')


class SIRO_PT_place(_SiroSection, bpy.types.Panel):
    bl_label = "Espejo y Acople"
    bl_icon = 'MOD_MIRROR'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_y = BOTON
        for axis in ('X', 'Y', 'Z'):
            row.operator("siro.mirror", text=axis, icon='MOD_MIRROR').axis = axis
        from ..operators import snap_dock
        active = snap_dock.dock_active(context.scene.tool_settings)
        col = layout.column()
        col.scale_y = BOTON
        col.operator("siro.snap_dock", icon='SNAP_ON' if active else 'SNAP_OFF', depress=active)


class SIRO_PT_relief(_SiroSection, bpy.types.Panel):
    bl_label = "Relieve desde imagen"
    bl_icon = 'MOD_DISPLACE'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = BOTON
        col.operator("siro.depthmap_relief", icon='IMPORT')
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return
        disp = obj.modifiers.get("SiroRelieve")
        if disp is None:
            return
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        if disp.texture is not None:
            col.prop(disp.texture, "filter_size", text="Suavizado")
        col.prop(disp, "strength", text="Profundidad (mm)")
        col = layout.column()
        col.scale_y = BOTON
        col.operator("siro.apply_relief", icon='CHECKMARK')


# --- SiroLab: pestaña aparte, banco de pruebas de las herramientas nuevas ----
# Vive en su propia pestaña a propósito: acá se desarrollan y se prueban las
# herramientas estilo Nomad sin tocar el toolbar principal. Cuando estén
# sólidas se mueven a las secciones de "SiroBuilder" y este panel se borra.

def _register_lab_props():
    Scene = bpy.types.Scene
    Scene.siro_shape = bpy.props.EnumProperty(
        name="Forma",
        items=[(i, n, d, ic, k) for k, (i, n, d, ic) in enumerate(shape_cut.SHAPES)],
        default='LASSO',
    )
    Scene.siro_keep = bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('OUT', "Exterior", "Se queda con lo de fuera de la forma dibujada"),
            ('IN', "Interior", "Se queda con lo de dentro de la forma dibujada"),
        ),
        default='OUT',
    )
    Scene.siro_solver = bpy.props.EnumProperty(
        name="Calidad",
        items=(
            ('FLOAT', "Rápida", "Para mallas densas, como los relieves"),
            ('EXACT', "Exacta", "Más lenta; solo si el corte rápido deja artefactos"),
        ),
        default='FLOAT',
    )


def _unregister_lab_props():
    for prop in ("siro_shape", "siro_keep", "siro_solver"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)


class SIRO_PT_lab(bpy.types.Panel):
    """Herramientas nuevas en prueba, todavía fuera del toolbar principal"""
    bl_label = "Corte por forma"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroLab"

    def draw_header(self, context):
        self.layout.label(icon='SHADERFX')

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.label(text="Forma", icon='GP_SELECT_STROKE')
        grid = col.grid_flow(columns=3, align=True)
        grid.scale_y = BOTON
        grid.prop(scene, "siro_shape", expand=True)

        col = layout.column(align=True)
        col.scale_y = BOTON
        for accion, texto, icono in (
            ('TRIM', "Recortar", 'SELECT_SUBTRACT'),
            ('SPLIT', "Partir", 'MOD_BEVEL'),
        ):
            op = col.operator("siro.shape_cut", text=texto, icon=icono)
            op.shape = scene.siro_shape
            op.action = accion
            op.keep = scene.siro_keep
            op.solver = scene.siro_solver

        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "siro_keep")
        col.prop(scene, "siro_solver")

        _aviso(layout, "Dibuja sobre el viewport · Esc cancela", 'MOUSE_MOVE')
