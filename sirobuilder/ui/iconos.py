"""Letras X / Y / Z en los colores de eje, como iconos propios.

Blender **no deja colorear el texto** de una etiqueta desde Python:
`UILayout.label()` solo acepta `text/icon/icon_value`, y lo único de `UILayout`
que tiñe es `alert`, que además es rojo y nada más. Lo que sí se puede es
registrar iconos propios pintando sus píxeles (`ImagePreview.icon_pixels_float`
es escribible), así que las letras van dibujadas a mano acá.

Los colores salen del **tema del usuario**, no de constantes: así concuerdan
exactamente con el gizmo de rotación del viewport, que es contra lo que Leo los
va a comparar, y siguen su tema si lo cambia.
"""

import bpy
import bpy.utils.previews

# 16×16, una fila por línea. Se escalan ×2 al cargarlas: a 16 píxeles las letras
# quedan borrosas en pantallas con factor de escala.
_GLIFOS = {
    'X': (
        "................",
        "................",
        "................",
        "...#..........#.",
        "...##........##.",
        "....##......##..",
        ".....##....##...",
        "......##..##....",
        ".......####.....",
        ".......####.....",
        "......##..##....",
        ".....##....##...",
        "....##......##..",
        "...##........##.",
        "...#..........#.",
        "................",
    ),
    'Y': (
        "................",
        "................",
        "................",
        "...#..........#.",
        "...##........##.",
        "....##......##..",
        ".....##....##...",
        "......##..##....",
        ".......####.....",
        "........##......",
        "........##......",
        "........##......",
        "........##......",
        "........##......",
        "........##......",
        "................",
    ),
    'Z': (
        "................",
        "................",
        "................",
        "...###########..",
        "...###########..",
        "...........##...",
        "..........##....",
        ".........##.....",
        "........##......",
        ".......##.......",
        "......##........",
        ".....##.........",
        "....##..........",
        "...###########..",
        "...###########..",
        "................",
    ),
}

_ESCALA = 2
_LADO = 16 * _ESCALA

# por si un tema no expone los colores de eje
_RESPALDO = {'X': (0.94, 0.30, 0.36), 'Y': (0.55, 0.87, 0.16), 'Z': (0.16, 0.45, 0.87)}

_coleccion = None


def _color_eje(letra):
    ui = bpy.context.preferences.themes[0].user_interface
    color = getattr(ui, f"axis_{letra.lower()}", None)
    return tuple(color[:3]) if color is not None else _RESPALDO[letra]


def _pixeles(letra):
    """RGBA de abajo hacia arriba, que es como los espera el preview"""
    r, g, b = _color_eje(letra)
    filas = _GLIFOS[letra]
    datos = []
    for y in range(_LADO):
        fila = filas[len(filas) - 1 - y // _ESCALA]  # invertido: origen abajo
        for x in range(_LADO):
            if fila[x // _ESCALA] == '#':
                datos += [r, g, b, 1.0]
            else:
                datos += [0.0, 0.0, 0.0, 0.0]
    return datos


def icono(letra):
    """`icon_value` de la letra pedida, o 0 (sin icono) si no se cargaron"""
    if _coleccion is None:
        return 0
    return _coleccion[letra].icon_id


def register():
    global _coleccion
    if _coleccion is not None:
        unregister()
    _coleccion = bpy.utils.previews.new()
    for letra in _GLIFOS:
        prev = _coleccion.new(letra)
        prev.icon_size = (_LADO, _LADO)
        prev.icon_pixels_float = _pixeles(letra)


def unregister():
    global _coleccion
    if _coleccion is not None:
        bpy.utils.previews.remove(_coleccion)
        _coleccion = None
