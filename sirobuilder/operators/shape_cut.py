"""Corte por forma dibujada en pantalla, estilo Nomad Sculpt (Trim / Split).

El módulo está partido en dos mitades con una costura deliberada:

- El **núcleo de geometría** (`build_cutter` y para abajo) no sabe nada de
  regiones ni de viewport: recibe **rayos** ya calculados, uno por punto del
  contorno. Eso lo hace testeable headless y, de paso, correcto tanto en vista
  ortográfica (rayos paralelos → prisma) como en perspectiva (rayos divergentes
  → tronco de pirámide), a diferencia del prisma de eje único de free_cut.py.
- El **modal de entrada** captura los puntos de pantalla y la vista en el
  momento del trazo, y convierte esos puntos en rayos.

Por qué importa lo de "en el momento del trazo": `context.region_data` solo
existe en la región WINDOW. Al lanzar un operador desde un botón del N-panel la
región de contexto es la UI y queda en None — verificado en el Blender de Leo:
el corte libre viejo caía a un fallback de vista superior y cortaba a 90° de lo
que se estaba dibujando.
"""

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from .boolean_ops import (
    _apply_bool,
    _apply_pending_modifiers,
    _make_single_user,
    _open_edge_count,
)

CUTTER_NAME = "SiroCortador"

SHAPES = (
    ('LASSO', "Lazo", "Trazo a mano alzada; se cierra solo al soltar", 'GREASEPENCIL'),
    ('LINE', "Línea", "Cuchillo: parte la pieza entera de lado a lado", 'DRIVER_DISTANCE'),
    ('RECT', "Rectángulo", "Arrastra la diagonal", 'MESH_PLANE'),
    ('ELLIPSE', "Elipse", "Arrastra la diagonal", 'MESH_CIRCLE'),
    ('POLYGON', "Polígono", "Un clic por vértice; Enter cierra", 'MOD_SIMPLIFY'),
)

_ELLIPSE_SEGMENTS = 48


def shape_points(shape, anclas, ancho, alto):
    """Contorno 2D cerrado, en píxeles de la región, para el modo dado.

    `anclas` son los puntos que puso el usuario (el trazo entero en Lazo y
    Polígono; inicio y fin en los demás). `ancho`/`alto` son los de la región:
    la Línea los necesita para salirse de pantalla por los dos extremos.
    El contorno vuelve sin repetir el primer punto al final.
    """
    if shape == 'LASSO':
        return _simplify(anclas)
    if shape == 'POLYGON':
        return _dedupe(anclas)
    if len(anclas) < 2:
        return []
    a, b = Vector(anclas[0]), Vector(anclas[-1])
    if shape == 'RECT':
        return [(a.x, a.y), (b.x, a.y), (b.x, b.y), (a.x, b.y)]
    if shape == 'ELLIPSE':
        centro, radio = (a + b) / 2, (b - a) / 2
        return [
            (centro.x + radio.x * math.cos(t), centro.y + radio.y * math.sin(t))
            for t in (2 * math.pi * i / _ELLIPSE_SEGMENTS for i in range(_ELLIPSE_SEGMENTS))
        ]
    if shape == 'LINE':
        return _knife_polygon(a, b, ancho, alto)
    return []


def _dedupe(puntos):
    limpio = []
    for p in puntos:
        if not limpio or (Vector(p) - Vector(limpio[-1])).length > 1.0:
            limpio.append(tuple(p))
    if len(limpio) > 2 and (Vector(limpio[0]) - Vector(limpio[-1])).length < 1.0:
        limpio.pop()
    return limpio


def _rdp(points, tol):
    """Douglas-Peucker: reduce la polilínea conservando la forma dentro de tol"""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i0, i1 = stack.pop()
        a, b = points[i0], points[i1]
        ab = b - a
        length = ab.length
        dmax, imax = tol, -1
        for i in range(i0 + 1, i1):
            if length < 1e-9:
                d = (points[i] - a).length
            else:
                d = ab.cross(points[i] - a).length / length
            if d > dmax:
                dmax, imax = d, i
        if imax != -1:
            keep[imax] = True
            stack += [(i0, imax), (imax, i1)]
    return [p for p, k in zip(points, keep) if k]


