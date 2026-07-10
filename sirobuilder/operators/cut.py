import bmesh
import bpy
from mathutils import Vector

from . import ghost_preview

CUTTER_NAME = "SiroCutter"
CONTOUR_NAME = "SiroContorno"
# nombres de la versión anterior (preview con boolean en vivo), solo para limpieza
_LEGACY_VOL_NAME = "SiroCutterVol"
_LEGACY_GHOST_NAME = "SiroGhost"
_LEGACY_PREVIEW_MOD = "SiroPreview"


def get_cutter(context):
    return context.scene.objects.get(CUTTER_NAME)


def remove_preview(context):
    """Limpia la vista previa fantasma actual (Geometry Nodes, ver
    ghost_preview.py) y restos del preview con boolean en vivo de versiones
    aún más antiguas del addon (ya no se usa)"""
    ghost_preview.remove_all_ghost_previews(context)
    for name in (_LEGACY_GHOST_NAME, _LEGACY_VOL_NAME):
        obj = context.scene.objects.get(name)
        if obj is not None:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if name == _LEGACY_VOL_NAME and data is not None and not data.users:
                bpy.data.meshes.remove(data)
    for obj in context.scene.objects:
        mod = obj.modifiers.get(_LEGACY_PREVIEW_MOD)
        if mod is not None:
            obj.modifiers.remove(mod)


def _cutter_material():
    """Verde translúcido, visible en Solid y Material Preview (estilo 3D Builder)"""
    mat = bpy.data.materials.get(CUTTER_NAME)
    if mat is None:
        mat = bpy.data.materials.new(CUTTER_NAME)
        mat.diffuse_color = (0.2, 0.9, 0.3, 0.35)  # color de viewport en modo Solid
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (0.2, 0.9, 0.3, 1.0)
            bsdf.inputs["Alpha"].default_value = 0.35
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = 'BLENDED'
    return mat


class SIRO_OT_add_cut_plane(bpy.types.Operator):
    """Añade el plano de corte sobre la pieza activa; muévelo/rótalo (G/R) y pulsa Cortar"""
    bl_idname = "siro.add_cut_plane"
    bl_label = "Añadir plano de corte"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.name != CUTTER_NAME

    def execute(self, context):
        target = context.active_object
        remove_preview(context)  # limpia restos de versiones anteriores, si los hay
        old = get_cutter(context)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)

        size = max(target.dimensions) * 1.5 or 1.0
        bpy.ops.mesh.primitive_plane_add(
            size=size, location=target.matrix_world.translation
        )
        cutter = context.active_object
        cutter.name = CUTTER_NAME
        cutter.show_in_front = True
        cutter.data.materials.append(_cutter_material())
        cutter.color = (0.2, 0.9, 0.3, 0.5)
        cutter["siro_target"] = target.name

        ghost_preview.add_ghost_modifier(target, cutter)

        # dejar el plano activo y seleccionado, listo para moverlo con G/R
        bpy.ops.object.select_all(action='DESELECT')
        cutter.select_set(True)
        context.view_layer.objects.active = cutter
        return {'FINISHED'}


def _loop_basis(normal):
    """Dos vectores ortogonales a `normal`, para proyectar el corte a 2D."""
    n = normal.normalized()
    helper = Vector((0.0, 1.0, 0.0)) if abs(n.x) > 0.9 else Vector((1.0, 0.0, 0.0))
    u = (helper - helper.dot(n) * n).normalized()
    v = n.cross(u)
    return u, v


def _walk_cut_loops(cut_edges):
    """Agrupa los edges de corte (todos coplanares, salen de bisect_plane) en
    contornos cerrados individuales, caminando vértice a vértice. Un corte
    puede dejar más de un contorno: p. ej. el agujero de un toro cortado por
    el medio genera un contorno exterior y uno interior por separado."""
    remaining = set(cut_edges)
    loops = []
    while remaining:
        e0 = next(iter(remaining))
        loop_edges = []
        loop_verts = []
        start_v = e0.verts[0]
        prev_v = start_v
        cur_e = e0
        safety = len(cut_edges) + 1
        while safety > 0:
            safety -= 1
            remaining.discard(cur_e)
            loop_edges.append(cur_e)
            loop_verts.append(prev_v)
            other_v = cur_e.other_vert(prev_v)
            if other_v == start_v:
                break
            next_e = next((ce for ce in other_v.link_edges if ce in remaining), None)
            if next_e is None:
                break  # contorno irregular/abierto (malla no-manifold); se deja tal cual
            prev_v, cur_e = other_v, next_e
        loops.append((loop_edges, loop_verts))
    return loops


def _point_in_poly_2d(pt, poly):
    """Ray casting par/impar, para saber si `pt` está dentro del polígono 2D `poly`."""
    inside = False
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > pt.y) != (by > pt.y):
            x_int = ax + (pt.y - ay) * (bx - ax) / (by - ay)
            if pt.x < x_int:
                inside = not inside
    return inside


