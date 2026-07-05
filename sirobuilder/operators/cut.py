import bmesh
import bpy
from mathutils import Vector

CUTTER_NAME = "SiroCutter"


def get_cutter(context):
    return context.scene.objects.get(CUTTER_NAME)


def _cutter_material():
    """Naranja translúcido, visible en Solid y Material Preview"""
    mat = bpy.data.materials.get(CUTTER_NAME)
    if mat is None:
        mat = bpy.data.materials.new(CUTTER_NAME)
        mat.diffuse_color = (1.0, 0.4, 0.1, 0.35)  # color de viewport en modo Solid
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (1.0, 0.4, 0.1, 1.0)
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
        cutter["siro_target"] = target.name
        return {'FINISHED'}


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
        bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)  # tapa del corte
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
        default=6,
        min=0,
    )
    keep_cutter: bpy.props.BoolProperty(
        name="Conservar plano de corte",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return get_cutter(context) is not None

    def execute(self, context):
        cutter = get_cutter(context)
        target = context.scene.objects.get(cutter.get("siro_target", ""))
        if target is None or target.type != 'MESH':
            self.report({'ERROR'}, "No encuentro la pieza a cortar; vuelve a añadir el plano")
            return {'CANCELLED'}

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