def _simplify(puntos):
    """Un trazo a mano alzada trae cientos de puntos; el booleano no necesita
    más de unas decenas. El Douglas-Peucker trabaja con vectores 3D — los
    puntos de pantalla van con z=0."""
    limpio = _dedupe(puntos)
    if len(limpio) <= 3:
        return limpio
    planos = [Vector((x, y, 0.0)) for x, y in limpio]
    lo = Vector((min(p[i] for p in planos) for i in range(3)))
    hi = Vector((max(p[i] for p in planos) for i in range(3)))
    return [(p.x, p.y) for p in _rdp(planos, max((hi - lo).length * 0.005, 0.5))]


def _knife_polygon(a, b, ancho, alto):
    """La línea del cuchillo, extendida más allá de la región por los dos
    extremos y cerrada por un costado fuera de pantalla: el único borde que
    toca la pieza es la línea dibujada.

    Resolverlo en 2D evita los casos degenerados que tenía la versión 3D de
    free_cut._close_knife (trazos vistos de canto, extremos coincidentes)."""
    d = b - a
    if d.length < 1e-6:
        return []
    d.normalize()
    lejos = (ancho + alto) * 2.0  # de sobra para salirse de cualquier región
    ext_a, ext_b = a - d * lejos, b + d * lejos
    lado = Vector((-d.y, d.x)) * lejos
    return [
        (ext_a.x, ext_a.y), (ext_b.x, ext_b.y),
        (ext_b.x + lado.x, ext_b.y + lado.y), (ext_a.x + lado.x, ext_a.y + lado.y),
    ]


def _bounding_sphere(obj):
    """Centro y radio en mundo que envuelven a la pieza"""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    center = sum(corners, Vector()) / len(corners)
    radius = max((c - center).length for c in corners)
    return center, max(radius, 1e-4)


def _cap_rings(rays, target):
    """Los dos anillos de vértices del cortador: uno delante de la pieza y otro
    detrás, a lo largo de cada rayo. Con rayos paralelos salen dos polígonos
    iguales (prisma); con rayos divergentes, uno más grande que el otro."""
    center, radius = _bounding_sphere(target)
    # profundidad medida sobre el rayo promedio: alcanza para cubrir la pieza
    # entera por delante y por detrás sin depender de dónde esté la cámara
    avg_dir = sum((d for _, d in rays), Vector()) / len(rays)
    if avg_dir.length < 1e-6:
        return None
    avg_dir.normalize()
    avg_origin = sum((o for o, _ in rays), Vector()) / len(rays)
    t_center = (center - avg_origin).dot(avg_dir)
    near, far = t_center - radius * 2.0, t_center + radius * 2.0
    return (
        [o + d * near for o, d in rays],
        [o + d * far for o, d in rays],
    )


def build_cutter(rays, target, name=CUTTER_NAME):
    """Sólido cerrado que barre el contorno dibujado a través de la pieza.

    `rays` es [(origen, dirección), ...], un rayo por punto del contorno, ya
    cerrado (el último punto NO repite al primero). Devuelve el objeto cortador
    enlazado a la escena, o None si el contorno era degenerado.
    """
    if len(rays) < 3:
        return None
    anillos = _cap_rings(rays, target)
    if anillos is None:
        return None
    near, far = anillos

    bm = bmesh.new()
    vn = [bm.verts.new(p) for p in near]
    vf = [bm.verts.new(p) for p in far]

    n = len(rays)
    for i in range(n):  # paredes laterales
        j = (i + 1) % n
        try:
            bm.faces.new((vn[i], vn[j], vf[j], vf[i]))
        except ValueError:
            pass  # cara repetida: el trazo pasó dos veces por el mismo punto

    # tapas trianguladas: un lazo a mano alzada suele ser cóncavo, y los
    # booleans digieren mal un ngon cóncavo gigante como cara única
    for anillo, verts in ((near, vn), (far, vf)):
        for tri in tessellate_polygon([anillo]):
            try:
                bm.faces.new(tuple(verts[k] for k in tri))
            except ValueError:
                pass

    # la orientación de tapas y paredes la resuelve esto de una vez
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    if not mesh.polygons:
        bpy.data.meshes.remove(mesh)
        return None

    cutter = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(cutter)
    return cutter


