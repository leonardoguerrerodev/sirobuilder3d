"""Relieve desde depthmap: producir el mapa de alturas y convertirlo en malla.

Tres piezas, en el orden en que se usan:

- **Preparar depthmap** — una imagen a color no tiene profundidad adentro. Se
  fabrica: silueta (alpha) + domo por distancia al borde + luminancia como
  detalle. Para fotos o dibujos ajenos.
- **Relieve desde pieza 3D** — profundidad **real**, medida sobre una malla con
  la misma proyección ortográfica que usa el relleno (`extrude_down`).
- **Nuevo relieve desde imagen / Aplicar relieve** — lo que ya existía: grid con
  Displace, y de ahí a malla sólida fusionable.
"""

import bmesh
import bpy
import numpy as np
from bpy_extras.io_utils import ImportHelper

from . import extrude_down

DISP_MOD = "SiroRelieve"
# densidad calcada de depth_maps.blend (malla horneada de 607×607 verts, sin
# Subsurf): un Subsurf nivel 9 en vivo + Displace encima obliga a Blender a
# recalcular ~262k caras por CPU en cada evaluación (Displace después de
# Subsurf desactiva el subdivision rápido por GPU). Hornear la densidad una
# sola vez al crear el plano es lo que hace fluido a depth_maps.blend.
GRID_RES = 607

# Lado máximo del depthmap que generamos. No es un tope puesto por síntoma: el
# grid del relieve tiene GRID_RES vértices por lado, así que la resolución que
# sobre de ahí no llega nunca a la malla. Medido: el distance transform tarda
# 0,55 s a 768² en el peor caso, y el Shrinkwrap 0,06 s a 512².
RES_DEPTH = 768


def crear_relieve(context, img, escala=2.5):
    """Plano con el Displace puesto, listo para tocar Suavizado y Profundidad.

    `escala` es el semiancho en mm (el plano nace de tamaño 2, o sea local -1..1),
    así que el default de 2.5 da los 5 mm de ancho de siempre. El bake desde 3D
    pasa el semiancho real de la pieza para que el relieve salga a tamaño.
    """
    # tamaño base 2 (local -1..1): con coords LOCAL la imagen mapea el plano completo,
    # igual que en depth_maps.blend; el tamaño real se da con la escala del objeto.
    # Grid ya horneado a la densidad final (nada de Subsurf en vivo) — ver GRID_RES arriba.
    # x/y_subdivisions son cortes, no vértices: -1 para dar GRID_RES vértices por lado
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=GRID_RES - 1, y_subdivisions=GRID_RES - 1, size=2.0
    )
    obj = context.active_object
    obj.name = "Relieve"
    # proporción real de la imagen cargada — nunca hardcodeada (a diferencia
    # del .blend de referencia, que sí la tiene fija)
    aspect = img.size[1] / img.size[0] if img.size[0] and img.size[1] else 1.0
    obj.scale = (escala, escala * aspect, 1.0)

    # valores calcados de depth_maps.blend (referencia de Leo)
    tex = bpy.data.textures.new(img.name, 'IMAGE')
    tex.image = img
    tex.extension = 'CLIP'
    tex.filter_size = 6.22  # "Suavizado"

    disp = obj.modifiers.new(DISP_MOD, 'DISPLACE')
    disp.texture = tex
    disp.texture_coords = 'LOCAL'
    disp.mid_level = 0.5
    disp.strength = 1.0
    return obj


# --- producir el depthmap ---------------------------------------------------


def leer_pixeles(img):
    """Píxeles de `img` como (alto, ancho, canales) en float32"""
    w, h = img.size
    buf = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(buf)
    return buf.reshape(h, w, img.channels)


