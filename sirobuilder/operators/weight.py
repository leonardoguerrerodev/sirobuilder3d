"""Peso de la pieza en plata: el volumen de la malla por la densidad de la aleación.

El anillo vivo ya muestra su peso en el panel —lo calcula `construir()` de paso—,
pero deja de hacerlo al aplicarlo a malla, que es justo cuando la pieza está
terminada: después de los cortes, los booleans y las fusiones. Esto lo mide sobre
cualquier malla cerrada.

Cerrada es la palabra: el volumen de una malla abierta no significa nada, así que
ahí no se inventa un número, se avisa.
"""

import bpy

from .boolean_ops import _open_edge_count
from .ring import DENSIDAD_PLATA_950
from .simplify import _volumen


def _mm3(obj):
    """Volumen en mm³ contando la escala del objeto.

    `calc_volume` mide la malla LOCAL: con el objeto escalado el peso real no es
    ése. El determinante de la matriz de mundo es el factor de escala al cubo, que
    es justo lo que hay que multiplicar.
    """
    return abs(_volumen(obj)) * abs(obj.matrix_world.determinant())


class SIRO_OT_weight(bpy.types.Operator):
    """Mide el volumen de las piezas seleccionadas y lo pasa a gramos de plata 950"""
    bl_idname = "siro.weight"
    bl_label = "Peso"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        piezas = [o for o in context.selected_objects if o.type == 'MESH']
        if not piezas:
            piezas = [context.active_object]

        abiertas = [o.name for o in piezas if _open_edge_count(o)]
        if abiertas:
            self.report({'WARNING'}, f"{', '.join(abiertas[:3])}: malla abierta. El volumen "
                                     f"de una malla abierta no significa nada — pasa Reparar malla")
            return {'CANCELLED'}

        vol = sum(_mm3(o) for o in piezas)
        cuantas = f"{len(piezas)} piezas: " if len(piezas) > 1 else ""
        self.report({'INFO'}, f"{cuantas}{vol:.0f} mm³ ({vol / 1000.0:.2f} cm³) · "
                              f"{vol * DENSIDAD_PLATA_950:.2f} g en plata 950")
        return {'FINISHED'}