def _discard(obj):
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if not data.users:
        bpy.data.meshes.remove(data)


def apply_shape_cut(context, target, rays, action='TRIM', keep='IN'):
    """Corta `target` con la forma que describen `rays`.

    TRIM deja una sola pieza (`keep`: 'IN' lo que quedó dentro de la forma,
    'OUT' lo de fuera); SPLIT deja las dos, ambas selladas. Devuelve la lista
    de objetos resultantes, o None si el contorno no dio un cortador válido.
    Puede lanzar RuntimeError si el booleano falla: lo reporta quien llame.
    """
    # Mismo saneamiento que Fusionar/Restar: una copia enlazada hace fallar
    # modifier_apply, y un modificador vivo (el relieve sin aplicar, caso
    # típico acá) haría que el corte se aplique fuera de orden sobre la malla
    # base. Va antes de construir el cortador, que mide la pieza ya horneada.
    _make_single_user(target)
    _apply_pending_modifiers(context, target)

    cutter = build_cutter(rays, target)
    if cutter is None:
        return None

    # El solver se elige solo, con el mismo criterio que Fusionar/Restar (ver
    # boolean_ops): con las dos mallas cerradas MANIFOLD es correcto y además el
    # más rápido —medido, 8,06 s contra 9,87 s de FLOAT sobre 2 millones de
    # caras—, y con la pieza abierta es un no-op silencioso, así que ahí va
    # EXACT. FLOAT ya no se ofrece: sobre geometría coincidente —una esfera con
    # la forma centrada, el eje pasando por sus polos— devolvía la pieza en
    # volumen 0, y no era más rápido que MANIFOLD en ningún tamaño medido.
    solver = 'EXACT' if _open_edge_count(target) else 'MANIFOLD'
    try:
        if action == 'SPLIT':
            otra = target.copy()
            otra.data = target.data.copy()
            for coll in target.users_collection:
                coll.objects.link(otra)
            _apply_bool(context, otra, cutter, 'DIFFERENCE', solver)
            _apply_bool(context, target, cutter, 'INTERSECT', solver)
            resultado = [target, otra]
        else:
            _apply_bool(context, target, cutter, 'INTERSECT' if keep == 'IN' else 'DIFFERENCE', solver)
            resultado = [target]
    finally:
        _discard(cutter)

    bpy.ops.object.select_all(action='DESELECT')
    for obj in resultado:
        obj.select_set(True)
    context.view_layer.objects.active = target
    return resultado


# --- máquina de estados del trazo (sin Blender, testeable headless) --------