def escribir_depth(nombre, alto, fuente=None):
    """Guarda `alto` (h, w) en 0–1 como imagen y devuelve el datablock.

    Va en **float y Non-Color** a propósito: los valores que escribimos SON la
    altura que va a desplazar la malla. Leerlos de vuelta como sRGB los pasaría
    por una gamma que nadie pidió, y en 8 bits el relieve sale escalonado.
    (La imagen que carga el usuario sigue en sRGB: eso es dato ajeno, esto es
    dato nuestro.)
    """
    h, w = alto.shape
    img = bpy.data.images.get(nombre)
    if img is not None and tuple(img.size) != (w, h):
        bpy.data.images.remove(img)  # cambió el tamaño: no se puede reusar el buffer
        img = None
    if img is None:
        img = bpy.data.images.new(nombre, w, h, alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'

    buf = np.empty((h, w, 4), np.float32)
    buf[..., :3] = alto[..., None]
    buf[..., 3] = 1.0
    img.pixels.foreach_set(buf.ravel())
    img.update()
    if fuente is not None:
        # de dónde salió: preparar de nuevo siempre parte del original, así
        # apretar el botón dos veces no compone efectos
        img["siro_source"] = fuente
    return img


def distancia_al_borde(mask):
    """Para cada píxel de la máscara, cuánto le falta para salirse de ella.

    Pila de erosiones alternando vecindad 4 y 8: a 4 vecinos la distancia sale
    en rombo y a 8 en cuadrado, y alternando queda octogonal, que es lo más
    parecido a la euclidiana sin traer scipy (Blender no lo trae). Corta sola
    cuando la máscara se vacía — no hay tope de vueltas inventado.
    """
    d = np.zeros(mask.shape, np.float32)
    m = mask
    vuelta = 0
    while m.any():
        d += m
        p = np.zeros((m.shape[0] + 2, m.shape[1] + 2), bool)
        p[1:-1, 1:-1] = m
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        if vuelta % 2:
            m = m & p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]
        vuelta += 1
    return d


