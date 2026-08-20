"""Generador de anillos por talla: banda + top de sello, en una sola malla barrida.

El anillo se barre alrededor de un ángulo `th` (0 = arriba, +Z), con el eje del
dedo en Y. Cada paso aporta una sección cerrada en el plano (Y, radio), y las
secciones consecutivas se puentean de forma cíclica: sale un sólido cerrado sin
tapas, manifold por construcción.

El top NO es un sólido aparte que se fusione después. Todas las formas de sello
(rectángulo redondeado, óvalo, hexágono) son convexas y simétricas respecto del
plano Y=0, con el eje largo a lo largo del barrido, así que se expresan como un
semiancho `w(th)` más un recorte plano: en el sector del sello el punto más
externo de cada sección se fija en `r = z_placa / cos(th)`, con lo que TODOS caen
en el plano `z = z_placa` y la cara superior sale plana por construcción.

Sin boolean hay una ventaja que no es cosmética: un boolean necesita `bpy.ops` y
objetos temporales, y eso no se puede correr desde un callback `update=` de una
propiedad. Siendo bmesh puro, reconstruir el anillo en vivo es seguro.
"""

import math

import bmesh
import bpy

# Copia literal de TABLA_TALLAS_CHILE en
# !Dashboard/src/components/PreciosCalculadora.tsx:433 — la fuente de verdad de
# las tallas. Si allá cambia un número, acá también. Sistema chileno, ∅ interior
# en mm (la escena del addon trabaja en mm: 1 unidad de Blender = 1 mm).
TALLAS = ((1, 13.0), (2, 13.4), (3, 13.7), (4, 14.0), (5, 14.3), (6, 14.6), (7, 15.0), (8, 15.3),
          (9, 15.6), (10, 15.9), (11, 16.2), (12, 16.5), (13, 16.8), (14, 17.2), (15, 17.5),
          (16, 17.8), (17, 18.1), (18, 18.4), (19, 18.8), (20, 19.1), (21, 19.4), (22, 19.7),
          (23, 20.0), (24, 20.3), (25, 20.6), (26, 21.0), (27, 21.3), (28, 21.6), (29, 22.0),
          (30, 22.3), (31, 22.6), (32, 22.9), (33, 23.2), (34, 23.5), (35, 23.9), (36, 24.2))

TALLAS_ITEMS = tuple((str(n), str(n), f"Talla {n} — ∅ interior {d} mm") for n, d in TALLAS)
DIAMETRO = {str(n): d for n, d in TALLAS}

PERFILES = (
    ('MEDIA_CANA', "Media caña", "Exterior abombado, interior recto. El clásico"),
    ('PLANO', "Plano", "Sección rectangular, cantos vivos"),
    ('CONFORT', "Confort", "Media caña con el interior abarrilado: entra y sale más fácil"),
    ('BISELADO', "Biselado", "Banda plana con los cantos exteriores chaflanados"),
)

TOPS = (
    ('RECTANGULO', "Rectángulo", "Sello rectangular de esquinas redondeadas. Con largo = ancho da un cuadrado"),
    ('OVALO', "Óvalo", "Sello ovalado. Con largo = ancho da un círculo"),
    ('HEXAGONO', "Hexágono", "Sello hexagonal, con las puntas sobre el eje largo. Girá 90° para ponerlas a lo ancho"),
    ('CORAZON', "Corazón", "Punta hacia el frente y muesca hacia atrás. Girado 90° la muesca se rellena (el panel avisa)"),
    ('ESCUDO', "Escudo", "Borde recto y punta al otro lado, para grabar. Girá 90° para que la punta mire al frente"),
    ('NINGUNO', "Sin top", "Solo la banda, sin sello"),
)

# El barrido completo, no la mitad: el sello se lleva un tercio de los pasos.
SEGMENTOS = (
    ('128', "Bajo", "Rápido de reconstruir; se notan las facetas en el sello"),
    ('256', "Medio", "El equilibrio para trabajar"),
    ('512', "Alto", "Para exportar a fundición"),
)