class StrokeState:
    """Traduce eventos de mouse en un contorno. Vive fuera del operador a
    propósito: mientras esta lógica estuvo dentro de `modal()` no había forma
    de que un test la tocara, y por eso pasó el bug que la hacía inútil —
    el modal se cancelaba solo con el RELEASE del clic que lo había arrancado.
    """

    def __init__(self, shape, width, height):
        self.shape = shape
        self.width = width
        self.height = height
        self.anclas = []
        # Hasta no ver un PRESS propio, la forma no está armada: al lanzar el
        # operador desde un botón del panel, el RELEASE de ESE clic llega acá.
        self.armado = False

    @property
    def libre(self):
        return self.shape in {'LASSO', 'POLYGON'}

    def event(self, tipo, valor, pos):
        """Devuelve 'DRAW' (redibujar), 'APPLY', 'CANCEL' o 'IGNORE'."""
        if tipo in {'ESC', 'RIGHTMOUSE'} and valor == 'PRESS':
            return 'CANCEL'

        if tipo == 'LEFTMOUSE':
            if valor == 'PRESS':
                self.armado = True
                self.anclas.append(pos)
                return 'DRAW'
            if valor == 'RELEASE':
                if not self.armado:
                    return 'IGNORE'  # el clic del botón que abrió la herramienta
                if self.shape == 'POLYGON':
                    return 'IGNORE'  # el polígono se cierra con Enter, no al soltar
                self.anclas.append(pos)
                return 'APPLY'
            return 'IGNORE'

        if tipo == 'MOUSEMOVE':
            if not self.armado or self.shape == 'POLYGON':
                return 'IGNORE'  # el polígono deja orbitar entre clic y clic
            if self.shape == 'LASSO':
                self.anclas.append(pos)
            elif len(self.anclas) > 1:
                self.anclas[-1] = pos  # las formas de dos anclas arrastran la segunda
            else:
                self.anclas.append(pos)
            return 'DRAW'

        if tipo in {'RET', 'NUMPAD_ENTER'} and valor == 'PRESS':
            return 'APPLY' if self.armado else 'IGNORE'

        return 'IGNORE'

    def preview(self):
        """Lo que se dibuja mientras trazás. El lazo y el polígono muestran sus
        anclas crudas: pasarlas por el Douglas-Peucker en cada redibujado
        arrastraría el viewport, y de todas formas es lo que la mano dibujó."""
        if self.libre:
            return list(self.anclas)
        return shape_points(self.shape, self.anclas, self.width, self.height)

    def contour(self):
        """El contorno definitivo, ya simplificado, que va al cortador"""
        return shape_points(self.shape, self.anclas, self.width, self.height)

    def reset(self):
        self.anclas = []
        self.armado = False


# --- modal: captura el gesto en pantalla (requiere viewport) ---------------

def _draw_overlay(op):
    """Contorno en curso y aviso de que la herramienta está esperando un trazo.
    Imports locales: en headless no hay contexto de GPU, pero el resto del
    módulo sí se testea."""
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader

    nombre = dict((i, n) for i, n, _, _ in SHAPES).get(op.shape, op.shape)
    accion = "Recortar" if op.action == 'TRIM' else "Partir"
    blf.size(0, 15)
    blf.position(0, 20, 45, 0)
    blf.color(0, 1.0, 0.6, 0.2, 1.0)
    blf.draw(0, f"{accion} · {nombre} — dibuja sobre la pieza · Esc para salir")

    puntos = op.estado.preview()
    if len(puntos) < 2:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.line_width_set(2.0)
    gpu.state.blend_set('ALPHA')
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": puntos})
    shader.uniform_float("color", (1.0, 0.35, 0.2, 0.95))  # naranja, como el plano de corte
    batch.draw(shader)
    gpu.state.blend_set('NONE')
    gpu.state.line_width_set(1.0)


