import bmesh
import bpy
from mathutils import Vector

from .cut import CONTOUR_NAME

PRISM_NAME = "SiroPrisma"


class SIRO_OT_draw_contour(bpy.types.Operator):
    """Paso 1: dibuja el trazo de corte sobre la pieza a mano alzada (mantén presionado el botón izquierdo).
Una línea de lado a lado actúa como cuchillo; un contorno cerrado recorta la silueta.
Cuando termines, pulsa Recortar con trazo"""
    bl_idname = "siro.draw_contour"
    bl_label = "Dibujar trazo de corte"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        target = context.active_object
        old = context.scene.objects.get(CONTOUR_NAME)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)

        data = bpy.data.curves.new(CONTOUR_NAME, 'CURVE')
        data.dimensions = '3D'
        curve = bpy.data.objects.new(CONTOUR_NAME, data)
        context.collection.objects.link(curve)
        curve["siro_target"] = target.name

        bpy.ops.object.select_all(action='DESELECT')
        curve.select_set(True)
        context.view_layer.objects.active = curve
        bpy.ops.object.mode_set(mode='EDIT')

        paint = context.scene.tool_settings.curve_paint_settings
        paint.depth_mode = 'SURFACE'  # el trazo se apoya sobre la pieza
        paint.curve_type = 'POLY'
        bpy.ops.wm.tool_set_by_id(name="builtin.draw")

        self.report({'INFO'}, "Dibuja el contorno sobre la pieza y pulsa Recortar con contorno")
        return {'FINISHED'}


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


def _stroke_points(contour):
    """Puntos del trazo en mundo, sin duplicados y simplificados (el trazo a mano
    alzada trae cientos de puntos; el boolean no necesita más de unas decenas)"""
    mw = contour.matrix_world
    pts = []
    for spline in contour.data.splines:
        if spline.type == 'BEZIER':
            pts += [mw @ p.co for p in spline.bezier_points]
        else:
            pts += [mw @ p.co.to_3d() for p in spline.points]
    clean = []
    for p in pts:
        if not clean or (p - clean[-1]).length > 1e-5:
            clean.append(p)
    if len(clean) > 1 and (clean[0] - clean[-1]).length < 1e-5:
        clean.pop()
    while len(clean) > 1000:  # tope antes del RDP, que es O(n²) en el peor caso
        clean = clean[::2]
    if len(clean) > 3:
        lo = Vector((min(p[i] for p in clean) for i in range(3)))
        hi = Vector((max(p[i] for p in clean) for i in range(3)))
        clean = _rdp(clean, (hi - lo).length * 0.005)
    return clean


def _flatten(points, view_dir):
    """Proyecta los puntos al plano perpendicular a la vista"""
    center = Vector()
    for p in points:
        center += p
    center /= len(points)
    return [p - view_dir * (p - center).dot(view_dir) for p in points]


def _is_closed(points):
    """Trazo cerrado = termina cerca de donde empezó (contorno); si no, es una línea-cuchillo"""
    lo = Vector((min(p[i] for p in points) for i in range(3)))
    hi = Vector((max(p[i] for p in points) for i in range(3)))
    return (points[0] - points[-1]).length < 0.15 * (hi - lo).length


def _close_knife(flat, view_dir, reach):
    """Convierte la línea abierta en un polígono cerrado: extiende ambos extremos
    más allá de la pieza y cierra por un costado, lejos — el borde que toca la
    pieza es solo la línea dibujada, como un cuchillo"""
    d0 = (flat[0] - flat[1]).normalized()
    d1 = (flat[-1] - flat[-2]).normalized()
    ext0 = flat[0] + d0 * reach
    ext1 = flat[-1] + d1 * reach
    side = (flat[-1] - flat[0]).cross(view_dir)
    if side.length < 1e-9:
        return None  # trazo degenerado (empieza y termina en el mismo punto de vista)
    side.normalize()
    return [ext0] + flat + [ext1, ext1 + side * reach, ext0 + side * reach]