# Cuántos puntos tiene cada borde de la sección (el otro borde lleva los mismos).
# Impares a propósito: así siempre hay un vértice en el centro de la sección, que
# es la cresta de la media caña y la punta del óvalo. Con conteo par no existían.
_MUESTRAS_Y = {128: 13, 256: 17, 512: 25}


def _suave(t):
    """Smoothstep: entra y sale con pendiente 0, así el hombro no deja una cresta"""
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _hermite(v, p0, m0, p1, m1):
    """Cúbica de Hermite: pasa por p0 y p1 con las pendientes m0 y m1"""
    v2 = v * v
    v3 = v2 * v
    return ((2.0 * v3 - 3.0 * v2 + 1.0) * p0 + (v3 - 2.0 * v2 + v) * m0
            + (-2.0 * v3 + 3.0 * v2) * p1 + (v3 - v2) * m1)


def contorno_top(forma, largo, ancho, redondeo, giro, n=128):
    """Contorno cerrado del sello visto desde arriba, ya girado. Lista de (x, y).

    `x` corre a lo largo del anillo y `y` a lo largo del dedo. Cada forma se
    dibuja en su propio marco con `largo` sobre x y `ancho` sobre y, y después se
    rota entera: por eso el giro es libre y no dos posiciones fijas.
    """
    a = max(1e-4, largo / 2.0)
    b = max(1e-4, ancho / 2.0)
    pts = []

    if forma == 'OVALO':
        for i in range(n):
            t = 2.0 * math.pi * i / n
            pts.append((a * math.cos(t), b * math.sin(t)))
    elif forma == 'HEXAGONO':
        # Puntas sobre el eje largo; los dos lados largos, rectos.
        pts = [(a, 0.0), (a / 2.0, b), (-a / 2.0, b), (-a, 0.0), (-a / 2.0, -b), (a / 2.0, -b)]
    elif forma == 'CORAZON':
        # El eje de simetría va sobre Y —punta abajo, muesca arriba— y NO sobre X.
        # No es capricho: la muesca tiene que ser una hendidura del borde de
        # arriba para que cada x siga teniendo un solo tramo de material. Con el
        # eje sobre X la huella se parte en dos y el barrido no puede
        # representarla (ver `_rango_y` y el aviso del panel).
        crudo = []
        for i in range(n):
            t = 2.0 * math.pi * i / n
            x = 16.0 * math.sin(t) ** 3
            y = 13.0 * math.cos(t) - 5.0 * math.cos(2 * t) - 2.0 * math.cos(3 * t) - math.cos(4 * t)
            crudo.append((x, y))
        # La curva no está centrada —va de -17 a +5 en y— así que se encaja en su
        # bbox y no se divide por el máximo absoluto: si no, el corazón salía
        # descentrado y con 6 mm de alto en vez de los 9 pedidos.
        xs = [q[0] for q in crudo]
        ys = [q[1] for q in crudo]
        cx, ex = (min(xs) + max(xs)) / 2.0, max(1e-9, max(xs) - min(xs))
        cy, ey = (min(ys) + max(ys)) / 2.0, max(1e-9, max(ys) - min(ys))
        pts = [((q[0] - cx) * 2.0 * a / ex, (q[1] - cy) * 2.0 * b / ey) for q in crudo]
    elif forma == 'ESCUDO':
        # Borde recto en -x, punta en +x: lados rectos el primer tramo y después
        # un cuarto de elipse hasta la punta.
        k = max(4, n // 4)
        arriba = []
        for i in range(k + 1):
            t = i / k
            h = b if t <= 0.35 else b * math.sqrt(max(0.0, 1.0 - ((t - 0.35) / 0.65) ** 2))
            arriba.append((-a + 2.0 * a * t, h))
        pts = arriba + [(x, -y) for x, y in reversed(arriba)]
    else:  # RECTANGULO con esquinas de radio `redondeo`
        r = min(redondeo, a, b)
        k = max(2, n // 8)
        for cx, cy, a0 in ((a - r, b - r, 0.0), (-(a - r), b - r, math.pi / 2.0),
                           (-(a - r), -(b - r), math.pi), (a - r, -(b - r), 1.5 * math.pi)):
            for i in range(k + 1):
                t = a0 + (math.pi / 2.0) * i / k
                pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))

    if abs(giro) < 1e-9:
        return pts
    co, si = math.cos(giro), math.sin(giro)
    return [(x * co - y * si, x * si + y * co) for x, y in pts]


