"""Toolbar de SiroBuilder: una sola pestaña, secciones al ras.

Antes había dos pestañas (`SiroBuilder` y `SiroLab`) y las secciones colgaban de
un panel contenedor que repetía el nombre de la pestaña. Las dos cosas se
fueron: en un N-panel angosto, cada nivel de anidamiento cuesta ancho, y una
pestaña de laboratorio solo tiene sentido mientras la herramienta está en prueba.
"""

import bpy

from ..operators import camera_nav, cut, depthmap_relief, extrude_down, select_mark, shape_cut
from . import iconos, overlay


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
EJES = ('X', 'Y', 'Z')


def escena_en_mm(scene):
    u = scene.unit_settings
    return u.system == 'METRIC' and u.length_unit == 'MILLIMETERS' and abs(u.scale_length - 0.001) < 1e-9


def _aviso(layout, texto, icono='INFO'):
    """Los hints van en caja: leídos como aviso y no como texto suelto"""
    layout.box().label(text=texto, icon=icono)


def _sin_pieza(layout, verbo):
    """Aviso de estado vacío. Sin esto los botones simplemente no responden y el
    panel parece roto — pasó con el corte por forma y costó una sesión."""
    _aviso(layout, f"Selecciona una pieza para {verbo}", 'ERROR')


# Las que Blender rellena desde el CONTEXTO en el `invoke` del operador (el
# cursor 3D, la orientación de la vista), no valores del botón. Su "default" no
# es un valor: es un centinela que significa "todavía no se sabe".
#
# `scale` es el caso que rompía: en los operadores de añadir su default es
# (0,0,0) y quiere decir "sin escala", pero escrito literalmente multiplica la
# geometría por cero y la primitiva nace **colapsada en un punto** — 64 vértices
# y 0 mm de lado, invisible. El gizmo quedaba plantado sobre ese objeto de
# tamaño cero en el origen y parecía que nada se podía mover.
_PROPS_DE_CONTEXTO = frozenset({"location", "rotation", "scale", "align"})


def _boton(layout, idname, **kwargs):
    """`layout.operator` que deja las propiedades en su valor por defecto.

    Blender las recuerda de la última vez que corrió el operador, incluido lo
    que se haya tocado en el panel de rehacer (F9). Verificado en el Blender de
    Leo: bajó el ratio de Simplificar a 1 para probar, y desde ahí el botón
    quedó inservible —"no se pudo reducir"— sin ninguna pista de por qué. Un
    botón grande de una toolbar tiene que hacer siempre lo mismo.

    Lo que NO se toca son las propiedades de contexto (ver `_PROPS_DE_CONTEXTO`):
    ahí el default es un centinela, no un valor.
    """
    op = layout.operator(idname, **kwargs)
    for prop in op.bl_rna.properties:
        if prop.identifier == "rna_type" or prop.is_readonly:
            continue
        if prop.identifier in _PROPS_DE_CONTEXTO:
            continue
        try:
            setattr(op, prop.identifier, prop.default)
        except (TypeError, AttributeError):
            pass  # punteros y colecciones no tienen default asignable
    return op


def _fila_ejes(col, data, prop, etiqueta):
    """Los tres ejes de una propiedad vectorial, cada uno con su letra en color.

    Va fila por fila y no `col.prop(data, prop)` de una porque el icono se
    aplica por widget: el vector completo dibuja sus tres campos con las
    etiquetas que le pone Blender y no hay dónde meter el color.
    """
    for i, eje in enumerate(EJES):
        fila = col.row(align=True)
        fila.label(text=etiqueta if i == 0 else "", icon_value=iconos.icono(eje))
        fila.prop(data, prop, index=i, text="")


