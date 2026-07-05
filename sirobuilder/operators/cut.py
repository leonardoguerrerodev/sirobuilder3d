import bmesh
import bpy
from mathutils import Vector

CUTTER_NAME = "SiroCutter"


def get_cutter(context):
    return context.scene.objects.get(CUTTER_NAME)


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
        cutter.display_type = 'WIRE'
        cutter.show_in_front = True
        cutter["siro_target"] = target.name
        return {'FINISHED'}


class SIRO_OT_cut(bpy.types.Operator):
    """Corta con el plano: conserva el lado hacia donde apunta la normal, tapa el corte y sella micro-agujeros"""
    bl_idname = "siro.cut"
    bl_label = "Cortar"
    bl_options = {'REGISTER', 'UNDO'}

    invert: bpy.props.BoolProperty(
        name="Invertir lado",
        description="Conservar el lado contrario a la normal del plano",
        default=False,
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
        if self.invert:
            no_world = -no_world
        # plano al espacio local de la pieza: punto con M^-1, normal con M^T
        co_local = target.matrix_world.inverted() @ cutter.matrix_world.translation
        no_local = (target.matrix_world.to_3x3().transposed() @ no_world).normalized()

        bm = bmesh.new()
        bm.from_mesh(target.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        result = bmesh.ops.bisect_plane(
            bm,
            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=co_local,
            plane_no=no_local,
            clear_inner=True,   # descarta el lado contrario a la normal
            clear_outer=False,
        )
        if not bm.verts:
            bm.free()
            self.report({'ERROR'}, "El corte eliminó toda la malla — prueba con Invertir lado")
            return {'CANCELLED'}

        cut_edges = [e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
        if cut_edges:
            bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)  # tapa del corte
        if self.max_hole_sides:
            bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=self.max_hole_sides)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        bm.to_mesh(target.data)
        bm.free()
        target.data.update()

        if not self.keep_cutter:
            bpy.data.objects.remove(cutter, do_unlink=True)
        context.view_layer.objects.active = target
        target.select_set(True)
        return {'FINISHED'}