def _rango_y(contorno, x):
    """Tramo de material (y_min, y_max) y cuántas veces la vertical en `x` cruza el contorno.

    `cruces > 2` significa que a esa altura el sello son DOS trozos separados
    —el caso del corazón girado 90°— y el barrido no puede representarlo: una
    sección ocupa un intervalo continuo de Y, así que la muesca se rellenaría.
    """
    ys = []
    n = len(contorno)
    for i in range(n):
        x0, y0 = contorno[i]
        x1, y1 = contorno[(i + 1) % n]
        if (x0 <= x < x1) or (x1 <= x < x0):
            ys.append(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    if not ys:
        return None
    return min(ys), max(ys), len(ys)


def _muestras_y(y0, y1, p0, p1, n):
    """`n` alturas de y0 a y1 que SIEMPRE incluyen p0 y p1, los bordes de la cara plana.

    Con muestreo parejo, una cara plana angosta —la punta del hexágono girado, el
    lóbulo del corazón— puede caer entre dos muestras y desaparecer: el sello
    sale con la punta redondeada y unas décimas corto. Es el mismo error que el
    del ulp en el borde del sello, un nivel más abajo.
    """
    cortes = sorted({y0, y1} | {q for q in (p0, p1) if y0 + 1e-9 < q < y1 - 1e-9})
    tramos = list(zip(cortes, cortes[1:]))
    largos = [b - a for a, b in tramos]
    total = sum(largos) or 1.0
    libres = n - len(cortes)
    reparto = [int(libres * L / total) for L in largos]
    while sum(reparto) < libres:  # los que sobran por truncar van al tramo más largo
        reparto[largos.index(max(largos))] += 1
    ys = [cortes[0]]
    for (a, b), k in zip(tramos, reparto):
        ys.extend(a + (b - a) * i / (k + 1) for i in range(1, k + 1))
        ys.append(b)
    return ys


def _seccion(perfil, r_int, y0, y1, r_ext, redondez, n_y, plano=None, r_caida=None):
    """Contorno cerrado de la sección, en (y, radio). Siempre devuelve 2*n_y puntos.

    El conteo tiene que ser el mismo en todas las secciones o el puenteado
    cíclico no cierra. `redondez` (0..1) apaga la curvatura del perfil exterior:
    va en 0 bajo el sello —donde la cara de arriba es plana— y en 1 en la banda.

    `plano` es el sub-tramo (p0, p1) donde la cara del sello es plana, cuando es
    más angosto que la sección. Pasa en las puntas del óvalo y del corazón, donde
    el sello ya es más angosto que la banda que lleva debajo: sin esto habría que
    recortar el sello al ancho de la banda y las puntas saldrían cortadas. El
    material que sobra a los lados baja hasta `r_caida`, el radio de la banda.
    """
    grosor = max(1e-4, r_ext - r_int)
    centro = (y0 + y1) / 2.0
    medio = max(1e-6, (y1 - y0) / 2.0)
    bulto = chaflan = 0.0
    if perfil in ('MEDIA_CANA', 'CONFORT'):
        bulto = redondez * min(grosor * 0.55, medio * 0.9)
    elif perfil == 'BISELADO':
        chaflan = redondez * min(grosor * 0.35, medio * 0.35)
    # El interior de confort NO se apaga bajo el sello: es la superficie que toca
    # el dedo y tiene que ser igual en toda la vuelta.
    confort = min(0.25, grosor * 0.2) if perfil == 'CONFORT' else 0.0
    borde = max(0.0, 1.0 - chaflan / medio) if chaflan else 1.0
    p0, p1 = plano if plano else (y0, y1)
    hombrito = plano is not None and (p0 - y0 > 1e-6 or y1 - p1 > 1e-6)
    caida = max(0.0, r_ext - r_caida) if hombrito else 0.0

    ys = _muestras_y(y0, y1, p0, p1, n_y)
    pts = []
    for y in ys:  # borde exterior, de y0 a y1
        u = abs(y - centro) / medio
        if hombrito:
            if y > p1:
                v = (y - p1) / max(1e-9, y1 - p1)
            elif y < p0:
                v = (p0 - y) / max(1e-9, p0 - y0)
            else:
                v = 0.0
            r = r_ext - caida * (1.0 - math.sqrt(max(0.0, 1.0 - v * v)))
        elif bulto:
            r = r_ext - bulto * (1.0 - math.sqrt(max(0.0, 1.0 - u * u)))
        elif chaflan:
            r = r_ext - chaflan * max(0.0, u - borde) / max(1e-9, 1.0 - borde)
        else:
            r = r_ext
        pts.append((y, r))
    for y in reversed(ys):  # borde interior, de y1 a y0
        u = abs(y - centro) / medio
        r = r_int + confort * (1.0 - math.sqrt(max(0.0, 1.0 - u * u)))
        pts.append((y, r))
    return pts


def construir(p):
    """bmesh cerrado del anillo descrito por `p` (un SIRO_PG_ring).

    Devuelve `(bm, huella_partida)`: lo segundo avisa que el sello elegido no se
    puede representar a este ángulo.
    """
    r_int = DIAMETRO[p.talla] / 2.0
    w_band = p.ancho / 2.0
    n = int(p.segmentos)
    n_y = _MUESTRAS_Y[n]
    masa = min(0.9, p.masa)

    # La banda deja de ser un cilindro: el refuerzo suma material arriba y se
    # desvanece con un coseno hasta 0 abajo, así `grosor` sigue significando lo
    # mismo que antes — el fondo del aro, que es la medida estructural.
    def r_banda(a):
        return r_int + p.grosor + p.refuerzo * (1.0 + math.cos(a)) / 2.0

    con_top = p.top != 'NINGUNO'
    partida = False
    lados = {}
    if con_top:
        contorno = contorno_top(p.top, p.top_largo, p.top_ancho, p.redondeo, p.giro)
        x_min = min(q[0] for q in contorno)
        x_max = max(q[0] for q in contorno)
        eps = 1e-6 * max(1e-4, x_max - x_min)
        z_placa = r_banda(0.0) + p.top_alto

        def _huella(x):
            """(y0, y1) del sello en `x`, recortando al bbox.

            El recorte no es cosmético: en el borde exacto, `x` se pasa por un
            ulp y el scanline no devuelve nada. La versión anterior sacaba 0 de
            ahí y el sello salía medio milímetro corto.
            """
            nonlocal partida
            rg = _rango_y(contorno, min(max(x, x_min + eps), x_max - eps))
            if rg is None:
                return 0.0, 0.0
            if rg[2] > 2:
                partida = True
            return rg[0], rg[1]

        # El sello puede ser asimétrico (corazón, escudo, cualquier giro), así que
        # cada lado del anillo se resuelve por separado.
        for s, x_ext in ((1, x_max), (-1, -x_min)):
            # 1.30 rad ≈ 74°: más allá, `tan` se dispara y el sello dejaría de
            # ser una tapa para envolver el anillo.
            lim = min(1.30, math.atan(x_ext / z_placa))
            r_p = z_placa / math.cos(lim)
            # El hombro es la TANGENTE desde el borde del sello a la banda: una
            # recta en el plano del anillo que aterriza sin costura. Interpolar
            # el radio con un smoothstep —lo primero que se probó— hacía que el
            # radio bajara más rápido de lo que avanzaba el ángulo, y la silueta
            # salía con un bulto y un pellizco. Sobre una recta no puede pasar.
            # Con refuerzo la banda ya no es un círculo, así que el punto de
            # tangencia se busca con un punto fijo: converge en un par de vueltas.
            r0 = r_banda(0.0)
            a_t = lim
            for _ in range(6):
                a_t = lim + math.acos(min(1.0, r0 / r_p))
                r0 = r_banda(a_t)
            y0_p, y1_p = _huella(s * x_ext)
            y0_p = min(y0_p, -w_band)
            y1_p = max(y1_p, w_band)
            # Pendiente real del contorno en el borde del sello: es lo que hace
            # que el hombro herede la curva de la forma elegida en vez de cerrar
            # siempre igual. El óvalo se cierra redondo, el rectángulo se
            # mantiene y dobla en la esquina.
            d = max(1e-3, (lim) * 0.05)
            xa = z_placa * math.tan(s * max(0.0, lim - d))
            y0_a, y1_a = _huella(xa)
            tramo = (a_t - lim) * max(1e-3, 1.0 - masa)
            m0 = (max(y0_p, -1e9) - min(y0_a, -w_band)) / d * tramo
            m1 = (y1_p - max(y1_a, w_band)) / d * tramo
            tope0 = 3.0 * abs(-w_band - y0_p)
            tope1 = 3.0 * abs(w_band - y1_p)
            lados[s] = (lim, a_t, r0, y0_p, y1_p,
                        max(-tope0, min(tope0, m0)), max(-tope1, min(tope1, m1)))
        con_top = min(lados[1][0], lados[-1][0]) > 1e-3

    angs = [2.0 * math.pi * i / n for i in range(n)]
    if con_top:
        # Los pasos van parejos, salvo los dos del borde del sello, que se meten
        # exactos: si el barrido cae 1° antes, el sello sale medio milímetro
        # corto y "14 mm de largo" deja de ser verdad.
        tol = math.pi / n * 0.25
        for extra in (lados[1][0], 2.0 * math.pi - lados[-1][0]):
            j = min(range(len(angs)), key=lambda i: abs(angs[i] - extra))
            if abs(angs[j] - extra) < tol:
                # Reemplaza, no saltea. Saltear parecía suficiente —el paso
                # vecino está a menos de un cuarto de grado— pero ese vecino
                # puede caer del lado de AFUERA del sello, y entonces la sección
                # del borde no existe: el hexágono girado perdía la punta y el
                # sello salía 0,7 mm corto.
                angs[j] = extra
            else:
                angs.append(extra)
        angs.sort()

    bm = bmesh.new()
    anillos = []
    for th in angs:
        d = ((th + math.pi) % (2.0 * math.pi)) - math.pi  # ángulo con signo al tope
        a = abs(d)
        plano = r_caida = None
        if not con_top:
            y0, y1, r_ext, red = -w_band, w_band, r_banda(a), 1.0
        else:
            lim, a_t, r0, y0_p, y1_p, m0, m1 = lados[1 if d >= 0 else -1]
            if a <= lim:
                q0, q1 = _huella(z_placa * math.tan(d))
                y0, y1 = min(q0, -w_band), max(q1, w_band)
                r_ext = z_placa / math.cos(a)
                plano = (q0, q1)
                r_caida = r_banda(a)
                red = 0.0
            elif a >= a_t:
                y0, y1, r_ext, red = -w_band, w_band, r_banda(a), 1.0
            else:
                u = (a - lim) / (a_t - lim)
                # `masa` sostiene la huella del sello el primer tramo y recién
                # después arranca el Hermite: es el bloque macizo bajo el sello.
                v = 0.0 if u <= masa else (u - masa) / max(1e-6, 1.0 - masa)
                y0 = min(-w_band, _hermite(v, y0_p, m0, -w_band, 0.0))
                y1 = max(w_band, _hermite(v, y1_p, m1, w_band, 0.0))
                recta = r0 / math.cos(a_t - a)
                # `cintura` tira la recta hacia la banda con un bombo que vale 0
                # en los dos extremos: ni el borde del sello ni el punto de
                # tangencia se mueven, así no se pierde la continuidad.
                r_ext = recta - p.cintura * (recta - r_banda(a)) * math.sin(math.pi * u)
                r_ext = max(r_ext, r_banda(a))
                red = v
        sec = _seccion(p.perfil, r_int, y0, y1, max(r_ext, r_int + 0.05), red, n_y, plano, r_caida)
        s, c = math.sin(th), math.cos(th)
        anillos.append([bm.verts.new((r * s, y, r * c)) for y, r in sec])

    m = len(anillos[0])
    for i in range(len(anillos)):
        A, B = anillos[i], anillos[(i + 1) % len(anillos)]
        for j in range(m):
            k = (j + 1) % m
            try:
                bm.faces.new((A[j], A[k], B[k], B[j]))
            except ValueError:
                pass  # cara repetida: dos secciones cayeron encima
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm, partida


def _reconstruir(self, context):
    """Callback de cada propiedad. El objeto dueño sale de `id_data`, no del contexto:
    el panel puede estar dibujando otro objeto cuando esto corre."""
    obj = self.id_data
    if not self.activo or obj is None or obj.type != 'MESH':
        return
    bm, partida = construir(self)
    bm.to_mesh(obj.data)  # la misma malla: conserva transform, materiales y selección
    bm.free()
    obj.data.update()
    # Ojo con el acceso crudo: `self.aviso_huella = ...` volvería a disparar el
    # callback `update=` y entraría en bucle. Escribir por clave toca la
    # ID-property directo y no dispara nada.
    self["aviso_huella"] = partida


class SIRO_PG_ring(bpy.types.PropertyGroup):
    activo: bpy.props.BoolProperty(
        name="Anillo vivo",
        description="Mientras esté encendido, cambiar cualquier medida reconstruye la malla",
        default=False,
    )
    talla: bpy.props.EnumProperty(
        name="Talla",
        description="Talla chilena. El ∅ interior sale de la tabla de la calculadora del dashboard",
        items=TALLAS_ITEMS,
        default='14',
        update=_reconstruir,
    )
    perfil: bpy.props.EnumProperty(
        name="Perfil", description="Forma de la sección de la banda",
        items=PERFILES, default='MEDIA_CANA', update=_reconstruir,
    )
    ancho: bpy.props.FloatProperty(
        name="Ancho", description="Ancho de la banda, a lo largo del dedo",
        default=4.0, min=0.6, soft_max=12.0, unit='LENGTH', update=_reconstruir,
    )
    grosor: bpy.props.FloatProperty(
        name="Grosor", description="Espesor de la banda en dirección radial",
        default=1.8, min=0.4, soft_max=6.0, unit='LENGTH', update=_reconstruir,
    )
    top: bpy.props.EnumProperty(
        name="Top", description="Forma del sello. Sin top deja la banda sola",
        items=TOPS, default='RECTANGULO', update=_reconstruir,
    )
    top_largo: bpy.props.FloatProperty(
        name="Largo", description="Medida del sello a lo largo del anillo",
        default=14.0, min=1.0, soft_max=30.0, unit='LENGTH', update=_reconstruir,
    )
    top_ancho: bpy.props.FloatProperty(
        name="Ancho del top", description="Medida del sello a lo largo del dedo",
        default=9.0, min=1.0, soft_max=30.0, unit='LENGTH', update=_reconstruir,
    )
    top_alto: bpy.props.FloatProperty(
        name="Alto", description="Material del sello por encima de la banda",
        default=1.5, min=0.1, soft_max=8.0, unit='LENGTH', update=_reconstruir,
    )
    redondeo: bpy.props.FloatProperty(
        name="Redondeo", description="Radio de las esquinas del sello rectangular",
        default=1.5, min=0.0, soft_max=8.0, unit='LENGTH', update=_reconstruir,
    )
    giro: bpy.props.FloatProperty(
        name="Giro", description="Gira el sello sobre la cara del anillo. 90° pone a lo ancho lo que estaba a lo largo",
        default=0.0, min=-math.pi, max=math.pi, subtype='ANGLE', update=_reconstruir,
    )
    masa: bpy.props.FloatProperty(
        name="Masa", description="Cuánto sostiene el hombro la huella del sello antes de cerrarse hacia la banda. Sube para el bloque macizo de los sellos clásicos",
        default=0.6, min=0.0, max=0.9, subtype='FACTOR', update=_reconstruir,
    )
    cintura: bpy.props.FloatProperty(
        name="Cintura", description="Curva el hombro hacia adentro en vez de bajar recto del sello a la banda",
        # El máximo está MEDIDO, no elegido: hasta 0,60 la silueta no retrocede
        # ni una micra; en 0,70 son 0,002 mm y en 0,80 ya son 0,072 —un pellizco
        # visible— porque el bombo que curva el hombro deja los extremos sobre la
        # recta y hunde el medio. 0,65 es el tope con margen.
        default=0.35, min=0.0, max=0.65, subtype='FACTOR', update=_reconstruir,
    )
    refuerzo: bpy.props.FloatProperty(
        name="Refuerzo", description="Grosor extra en la mitad de arriba del aro, que se desvanece hacia el fondo. `Grosor` sigue siendo la banda de abajo",
        default=1.0, min=0.0, soft_max=4.0, unit='LENGTH', update=_reconstruir,
    )
    aviso_huella: bpy.props.BoolProperty(
        name="Huella partida", default=False, options={'HIDDEN'},
    )
    segmentos: bpy.props.EnumProperty(
        name="Detalle", description="Pasos del barrido alrededor del anillo",
        items=SEGMENTOS, default='256', update=_reconstruir,
    )


class SIRO_OT_ring_add(bpy.types.Operator):
    """Crea un anillo de la talla elegida. Queda vivo: podés cambiar talla, perfil y sello cuantas veces quieras hasta apretar Aplicar"""
    bl_idname = "siro.ring_add"
    bl_label = "Nuevo anillo"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..ui import panels

        obj = bpy.data.objects.new("Anillo", bpy.data.meshes.new("Anillo"))
        context.collection.objects.link(obj)
        obj.siro_ring.activo = True
        _reconstruir(obj.siro_ring, context)

        # Foco: un operador que deja la escena sin objeto activo hace que el
        # gizmo se dibuje y no arrastre (v0.15.3).
        for otro in context.selected_objects:
            otro.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

        if not panels.escena_en_mm(context.scene):
            self.report({'WARNING'}, "La escena no está en mm: el anillo mide bien igual, "
                                     "pero los paneles no lo muestran en mm")
        return {'FINISHED'}


class SIRO_OT_ring_apply(bpy.types.Operator):
    """Congela el anillo como malla normal: deja de reconstruirse y entra al resto del pipeline"""
    bl_idname = "siro.ring_apply"
    bl_label = "Aplicar a malla"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and getattr(obj, "siro_ring", None) \
            and obj.siro_ring.activo

    def execute(self, context):
        from . import boolean_ops

        obj = context.active_object
        obj.siro_ring.activo = False
        abiertas = boolean_ops._open_edge_count(obj)
        if abiertas:
            self.report({'WARNING'}, f"El anillo quedó con {abiertas} aristas abiertas")
        else:
            self.report({'INFO'}, "Anillo aplicado: malla cerrada")
        return {'FINISHED'}