def _group_cut_loops(cut_edges, plane_co, plane_no):
    """Agrupa los contornos de corte según su anidamiento 2D en el plano de
    corte: un contorno adentro de otro (p. ej. el borde del agujero de un
    toro adentro del borde exterior) va al MISMO grupo, para que el tapado
    respete el hueco en vez de taparlo con una superficie sólida. Contornos
    que no están anidados entre sí (piezas separadas al mismo alto) quedan en
    grupos distintos, para no puentearlos con una cara falsa entre medio."""
    loops = _walk_cut_loops(cut_edges)
    if len(loops) <= 1:
        return [cut_edges]

    u, v = _loop_basis(plane_no)
    polys_2d = []
    for _edges, verts in loops:
        polys_2d.append([Vector(((w.co - plane_co).dot(u), (w.co - plane_co).dot(v))) for w in verts])

    n = len(loops)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        if len(polys_2d[i]) < 1:
            continue
        test_pt = polys_2d[i][0]
        for j in range(n):
            if i == j or len(polys_2d[j]) < 3:
                continue
            if _point_in_poly_2d(test_pt, polys_2d[j]):
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    grouped_edges = []
    for idxs in groups.values():
        edges = []
        for i in idxs:
            edges.extend(loops[i][0])
        grouped_edges.append(edges)
    return grouped_edges


def _cut_mesh(me, plane_co, plane_no, max_hole_sides):
    """Corta la malla in place conservando el lado hacia plane_no; tapa y sella.
    Devuelve False (sin tocar la malla) si el corte la dejaría vacía."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    result = bmesh.ops.bisect_plane(
        bm,
        geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
        plane_co=plane_co,
        plane_no=plane_no,
        clear_inner=True,   # descarta el lado contrario a la normal
        clear_outer=False,
    )
    if not bm.verts:
        bm.free()
        return False
    cut_edges = [e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
    if cut_edges:
        # tapa por grupos de contornos anidados: respeta huecos (agujero de un
        # toro) y no puentea piezas separadas con una cara falsa entre ellas
        for group_edges in _group_cut_loops(cut_edges, plane_co, plane_no):
            if group_edges:
                bmesh.ops.triangle_fill(bm, edges=group_edges, normal=plane_no)
    if max_hole_sides:
        bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=max_hole_sides)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return True


class SIRO_OT_cut(bpy.types.Operator):
    """Corta con el plano: conserva arriba (normal), abajo o ambas partes; tapa el corte y sella micro-agujeros"""
    bl_idname = "siro.cut"
    bl_label = "Cortar"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('FRONT', "Arriba (lado de la normal)", "La parte hacia donde apunta la normal del plano"),
            ('BACK', "Abajo (lado opuesto)", "La parte contraria a la normal del plano"),
            ('BOTH', "Ambas partes", "Divide en dos objetos separados, ambos sellados"),
        ),
        default='FRONT',
    )
    max_hole_sides: bpy.props.IntProperty(
        name="Máx. lados de micro-agujero",
        description="Sella agujeros de hasta este número de lados (0 = no sellar extra, protege huecos de diseño)",
        default=0,
        min=0,
    )
    keep_cutter: bpy.props.BoolProperty(
        name="Conservar plano de corte",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return get_cutter(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        cutter = get_cutter(context)
        target = context.scene.objects.get(cutter.get("siro_target", ""))
        if target is None or target.type != 'MESH':
            self.report({'ERROR'}, "No encuentro la pieza a cortar; vuelve a añadir el plano")
            return {'CANCELLED'}
        remove_preview(context)

        no_world = (cutter.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        # plano al espacio local de la pieza: punto con M^-1, normal con M^T
        co_local = target.matrix_world.inverted() @ cutter.matrix_world.translation
        no_local = (target.matrix_world.to_3x3().transposed() @ no_world).normalized()

        if self.side == 'BOTH':
            other = target.copy()
            other.data = target.data.copy()
            for coll in target.users_collection:
                coll.objects.link(other)
            ok_front = _cut_mesh(target.data, co_local, no_local, self.max_hole_sides)
            ok_back = _cut_mesh(other.data, co_local, -no_local, self.max_hole_sides)
            if not (ok_front and ok_back):
                other_data = other.data
                bpy.data.objects.remove(other, do_unlink=True)
                bpy.data.meshes.remove(other_data)
                self.report({'ERROR'}, "El plano no atraviesa la pieza — no hay nada que dividir")
                return {'CANCELLED'}
        else:
            if self.side == 'BACK':
                no_local = -no_local
            if not _cut_mesh(target.data, co_local, no_local, self.max_hole_sides):
                self.report({'ERROR'}, "El corte eliminó toda la malla — prueba conservando el otro lado")
                return {'CANCELLED'}

        if not self.keep_cutter:
            bpy.data.objects.remove(cutter, do_unlink=True)
        context.view_layer.objects.active = target
        target.select_set(True)
        return {'FINISHED'}


class SIRO_OT_cancel_cut(bpy.types.Operator):
    """Cancela el corte pendiente: quita el plano, el contorno y el preview sin cortar nada"""
    bl_idname = "siro.cancel_cut"
    bl_label = "Cancelar corte"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        remove_preview(context)
        for name in (CUTTER_NAME, CONTOUR_NAME):
            obj = context.scene.objects.get(name)
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
        return {'FINISHED'}