def silueta(px, tolerancia):
    """(máscara, hubo_alpha) — qué parte de la imagen es la pieza.

    Con alpha es exacto y gratis: un render con *Film → Transparent* ya lo trae.
    Sin alpha hay que adivinar, y solo se puede adivinar bien con un fondo
    **plano**: se toma el color de las esquinas y se descarta lo que se le
    parece. Medido sobre un render de fondo degradado, ningún modelo simple
    separa fondo de pieza —ni el color de esquina, ni una cuadrática ajustada al
    marco, ni el matiz—, porque el degradado del fondo varía más que la
    diferencia con la pieza. Por eso el operador avisa cuando tuvo que adivinar
    en vez de dar el resultado por bueno.
    """
    if px.shape[2] > 3 and px[..., 3].min() < 0.5:
        return px[..., 3] > 0.5, True

    rgb = px[..., :3]
    k = max(4, min(px.shape[:2]) // 40)
    esquinas = np.concatenate([
        rgb[:k, :k].reshape(-1, 3), rgb[:k, -k:].reshape(-1, 3),
        rgb[-k:, :k].reshape(-1, 3), rgb[-k:, -k:].reshape(-1, 3),
    ])
    fondo = np.median(esquinas, axis=0)
    # tolerancia 0–1 sobre la diagonal del cubo RGB, que es la distancia máxima
    dist = np.sqrt(((rgb - fondo) ** 2).sum(-1))
    return dist > tolerancia * np.sqrt(3.0), False


def calcular_depth(px, domo=0.5, contraste=1.0, invertir=False, tolerancia=0.15):
    """Imagen a color → mapa de alturas 0–1. Devuelve (alto, hubo_alpha).

    `alto` es None si la máscara quedó vacía (tolerancia demasiado alta).
    """
    # submuestreo por salto. El "Suavizado" del Displace (filter_size 6.22 por
    # defecto) difumina bastante más que el paso que se pierde acá, así que no
    # hace falta promediar el bloque.
    paso = max(1, -(-max(px.shape[:2]) // RES_DEPTH))
    px = px[::paso, ::paso]

    mask, hubo_alpha = silueta(px, tolerancia)
    if not mask.any():
        return None, hubo_alpha

    # detalle: luminancia, auto-nivelada DENTRO de la silueta. Esa nivelación y
    # el contraste (que es una gamma) son la perilla: absorben que `pixels[]`
    # entregue sRGB o lineal, que depende de la gestión de color de la máquina.
    lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    lo, hi = float(lum[mask].min()), float(lum[mask].max())
    detalle = (lum - lo) / (hi - lo) if hi > lo else np.zeros_like(lum)
    detalle = np.clip(detalle, 0.0, 1.0) ** contraste

    # domo: la distancia al borde da un cono; la raíz lo redondea en cabujón,
    # que es la forma que se busca en una pieza de joyería
    d = distancia_al_borde(mask)
    cima = float(d.max())
    cupula = np.sqrt(d / cima) if cima else d

    alto = cupula * domo + detalle * (1.0 - domo)
    if invertir:
        alto = 1.0 - alto
    # el fondo queda plano en 0 pase lo que pase, incluso invirtiendo
    return np.clip(alto, 0.0, 1.0) * mask, hubo_alpha


def _imagen_del_relieve(obj):
    """(textura, imagen origen) del relieve activo, o (None, None)"""
    disp = obj.modifiers.get(DISP_MOD) if obj else None
    tex = disp.texture if disp else None
    img = tex.image if tex else None
    if img is None:
        return None, None
    # si ya se preparó una vez, se vuelve al original: nunca se apila el efecto
    origen = bpy.data.images.get(img.get("siro_source", "")) or img
    return tex, origen


# --- operadores -------------------------------------------------------------


class SIRO_OT_depthmap_relief(bpy.types.Operator, ImportHelper):
    """Crea un plano con relieve a partir de una imagen en escala de grises (depthmap)"""
    bl_idname = "siro.depthmap_relief"
    bl_label = "Nuevo relieve desde imagen"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp",
        options={'HIDDEN'},
    )

    def execute(self, context):
        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError:
            self.report({'ERROR'}, f"No pude cargar la imagen: {self.filepath}")
            return {'CANCELLED'}
        # espacio de color: se queda en sRGB (decidido en el plan), que es el default al cargar
        crear_relieve(context, img)  # 25% del tamaño original (5 mm de ancho)
        return {'FINISHED'}


class SIRO_OT_prep_depthmap(bpy.types.Operator):
    """Convierte la imagen a color del relieve en un depthmap: recorta la silueta, la abomba y usa la luminancia como detalle"""
    bl_idname = "siro.prep_depthmap"
    bl_label = "Preparar depthmap"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _imagen_del_relieve(context.active_object)[0] is not None

    def execute(self, context):
        scene = context.scene
        tex, origen = _imagen_del_relieve(context.active_object)
        if tex is None:
            self.report({'ERROR'}, "El relieve activo no tiene imagen")
            return {'CANCELLED'}

        alto, hubo_alpha = calcular_depth(
            leer_pixeles(origen),
            domo=scene.siro_dm_domo,
            contraste=scene.siro_dm_contraste,
            invertir=scene.siro_dm_invertir,
            tolerancia=scene.siro_dm_tolerancia,
        )
        if alto is None:
            self.report({'ERROR'}, "La silueta quedó vacía: baja la Tolerancia de fondo")
            return {'CANCELLED'}

        tex.image = escribir_depth(f"{origen.name}_depth", alto, fuente=origen.name)
        if hubo_alpha:
            self.report({'INFO'}, f"Depthmap de {alto.shape[1]}×{alto.shape[0]} desde el alpha de la imagen")
        else:
            # no es un detalle menor: sin alpha la silueta es una suposición, y
            # con fondo degradado o con sombra proyectada sale mal
            self.report(
                {'WARNING'},
                "Sin alpha: la silueta se adivinó por el color de las esquinas. "
                "Ajusta la Tolerancia, o trae un PNG con alpha (Film → Transparent)",
            )
        return {'FINISHED'}


class SIRO_OT_bake_depthmap(bpy.types.Operator):
    """Depthmap real de la pieza activa vista desde arriba, y el relieve plano que sale de él"""
    bl_idname = "siro.bake_depthmap"
    bl_label = "Relieve desde pieza 3D"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and DISP_MOD not in obj.modifiers

    def execute(self, context):
        obj = context.active_object
        # el mismo muestreo que usa el relleno para imitar la vista ortográfica
        # de 3D Builder: cada vértice de una grilla cae sobre la superficie más
        # alta de su columna. 0,06 s contra 8 000 caras, medido.
        cx, cy, lado, top = extrude_down._encuadre(obj)
        altura = top + lado  # nace bien arriba: naciendo adentro, el rayo saldría por abajo

        bpy.ops.mesh.primitive_grid_add(
            x_subdivisions=RES_DEPTH - 1, y_subdivisions=RES_DEPTH - 1,
            size=lado, location=(cx, cy, altura),
        )
        grilla = context.active_object
        mod = grilla.modifiers.new("SiroProyeccion", 'SHRINKWRAP')
        mod.wrap_method = 'PROJECT'
        mod.use_project_z = True
        mod.use_negative_direction = True   # hacia abajo
        mod.use_positive_direction = False
        mod.target = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)

        n = len(grilla.data.vertices)
        co = np.empty(n * 3, np.float32)
        grilla.data.vertices.foreach_get('co', co)
        bpy.data.objects.remove(grilla, do_unlink=True)
        # los vértices salen en orden de filas, X primero e Y ascendente — el
        # mismo orden en que se guardan los píxeles de una imagen (fila 0 abajo),
        # así que no hay que voltear nada. `co` está en espacio local: la grilla
        # no rota ni escala, así que pasar a mundo es sumarle su altura.
        z = co.reshape(n, 3)[:, 2].reshape(RES_DEPTH, RES_DEPTH) + altura

        tocado = z < altura - 1e-4  # los que no impactaron se quedaron arriba: son el fondo
        if not tocado.any():
            self.report({'ERROR'}, "La proyección no tocó la pieza")
            return {'CANCELLED'}
        lo, hi = float(z[tocado].min()), float(z[tocado].max())
        rango = hi - lo
        alto = np.where(tocado, (z - lo) / rango if rango else 1.0, 0.0)

        img = escribir_depth(f"{obj.name}_depth", np.clip(alto, 0.0, 1.0).astype(np.float32))
        # a tamaño real: el cuadro de muestreo mide `lado`, y el plano nace de 2
        relieve = crear_relieve(context, img, escala=lado / 2.0)
        relieve.modifiers[DISP_MOD].strength = rango  # 1:1 con la pieza de origen
        self.report({'INFO'}, f"Depthmap {RES_DEPTH}² · el rango 0–1 son {rango:.2f} mm")
        return {'FINISHED'}


class SIRO_OT_apply_relief(bpy.types.Operator):
    """Convierte el relieve en malla real y cerrada, lista para recortar el contorno y unir al resto de la pieza"""
    bl_idname = "siro.apply_relief"
    bl_label = "Aplicar relieve"
    bl_options = {'REGISTER', 'UNDO'}

    base_thickness: bpy.props.FloatProperty(
        name="Grosor de base (mm)",
        description="Espesor que se le da a la lámina para que sea un sólido fusionable",
        default=1.0,
        min=0.1,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and DISP_MOD in obj.modifiers

    def execute(self, context):
        obj = context.active_object
        if DISP_MOD in obj.modifiers:
            bpy.ops.object.modifier_apply(modifier=DISP_MOD)

        # el grid desplazado es una lámina abierta: sin volumen, fusionarlo con
        # una pieza da basura no-manifold (EXACT) o no hace nada (MANIFOLD)
        n = len(obj.data.vertices)
        solid = obj.modifiers.new("SiroGrosor", 'SOLIDIFY')
        solid.thickness = self.base_thickness
        solid.offset = -1.0  # crece hacia abajo, la cara con relieve no se mueve
        bpy.ops.object.modifier_apply(modifier=solid.name)

        # El Solidify hace el trabajo topológico —duplica la malla, invierte la
        # copia y cose el borde— pero la desplaza **a lo largo de la normal**, y
        # esto es un heightfield con paredes verticales en el borde de la
        # silueta. Encima el objeto tiene escala no uniforme (ver crear_relieve),
        # que en local, donde opera el modifier, empina las pendientes 2,5×.
        # Medido sobre una pieza de 5 mm: la base se arrastraba 2,5 mm de costado,
        # el grosor caía de 1 mm a 0,03 mm y la malla quedaba auto-intersecada
        # (volumen negativo: ni orientable, y cualquier Fusionar posterior daba
        # basura). Se aplana a mano: la copia (índices n..2n, 1:1 con la de
        # arriba) toma el mismo XY y un Z constante. Base plana, que además es la
        # que apoya para fundición.
        co = np.empty(len(obj.data.vertices) * 3, np.float32)
        obj.data.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        co[n:2 * n, :2] = co[:n, :2]
        # los vértices están en local: el grosor se pide en mm de la escena
        co[n:2 * n, 2] = co[:n, 2].min() - self.base_thickness / (abs(obj.scale.z) or 1.0)
        obj.data.vertices.foreach_set('co', co.ravel())

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {'FINISHED'}
