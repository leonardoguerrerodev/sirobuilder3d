import bmesh
import bpy

from .boolean_ops import _apply_pending_modifiers, _make_single_user

# Cuánto puede encoger la pieza antes de que valga avisar. No es un tope sobre el
# conteo de caras —la cantidad de polígonos nunca fue la variable—: es la
# deformación real. Medido al ratio 0.5, la pérdida depende de la densidad y no
# del tamaño: 63 % con 12 triángulos, 16 % con 48, 3,7 % con 192, 0,7 % con 768 y
# 0,1 % con 3072. Abajo de unos 200 triángulos el Decimate no tiene margen y
# devuelve otra cosa con cara de éxito.
DEFORMACION_AVISO = 0.05


def _tri_count(obj):
    """Decimate Collapse trabaja en triángulos: contar caras engaña (150 quads
    = 300 tris; al ratio 0.5 quedan 150 tris y parece que no redujo nada)"""
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def _volumen(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol


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
        vol_antes = _volumen(obj)
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
            return {'FINISHED'}

        # bajar el conteo no es haber salido bien: en mallas de pocas caras el
        # Decimate reduce igual y se lleva la forma puesta, y el mensaje viejo
        # ("Triángulos: 12 → 6") lo daba por éxito
        deformacion = abs(_volumen(obj) - vol_antes) / abs(vol_antes) if vol_antes else 0.0
        if deformacion > DEFORMACION_AVISO:
            self.report(
                {'WARNING'},
                f"Triángulos: {before} → {after}, pero la pieza cambió {deformacion * 100:.0f}% "
                "de volumen: quedaba poca malla para reducir. Deshaz (Ctrl+Z) y prueba una "
                "proporción más alta",
            )
        else:
            self.report({'INFO'}, f"Triángulos: {before} → {after}")
        return {'FINISHED'}
