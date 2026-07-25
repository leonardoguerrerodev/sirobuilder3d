import bmesh
import bpy
from mathutils import Matrix, Vector

from .boolean_ops import _make_single_user


class SIRO_OT_mirror(bpy.types.Operator):
    """Refleja la pieza sobre el eje elegido: la voltea en su lugar, sin duplicarla ni moverla"""
    bl_idname = "siro.mirror"
    bl_label = "Espejo"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(
        name="Eje",
        items=(('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")),
        default='X',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        _make_single_user(obj)

        # reflejar alrededor del centro del bounding box, no del origen: si el
        # origen está descentrado la pieza saltaría de lugar al voltearse
        centro = sum((Vector(c) for c in obj.bound_box), Vector()) / 8
        escala = [1.0, 1.0, 1.0]
        escala['XYZ'.index(self.axis)] = -1.0
        obj.data.transform(
            Matrix.Translation(centro)
            @ Matrix.Diagonal(escala).to_4x4()
            @ Matrix.Translation(-centro)
        )

        # una reflexión invierte el orden de los vértices de cada cara: sin esto
        # la pieza queda del revés (normales hacia adentro, no imprimible)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {'FINISHED'}
