import bmesh
import bpy


def _nonmanifold_edges(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return count


class SIRO_OT_repair(bpy.types.Operator):
    """Repara la malla: borra geometría suelta y degenerada, suelda vértices, tapa agujeros y corrige normales"""
    bl_idname = "siro.repair"
    bl_label = "Reparar malla"
    bl_options = {'REGISTER', 'UNDO'}

    merge_distance: bpy.props.FloatProperty(
        name="Distancia de soldado",
        description="Vértices más cercanos que esto se fusionan",
        default=0.0001,
        min=0.0,
        precision=5,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        before = _nonmanifold_edges(obj)

        bpy.ops.object.mode_set(mode='EDIT')
        for op in (
            lambda: bpy.ops.mesh.delete_loose(),
            lambda: bpy.ops.mesh.dissolve_degenerate(),
            lambda: bpy.ops.mesh.remove_doubles(threshold=self.merge_distance),
            lambda: bpy.ops.mesh.fill_holes(sides=0),
            lambda: bpy.ops.mesh.normals_make_consistent(inside=False),
        ):
            bpy.ops.mesh.select_all(action='SELECT')
            op()
        bpy.ops.object.mode_set(mode='OBJECT')

        after = _nonmanifold_edges(obj)
        self.report({'INFO'}, f"Aristas no-manifold: {before} → {after}")
        return {'FINISHED'}
