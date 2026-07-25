import bpy

from .boolean_ops import _apply_pending_modifiers, _make_single_user


def _tri_count(obj):
    """Decimate Collapse trabaja en triángulos: contar caras engaña (150 quads
    = 300 tris; al ratio 0.5 quedan 150 tris y parece que no redujo nada)"""
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


class SIRO_OT_simplify(bpy.types.Operator):
    """Reduce la cantidad de polígonos preservando la forma (Decimate Collapse)"""
    bl_idname = "siro.simplify"
    bl_label = "Simplificar"
    bl_options = {'REGISTER', 'UNDO'}

    ratio: bpy.props.FloatProperty(
        name="Proporción",
        description="0.5 = deja la mitad de los polígonos",
        default=0.5,
        min=0.01,
        max=1.0,
        subtype='FACTOR',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        _make_single_user(obj)
        _apply_pending_modifiers(context, obj)
        before = _tri_count(obj)
        mod = obj.modifiers.new("SiroDecimate", 'DECIMATE')
        mod.ratio = self.ratio
        # Collapse no colapsa nada en mallas con ngons — justo lo que dejan los
        # booleans, que es cuando más falta hace simplificar. Solo se triangula
        # si hace falta: en malla de quads destruiría topología limpia a cambio de nada
        mod.use_collapse_triangulate = any(len(p.vertices) > 4 for p in obj.data.polygons)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        after = _tri_count(obj)
        if after >= before:
            self.report({'WARNING'}, f"No se pudo reducir ({before} triángulos) — prueba Reparar malla primero")
        else:
            self.report({'INFO'}, f"Triángulos: {before} → {after}")
        return {'FINISHED'}
