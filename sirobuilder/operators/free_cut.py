import bmesh
import bpy
from mathutils import Vector

from .cut import CONTOUR_NAME

PRISM_NAME = "SiroPrisma"


class SIRO_OT_draw_contour(bpy.types.Operator):
    """Paso 1: dibuja a mano alzada el contorno de corte sobre la pieza (mantén presionado el botón izquierdo).
Cuando termines, pulsa Recortar con contorno"""
    bl_idname = "siro.draw_contour"
    bl_label = "Dibujar contorno"
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


def _stroke_points(contour):
    """Puntos del trazo en coordenadas de mundo, sin duplicados consecutivos"""
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
    return clean


def _make_prism(context, points, view_dir, depth):
    """Silueta del trazo aplanada según la vista y extruida: el cortador del boolean"""
    center = Vector()
    for p in points:
        center += p
    center /= len(points)
    flat = [p - view_dir * (p - center).dot(view_dir) for p in points]

    bm = bmesh.new()
    verts = [bm.verts.new(p - view_dir * depth) for p in flat]
    face = bm.faces.new(verts)  # ValueError si el trazo es degenerado
    extruded = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [v for v in extruded['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=view_dir * (2.0 * depth))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(PRISM_NAME)
    bm.to_mesh(mesh)
    bm.free()
    prism = bpy.data.objects.new(PRISM_NAME, mesh)
    context.collection.objects.link(prism)
    return prism


def _apply_bool(context, obj, prism, operation):
    mod = obj.modifiers.new("SiroBool", 'BOOLEAN')
    mod.object = prism
    mod.operation = operation
    mod.solver = 'EXACT'  # corte real: exactitud sobre velocidad
    context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


class SIRO_OT_free_cut(bpy.types.Operator):
    """Paso 2: corta la pieza con la silueta dibujada, proyectada desde la vista actual.
Igual que el corte con plano: resultado sellado y manifold"""
    bl_idname = "siro.free_cut"
    bl_label = "Recortar con contorno"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('INSIDE', "Interior del contorno", "Se queda lo de adentro de la silueta"),
            ('OUTSIDE', "Exterior del contorno", "Se queda lo de afuera de la silueta"),
            ('BOTH', "Ambas partes", "Divide en dos objetos separados, ambos sellados"),
        ),
        default='INSIDE',
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
        try:
            prism = _make_prism(context, points, view_dir, depth)
        except ValueError:
            self.report({'ERROR'}, "Contorno inválido — dibújalo de nuevo sin cruzar el trazo")
            return {'CANCELLED'}

        if self.mode == 'BOTH':
            other = target.copy()
            other.data = target.data.copy()
            for coll in target.users_collection:
                coll.objects.link(other)
            _apply_bool(context, other, prism, 'DIFFERENCE')
            _apply_bool(context, target, prism, 'INTERSECT')
        else:
            op = 'INTERSECT' if self.mode == 'INSIDE' else 'DIFFERENCE'
            _apply_bool(context, target, prism, op)

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