class _SiroSection:
    """Secciones al ras: misma pestaña, mismo aspecto, sin anidar unas en otras"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SiroBuilder"
    bl_icon = 'DOT'

    def draw_header(self, context):
        self.layout.label(icon=self.bl_icon)


# El orden de las secciones sigue el flujo de trabajo: acciones → añadir →
# transformar → cortar (plano, forma) → rellenar → arreglar malla → espejo y
# acople → relieve. Blender las ordena por orden de registro (ver __init__.py).


class SIRO_PT_main(_SiroSection, bpy.types.Panel):
    """Lo que se usa en cualquier momento, sin importar en qué paso del trabajo estés"""
    bl_label = "Acciones"
    bl_icon = 'SHADERFX'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = BOTON
        # setup de una sola vez: no merece un botón permanente en la zona más
        # valiosa del panel, así que se esconde en cuanto está hecho
        if not escena_en_mm(context.scene):
            col.operator("siro.scene_mm", icon='SNAP_INCREMENT')
        col.operator("siro.toggle_dims", icon='DRIVER_DISTANCE', depress=overlay.handler_active())
        col.operator("siro.cam_mode", icon='VIEW_PAN', depress=camera_nav.nav_active())
        col.operator("siro.select_mark", icon='RESTRICT_SELECT_OFF', depress=select_mark.mark_active())

        row = layout.row(align=True)
        row.scale_y = BOTON
        row.operator("siro.group", icon='GROUP')
        row.operator("siro.ungroup", icon='LIBRARY_DATA_BROKEN')

        col = layout.column()
        col.scale_y = BOTON
        _boton(col, "siro.align_base", icon='TRIA_DOWN_BAR')


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
            op = _boton(grid, idname, text=texto, icon=icono)
            for prop, valor in props.items():
                setattr(op, prop, valor)


class SIRO_PT_transform(_SiroSection, bpy.types.Panel):
    bl_label = "Transformar"
    bl_icon = 'OBJECT_ORIGIN'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None:
            _sin_pieza(layout, "transformar")
            return
        col = layout.column(align=True)
        _fila_ejes(col, obj, "location", "Posición")
        col.separator()
        _fila_ejes(col, obj, "rotation_euler", "Rotación")
        col.separator()
        _fila_ejes(col, obj, "dimensions", "Dimensiones")


class SIRO_PT_cut(_SiroSection, bpy.types.Panel):
    bl_label = "Plano de corte"
    bl_icon = 'MOD_BOOLEAN'

    def draw(self, context):
        layout = self.layout
        plano = context.scene.objects.get(cut.CUTTER_NAME)
        obj = context.active_object
        # mismo aviso que el resto de las secciones: sin esto los botones quedan
        # grises sin decir por qué y el panel parece roto
        if plano is None and (obj is None or obj.type != 'MESH'):
            _sin_pieza(layout, "cortar")
            return

        col = layout.column(align=True)
        col.scale_y = BOTON
        _boton(col, "siro.add_cut_plane", icon='MESH_PLANE')
        col.operator("siro.cut", icon='UV_EDGESEL')

        if plano is not None:
            _aviso(layout, "Sólido = se conserva · fantasma = se descarta", 'GHOST_ENABLED')
            col = layout.column()
            col.scale_y = BOTON
            _boton(col, "siro.cancel_cut", icon='CANCEL')


class SIRO_PT_shape_cut(_SiroSection, bpy.types.Panel):
    """Corte por forma dibujada sobre el viewport, estilo Nomad Sculpt"""
    bl_label = "Corte por forma"
    bl_icon = 'GREASEPENCIL'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            _sin_pieza(layout, "cortar")
            return

        # Recortar/Partir es el MODO, y cada forma es la acción que arranca el
        # trazo: elegís la forma y ya estás dibujando, como en Nomad y 3D
        # Builder. Cuando la forma era un simple selector parecía un botón de
        # acción, se clickeaba, y no pasaba nada.
        row = layout.row(align=True)
        row.scale_y = BOTON
        row.prop(scene, "siro_action", expand=True)

        grid = layout.grid_flow(columns=2, align=True)
        grid.scale_y = BOTON
        for ident, nombre, _desc, icono in shape_cut.SHAPES:
            op = grid.operator("siro.shape_cut", text=nombre, icon=icono)
            op.shape = ident
            op.action = scene.siro_action
            op.keep = scene.siro_keep

        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "siro_keep")

        _aviso(layout, "Dibuja sobre el viewport · Esc cancela", 'MOUSE_MOVE')


class SIRO_PT_extrude(_SiroSection, bpy.types.Panel):
    """Extrudir hacia abajo, como 3D Builder: lo que se ve de la pieza desde
    arriba baja recto hasta el fondo y se une a ella, sin cortarla"""
    bl_label = "Extrudir hacia abajo"
    bl_icon = 'TRIA_DOWN_BAR'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        plano = context.scene.objects.get(cut.CUTTER_NAME)
        obj = context.active_object

        if plano is None and (obj is None or obj.type != 'MESH'):
            _sin_pieza(layout, "extrudir")
            return

        col = layout.column()
        col.scale_y = BOTON
        _boton(col, "siro.extrude_plane", icon='MESH_PLANE')
        if plano is None:
            return

        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(plano, "location", index=2, text="Altura")
        col.prop(scene, "siro_base_z")
        col.prop(scene, "siro_resolucion")

        # el paso depende del tamaño de la pieza, así que el número abstracto de
        # la grilla no le dice nada a nadie. Va como texto y no en caja: tres
        # cajas apiladas se comen un panel angosto.
        pieza = context.scene.objects.get(plano.get("siro_target", "")) or obj
        if pieza is not None and pieza.type == 'MESH':
            paso = extrude_down.paso_silueta(pieza, int(scene.siro_resolucion))
            col.label(text=f"Escalón del borde: {paso:.3f} mm")

        _aviso(layout, "El fantasma marca lo que se rellena hacia abajo", 'GHOST_ENABLED')

        col = layout.column(align=True)
        col.scale_y = BOTON
        _boton(col, "siro.extrude_down", icon='TRIA_DOWN_BAR').resolucion = scene.siro_resolucion
        _boton(col, "siro.cancel_cut", text="Cancelar", icon='CANCEL')


class SIRO_PT_mesh(_SiroSection, bpy.types.Panel):
    bl_label = "Malla"
    bl_icon = 'MESH_DATA'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            _sin_pieza(layout, "arreglar")
            return
        row = layout.row(align=True)
        row.scale_y = BOTON
        _boton(row, "siro.boolean", text="Fusionar", icon='SELECT_EXTEND').operation = 'UNION'
        _boton(row, "siro.boolean", text="Restar", icon='SELECT_SUBTRACT').operation = 'DIFFERENCE'
        col = layout.column(align=True)
        col.scale_y = BOTON
        _boton(col, "siro.repair", icon='MODIFIER_ON')
        _boton(col, "siro.simplify", icon='MOD_DECIM')
        _aviso(layout, "La pieza activa recibe el resultado", 'RESTRICT_SELECT_OFF')


class SIRO_PT_place(_SiroSection, bpy.types.Panel):
    bl_label = "Espejo y Acople"
    bl_icon = 'MOD_MIRROR'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_y = BOTON
        # mismas letras de color que en Transformar: un solo idioma para los ejes
        for eje in EJES:
            _boton(row, "siro.mirror", text=eje, icon_value=iconos.icono(eje)).axis = eje
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
        scene = context.scene
        col = layout.column(align=True)
        col.scale_y = BOTON
        _boton(col, "siro.depthmap_relief", icon='IMPORT')
        _boton(col, "siro.bake_depthmap", icon='MOD_SHRINKWRAP')
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            _sin_pieza(layout, "aplicar el relieve")
            return
        disp = obj.modifiers.get(depthmap_relief.DISP_MOD)
        if disp is None:
            return

        # Preparar va antes que Suavizado/Profundidad: primero se fabrica el
        # mapa de alturas, después se regula cuánto y con qué suavidad desplaza.
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "siro_dm_domo")
        col.prop(scene, "siro_dm_contraste")
        col.prop(scene, "siro_dm_tolerancia")
        col.prop(scene, "siro_dm_invertir")
        col = layout.column()
        col.scale_y = BOTON
        _boton(col, "siro.prep_depthmap", icon='IMAGE_ZDEPTH')

        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        if disp.texture is not None:
            col.prop(disp.texture, "filter_size", text="Suavizado")
        col.prop(disp, "strength", text="Profundidad (mm)")
        col = layout.column()
        col.scale_y = BOTON
        _boton(col, "siro.apply_relief", icon='CHECKMARK')


def _register_props():
    Scene = bpy.types.Scene
    Scene.siro_action = bpy.props.EnumProperty(
        name="Acción",
        items=(
            ('TRIM', "Recortar", "Deja una sola pieza"),
            ('SPLIT', "Partir", "Deja las dos partes como piezas separadas y selladas"),
        ),
        default='TRIM',
    )
    Scene.siro_base_z = bpy.props.FloatProperty(
        name="Fondo",
        description="Altura hasta la que baja la extrusión; 0 es la placa, como en 3D Builder",
        default=0.0,
        unit='LENGTH',
    )
    Scene.siro_resolucion = bpy.props.EnumProperty(
        name="Detalle",
        description="Con cuánto detalle se muestrea la silueta vista desde arriba",
        items=extrude_down.RESOLUCIONES,
        default='256',
    )
    Scene.siro_keep = bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('OUT', "Exterior", "Se queda con lo de fuera de la forma dibujada"),
            ('IN', "Interior", "Se queda con lo de dentro de la forma dibujada"),
        ),
        default='OUT',
    )
    # "Preparar depthmap": fabricar altura a partir de una imagen a color
    Scene.siro_dm_domo = bpy.props.FloatProperty(
        name="Domo",
        description="Cuánto manda la forma abombada de la silueta y cuánto el detalle de la imagen. 0 = solo detalle, 1 = cabujón liso",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
    )
    Scene.siro_dm_contraste = bpy.props.FloatProperty(
        name="Contraste",
        description="Gamma sobre el detalle: por debajo de 1 levanta las zonas bajas, por encima las hunde",
        default=1.0, min=0.2, max=5.0,
    )
    Scene.siro_dm_tolerancia = bpy.props.FloatProperty(
        name="Tolerancia de fondo",
        description="Cuánto se puede parecer un píxel al color de las esquinas para contarlo como fondo. Solo se usa si la imagen no trae alpha",
        default=0.15, min=0.01, max=1.0, subtype='FACTOR',
    )
    Scene.siro_dm_invertir = bpy.props.BoolProperty(
        name="Invertir",
        description="Da vuelta la altura: lo que subía baja. El fondo se queda plano igual",
        default=False,
    )


def _unregister_props():
    for prop in ("siro_action", "siro_base_z", "siro_resolucion", "siro_keep",
                 "siro_dm_domo", "siro_dm_contraste", "siro_dm_tolerancia", "siro_dm_invertir"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