class SIRO_OT_shape_cut(bpy.types.Operator):
    """Corta la pieza activa dibujando una forma sobre el viewport.
Arrastra para dibujar (en Polígono, un clic por vértice y Enter para cerrar).
Escape o clic derecho cancela sin tocar la pieza"""
    bl_idname = "siro.shape_cut"
    bl_label = "Cortar con forma"
    bl_options = {'REGISTER', 'UNDO'}

    shape: bpy.props.EnumProperty(
        name="Forma",
        items=[(i, n, d, ic, k) for k, (i, n, d, ic) in enumerate(SHAPES)],
        default='LASSO',
    )
    action: bpy.props.EnumProperty(
        name="Acción",
        items=(
            ('TRIM', "Recortar", "Deja una sola pieza"),
            ('SPLIT', "Partir", "Deja las dos partes como piezas separadas y selladas"),
        ),
        default='TRIM',
    )
    keep: bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('IN', "Interior", "Lo que quedó dentro de la forma dibujada"),
            ('OUT', "Exterior", "Lo que quedó fuera de la forma dibujada"),
        ),
        default='OUT',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            self.report({'ERROR'}, "Pon el cursor sobre el viewport 3D antes de cortar")
            return {'CANCELLED'}
        # La vista se captura ACÁ y resolviendo la región WINDOW a mano. Si se
        # confía en context.region/region_data, un botón del N-panel entrega la
        # región UI, donde region_data es None: es exactamente lo que hacía el
        # corte libre viejo, que caía a un fallback de vista superior y cortaba
        # a 90° de lo que se estaba dibujando.
        self._region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        self._rv3d = context.area.spaces.active.region_3d
        if self._region is None or self._rv3d is None:
            self.report({'ERROR'}, "No encuentro la vista 3D")
            return {'CANCELLED'}

        self.estado = StrokeState(self.shape, self._region.width, self._region.height)
        self._cortes = 0  # >0 al salir significa FINISHED, para que el undo agrupe bien
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (self,), 'WINDOW', 'POST_PIXEL'
        )
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(
            "Dibuja la forma · Enter confirma (Polígono) · Escape o clic derecho sale"
        )
        return {'RUNNING_MODAL'}

    def _limpiar(self, context):
        if self._handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        self._region.tag_redraw()

    def modal(self, context, event):
        # traductor delgado: toda la lógica del gesto vive en StrokeState, que
        # sí se puede testear sin viewport
        pos = (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
        accion = self.estado.event(event.type, event.value, pos)

        if accion == 'CANCEL':
            self._limpiar(context)
            return {'FINISHED' if self._cortes else 'CANCELLED'}
        if accion == 'DRAW':
            self._region.tag_redraw()
            return {'RUNNING_MODAL'}
        if accion == 'APPLY':
            self._aplicar(context)
            # la herramienta sigue armada para el corte siguiente, como Nomad
            self.estado.reset()
            self._region.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'} if self.estado.armado else {'PASS_THROUGH'}

    def _aplicar(self, context):
        from bpy_extras import view3d_utils

        puntos = self.estado.contour()
        if len(puntos) < 3:
            self.report({'WARNING'}, "Forma vacía — no se cortó nada")
            return

        # se relee la pieza activa en cada corte: tras un Partir cambia
        target = context.active_object
        if target is None or target.type != 'MESH':
            self.report({'WARNING'}, "No hay pieza activa que cortar")
            return

        rays = [
            (
                view3d_utils.region_2d_to_origin_3d(self._region, self._rv3d, p),
                view3d_utils.region_2d_to_vector_3d(self._region, self._rv3d, p),
            )
            for p in puntos
        ]
        try:
            resultado = apply_shape_cut(context, target, rays, self.action, self.keep)
        except RuntimeError as err:
            self.report({'ERROR'}, f"No se pudo cortar: {err}")
            return
        if resultado is None:
            self.report({'ERROR'}, "Forma inválida — vuelve a dibujarla sin cruzar la línea")
            return
        self._cortes += 1
        verbo = "Partida en 2" if self.action == 'SPLIT' else "Recortada"
        # Un paso de deshacer POR CORTE. Blender empuja el suyo cuando el
        # operador termina, y este sigue armado para encadenar cortes: sin esto,
        # los cortes hechos durante el modal quedaban fuera del stack y el
        # Ctrl+Z se comía el paso anterior en vez del corte.
        bpy.ops.ed.undo_push(message=f"{verbo} con forma")
        if not target.data.vertices:
            self.report({'WARNING'}, "El corte dejó la pieza vacía — ¿la forma quedó fuera de la pieza?")
        else:
            self.report({'INFO'}, f"{verbo} con {len(puntos)} puntos de contorno")