def _make_prism(context, flat, view_dir, depth):
    """Polígono (ya plano según la vista) extruido: el cortador del boolean"""
    bm = bmesh.new()
    verts = [bm.verts.new(p - view_dir * depth) for p in flat]
    face = bm.faces.new(verts)  # ValueError si el trazo es degenerado
    extruded = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [v for v in extruded['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=view_dir * (2.0 * depth))
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:  # tapas trianguladas: los booleans digieren mal ngons cóncavos gigantes
        bmesh.ops.triangulate(bm, faces=ngons)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(PRISM_NAME)
    bm.to_mesh(mesh)
    bm.free()
    prism = bpy.data.objects.new(PRISM_NAME, mesh)
    context.collection.objects.link(prism)
    return prism


def _apply_bool(context, obj, prism, operation, solver):
    mod = obj.modifiers.new("SiroBool", 'BOOLEAN')
    mod.object = prism
    mod.operation = operation
    mod.solver = solver
    context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


class SIRO_OT_free_cut(bpy.types.Operator):
    """Paso 2: corta la pieza con el trazo dibujado, proyectado desde la vista actual.
Línea abierta = cuchillo que parte el modelo entero; trazo cerrado = recorte del contorno.
Resultado sellado y manifold, igual que el corte con plano"""
    bl_idname = "siro.free_cut"
    bl_label = "Recortar con trazo"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('BOTH', "Ambas partes", "Divide en dos objetos separados, ambos sellados"),
            ('A', "Un lado (interior)", "Con contorno cerrado: el interior de la silueta"),
            ('B', "El otro lado (exterior)", "Con contorno cerrado: el exterior de la silueta"),
        ),
        default='BOTH',
    )
    solver: bpy.props.EnumProperty(
        name="Calidad",
        items=(
            ('FLOAT', "Rápida", "Solver liviano — el indicado para mallas densas como los relieves"),
            ('EXACT', "Exacta", "Más lento; úsalo solo si el corte rápido deja artefactos"),
        ),
        default='FLOAT',
    )

    @classmethod
    def poll(cls, context):
        return (
            context.scene.objects.get(CONTOUR_NAME) is not None
            or (context.active_object is not None and context.active_object.type == 'MESH')
        )

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        contour = context.scene.objects.get(CONTOUR_NAME)
        if contour is not None:
            target = context.scene.objects.get(contour.get("siro_target", ""))
            if target is None or target.type != 'MESH':
                self.report({'ERROR'}, "No encuentro la pieza — vuelve a Dibujar contorno con la pieza activa")
                return {'CANCELLED'}
        else:
            # sin contorno dibujado: sirve cualquier curva seleccionada junto a la pieza activa
            target = context.active_object
            others = [o for o in context.selected_objects if o is not target]
            if len(others) != 1 or others[0].type != 'CURVE':
                self.report({'ERROR'}, "Primero pulsa Dibujar contorno (o selecciona una curva + la pieza)")
                return {'CANCELLED'}
            contour = others[0]

        points = _stroke_points(contour)
        if len(points) < 3:
            self.report({'ERROR'}, "El contorno está vacío — pulsa Dibujar contorno y traza sobre la pieza")
            return {'CANCELLED'}

        rv3d = context.region_data
        view_dir = (
            (rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()
            if rv3d is not None else Vector((0.0, 0.0, -1.0))  # sin viewport: vista superior
        )
        depth = max(*target.dimensions, 1.0) * 3.0

        flat = _flatten(points, view_dir)
        if not _is_closed(flat):
            flat = _close_knife(flat, view_dir, depth * 2.0)
            if flat is None:
                self.report({'ERROR'}, "Trazo degenerado — dibuja la línea de lado a lado de la pieza")
                return {'CANCELLED'}
        try:
            prism = _make_prism(context, flat, view_dir, depth)
        except ValueError:
            self.report({'ERROR'}, "Trazo inválido — dibújalo de nuevo sin cruzar la línea sobre sí misma")
            return {'CANCELLED'}

        if self.mode == 'BOTH':
            other = target.copy()
            other.data = target.data.copy()
            for coll in target.users_collection:
                coll.objects.link(other)
            _apply_bool(context, other, prism, 'DIFFERENCE', self.solver)
            _apply_bool(context, target, prism, 'INTERSECT', self.solver)
        else:
            op = 'INTERSECT' if self.mode == 'A' else 'DIFFERENCE'
            _apply_bool(context, target, prism, op, self.solver)
        self.report({'INFO'}, f"Corte con {len(points)} puntos de trazo")

        prism_data = prism.data
        bpy.data.objects.remove(prism, do_unlink=True)
        bpy.data.meshes.remove(prism_data)
        if contour.name.startswith(CONTOUR_NAME):
            contour_data = contour.data
            bpy.data.objects.remove(contour, do_unlink=True)
            if not contour_data.users:
                bpy.data.curves.remove(contour_data)

        if not target.data.vertices:
            self.report({'WARNING'}, "El corte dejó la pieza vacía — ¿el contorno quedó fuera de la pieza?")
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        context.view_layer.objects.active = target
        return {'FINISHED'}
