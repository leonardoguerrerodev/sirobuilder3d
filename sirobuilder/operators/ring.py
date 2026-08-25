"""Generador de anillos por talla: banda + top de sello, en una sola malla barrida.

El anillo se barre alrededor de un ángulo `th` (0 = arriba, +Z), con el eje del
dedo en Y. Cada paso aporta una sección cerrada en el plano (Y, radio), y las
secciones consecutivas se puentean de forma cíclica: sale un sólido cerrado sin
tapas, manifold por construcción.

El top NO es un sólido aparte que se fusione después. Cada sección es el CUERPO
del anillo —una media caña barrida, con su radio y su semiancho propios— con la
PLACA del sello puesta encima donde la huella la tapa: `r = max(cuerpo, placa)`,
con la placa en `r = z_placa / cos(th)`, así que TODOS sus puntos caen en el plano
`z = z_placa` y la cara superior sale plana por construcción.

Que sean dos superficies que conviven y no dos regímenes que se turnan es lo que
saca el escalón: hasta la v0.17.0 el material que flanqueaba la placa caía al aro
pelado mientras el hombro de al lado ya estaba un milímetro más afuera, y en el
borde del sello las dos se topaban con un filo.

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
    ('CIRCULO', "Círculo", "Sello redondo. Un solo diámetro: `Ancho del top` no se usa"),
    ('HEXAGONO', "Hexágono", "Sello hexagonal, con las puntas sobre el eje largo. Girá 90° para ponerlas a lo ancho"),
    ('CORAZON', "Corazón", "Punta hacia el frente y muesca hacia atrás. Girado 90° la muesca se rellena (el panel avisa)"),
    ('ESCUDO', "Escudo", "Borde recto y punta al otro lado, para grabar. Girá 90° para que la punta mire al frente"),
    ('NINGUNO', "Sin top", "Solo la banda, sin sello"),
)

# Qué es la cara de arriba de la CABEZA por fuera de la huella del sello. Hasta la
# v0.21.0 sólo existía `ABOMBADA`, y con una huella más angosta que la banda esa
# media caña se comía el sello: un hexágono de 1 mm de largo sobre una banda de 8
# daba un domo de 1,74 mm y la cara plana quedaba como un filo adentro.
CABEZAS = (
    ('PLANA', "Plana", "La cara de arriba de la cabeza es un solo plano: al achicar el sello el top no se curva"),
    ('ABOMBADA', "Abombada", "El lomo de la cabeza sigue la media caña de la banda alrededor del sello"),
    ('RELIEVE', "Relieve", "El sello se para sobre el lomo de la banda: su contorno se ve aunque sea más angosto que el aro. `Masa` y `Cintura` no aplican"),
)

# g/mm³ de la plata 950 (95 % plata fina, 5 % cobre), que es la ley con la que se
# trabaja acá. Lo que fija el peso no es el peso atómico sino la DENSIDAD de la
# aleación, y ésta sale de la regla de volúmenes aditivos sobre las densidades de
# los dos metales —plata fina 10,49 y cobre 8,96 g/cm³:
#     1/ρ = 0,95/10,49 + 0,05/8,96  →  10,4012 g/cm³
# La misma cuenta devuelve 10,357 para la 925, que es el 10,36 de tabla: ésa es la
# comprobación de que está bien planteada y no es un número copiado.
# Es el peso de la PIEZA: la fundición pide además bebedero, botón y mermas, que no
# salen de la geometría.
DENSIDAD_PLATA_950 = 0.0104012

# Radio, en mm, del filete que redondea el codo en planta donde la huella del sello
# cruza el ancho de la banda. Era `w_b` —el semiancho de la banda ENTERO—, así que la
# mezcla entre "ancho del sello" y "ancho de la banda" estaba activa en TODO el
# recorrido en vez de en una franja: el smooth-max sobrepasa hasta 0,1875·k, y con
# k = 4 mm un hexágono de 12 salía de 12,219 con las puntas romas y un óvalo de 8 de
# ancho salía de 9,5. Con 0,25 el sobrepaso máximo (0,047 mm) queda bajo los 0,05 con
# que los tests miden el sello, y el codo sigue sin ser un filo.
SUAVIZADO_PLANTA = 0.25

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
    """Smoothstep: entra y sale con pendiente 0, así el hombro no deja una cresta.

    Rige cuánto se acota el bulto de la media caña bajo el sello (ver `construir`)."""
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _maximo_suave(a, b, k):
    """`max(a, b)` sin el vértice: en la franja `±k` alrededor del cruce redondea.

    El ancho del anillo es `max(huella del sello, ancho de la banda)`, y ese max
    a secas deja un codo en planta justo donde el sello se angosta hasta el ancho
    del aro — el semiancho del óvalo venía bajando 0,21 mm por grado y se cortaba
    en seco. Afuera de la franja devuelve el max exacto, así que el sello mide lo
    que dice la perilla.
    """
    d = a - b
    if d >= k:
        return a
    if d <= -k:
        return b
    # Quíntica y no parábola: la parábola empalma con pendiente pero no con
    # CURVATURA, y ese salto de curvatura se ve —una cornisa por lado sobre la
    # cara del sello, justo donde la huella deja de mandar. `2x³ - x⁴` entra y
    # sale con la curvatura del lado que corresponde.
    x = (d + k) / (2.0 * k)
    return b + k * x * x * x * (2.0 - x)


# Ángulo interior por debajo del cual un vértice cuenta como esquina viva. Un óvalo
# de 128 puntos gira 2,8° por vértice —177,2° de interior— y no entra ni de casualidad;
# el hexágono tiene 106° y 127°, el escudo 90°.
_ESQUINA = math.radians(150.0)


def _redondear(pts, r, tope, n_arco=6):
    """Reemplaza cada esquina viva del contorno cerrado por un arco tangente tope `r`.

    Un filete de radio `r` en una esquina de ángulo interior θ hay que recortarlo
    `r / tan(θ/2)` sobre cada lado, medido DESDE la esquina. Donde los dos lados son
    rectos (rectángulo, hexágono, el canto del escudo) el arco es tangente exacto y
    `Redondeo` vale lo que dice.

    `tope` es el segundo freno, por tamaño de la forma: sin él, una esquina muy
    aguda pediría recortar más de lo que la forma tiene y el filete se comería el
    contorno entero. Con el freno, el filete es el más grande que entra.
    """
    n = len(pts)
    if r <= 0.0 or n < 3:
        return pts

    def _dir(i, j):
        dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
        L = math.hypot(dx, dy)
        return None if L < 1e-9 else (dx / L, dy / L)

    esquinas = []
    for i in range(n):
        u, v = _dir(i, (i - 1) % n), _dir(i, (i + 1) % n)
        if u is None or v is None:
            continue
        ang = math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))
        if ang < _ESQUINA:
            esquinas.append((i, u, v, ang))
    if not esquinas:
        return pts

    seg = [math.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1])
           for i in range(n)]

    def _arco(i, j):
        """Largo de polilínea de `i` a `j` yendo hacia adelante"""
        total, k = 0.0, i
        while k != j:
            total += seg[k]
            k = (k + 1) % n
        return total or sum(seg)

    # El recorte no puede pasar de la mitad del tramo que separa dos esquinas, o dos
    # filetes vecinos se pisan y el contorno se cruza a sí mismo.
    m = len(esquinas)
    cortes = []
    for k, (i, u, v, ang) in enumerate(esquinas):
        vecinas = 0.45 * min(_arco(esquinas[(k - 1) % m][0], i), _arco(i, esquinas[(k + 1) % m][0]))
        cortes.append(min(r / math.tan(ang / 2.0), vecinas, tope))

    fuera = []
    for k, (i, u, v, ang) in enumerate(esquinas):
        d = cortes[k]
        rad = d * math.tan(ang / 2.0)  # el radio que de verdad entró, ya acotado
        bx, by = u[0] + v[0], u[1] + v[1]
        bl = math.hypot(bx, by)
        if rad < 1e-6 or bl < 1e-9:
            fuera.append(pts[i])
        else:
            h = rad / math.sin(ang / 2.0)  # esquina → centro, sobre la bisectriz
            cen = (pts[i][0] + bx / bl * h, pts[i][1] + by / bl * h)
            t0 = math.atan2(pts[i][1] + u[1] * d - cen[1], pts[i][0] + u[0] * d - cen[0])
            t1 = math.atan2(pts[i][1] + v[1] * d - cen[1], pts[i][0] + v[0] * d - cen[0])
            giro_arco = (t1 - t0 + math.pi) % (2.0 * math.pi) - math.pi  # por el lado corto
            fuera.extend((cen[0] + rad * math.cos(t0 + giro_arco * q / n_arco),
                          cen[1] + rad * math.sin(t0 + giro_arco * q / n_arco))
                         for q in range(n_arco + 1))
        # Los vértices originales hasta la esquina siguiente, salvo los que se comen
        # este filete y el de allá.
        j, largo, i_sig, d_sig = (i + 1) % n, 0.0, esquinas[(k + 1) % m][0], cortes[(k + 1) % m]
        while j != i_sig:
            largo += seg[(j - 1) % n]
            if largo > d and _arco(j, i_sig) > d_sig:
                fuera.append(pts[j])
            j = (j + 1) % n
    return fuera


def contorno_top(forma, largo, ancho, redondeo, giro, n=128):
    """Contorno cerrado del sello visto desde arriba, ya girado. Lista de (x, y).

    `x` corre a lo largo del anillo y `y` a lo largo del dedo. Cada forma se
    dibuja en su propio marco con `largo` sobre x y `ancho` sobre y, y después se
    rota entera: por eso el giro es libre y no dos posiciones fijas.
    """
    def _crudo(a, b):
        pts = []
        if forma == 'CIRCULO':
            b = a  # un solo diámetro: `ancho` no manda
            for i in range(n):
                t = 2.0 * math.pi * i / n
                pts.append((a * math.cos(t), b * math.sin(t)))
        elif forma == 'OVALO':
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
        else:  # RECTANGULO: pelado, que `_redondear` le pone las esquinas
            pts = [(a, b), (-a, b), (-a, -b), (a, -b)]
        return pts

    def _bbox(P):
        return (max(q[0] for q in P) - min(q[0] for q in P),
                max(q[1] for q in P) - min(q[1] for q in P))

    a = max(1e-4, largo / 2.0)
    b = max(1e-4, ancho / 2.0)
    pts = _crudo(a, b)
    # `Redondeo` vale para toda forma con esquinas de polígono, no solo el rectángulo:
    # el hexágono tiene seis y el escudo dos. El óvalo y el círculo no tienen ninguna
    # y esto no hace nada. El corazón queda afuera a propósito (ver el panel): sus
    # esquinas son cúspides de 6° de una curva, no vértices de polígono, y un radio
    # ahí o no se nota o deforma la forma.
    if redondeo > 0.0 and forma != 'CORAZON':
        objetivo = _bbox(pts)
        ea, eb = a, b
        # Redondear una PUNTA la acorta: un hexágono de 12 mm con 1,2 mm de filete
        # medía 11,38. `Largo` y `Ancho del top` son medidas, no sugerencias, así que
        # se agranda el molde y se vuelve a redondear hasta que el contorno mida lo
        # pedido. Converge en un par de vueltas; el rectángulo y el escudo entran
        # derecho porque sus lados rectos ya tocan el bbox.
        for _ in range(5):
            pts = _redondear(_crudo(ea, eb), redondeo, 0.5 * min(a, b), max(2, n // 24))
            bx, by = _bbox(pts)
            if abs(bx - objetivo[0]) < 1e-4 and abs(by - objetivo[1]) < 1e-4:
                break
            ea *= objetivo[0] / max(1e-9, bx)
            eb *= objetivo[1] / max(1e-9, by)

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


def _muestras_y(cortes, n):
    """`n` alturas que SIEMPRE incluyen los `cortes`, los quiebres de la sección.

    Los quiebres tienen que ser muestras exactas o se pierden: una cara plana
    angosta —la punta del óvalo, la del hexágono girado— cae entre dos muestras y
    desaparece, y el bisel del marco se redondea.

    El cupo de cada tramo es FIJO, no proporcional a su largo: con reparto
    proporcional el índice del vértice del borde del sello cambiaba de una sección
    a la siguiente y el puenteado cíclico lo unía con un vértice interior de la
    vecina — de ahí los dientes de sierra alrededor del sello. El grueso va a los
    FLANCOS: la cara del sello y el bisel son planos y con sus bordes ya está.
    Donde un tramo mide cero las muestras caen encima y las suelda el
    `remove_doubles` del final.
    """
    libres = n - len(cortes)
    lomo = max(1, libres * 2 // 5)
    bisel = max(1, libres // 10)
    cupos = (bisel, lomo, libres - 2 * lomo - 2 * bisel, lomo, bisel)
    ys = [cortes[0]]
    for (a, b), c in zip(zip(cortes, cortes[1:]), cupos):
        ys.extend(a + (b - a) * i / (c + 1) for i in range(1, max(0, c) + 1))
        ys.append(b)
    return ys


def _seccion(perfil, r_int, y0, y1, r_ext, n_y, w_base, marco=0.0, mezcla=1.0,
             huella=None, r_placa=None, cabeza='PLANA', crown=None):
    """Contorno cerrado de la sección, en (y, radio). Siempre devuelve 2*n_y puntos.

    El conteo tiene que ser el mismo en todas las secciones o el puenteado
    cíclico no cierra.

    **El sello no es una placa puesta encima: es el PLANO que corta el cuerpo.**
    La cara sale de `min(lomo, r_placa)`, así que su contorno es la intersección
    del cuerpo con el plano y el borde no puede tener cornisa: el cuerpo cruza el
    plano con un ángulo, no con un salto.

    De adentro hacia afuera la sección tiene: **cara, marco, lomo, flanco** y
    recién el agujero. El `marco` es el bisel que bordea la cara del sello, de
    ancho propio; se apaga hacia la banda, donde manda `Perfil`. Sin él el bisel
    de la banda moría debajo del sello y dejaba una muesca en V.

    El flanco baja del punto más ancho hasta `w_base` contra el agujero con un
    cuarto de elipse tangente al lomo. En la banda `w_base` es el ancho entero y
    el flanco sale vertical —la sección de siempre—; en la cabeza el sello es
    mucho más ancho que el aro y ese desnivel se resuelve con los flancos
    inclinados, que es como se ve un sello de verdad.
    """
    grosor = max(1e-4, r_ext - r_int)
    centro = (y0 + y1) / 2.0
    medio = max(1e-6, (y1 - y0) / 2.0)
    w_b = min(max(1e-6, w_base), medio)
    # La media caña se dimensiona por el grosor de la BANDA (`crown`), no por
    # `r_ext - r_int`: bajo la placa ese grosor es la CABEZA entera —banda +
    # refuerzo + alto— y entonces subir `Alto` abombaba el lomo que rodea al sello
    # (domo de 1,40 mm con Alto 0,5 y de 2,50 mm con Alto 4). Una perilla que sube
    # el sello no puede curvar lo que tiene al lado. En la banda pura `crown` y
    # `grosor` valen lo mismo, así que ahí no cambia nada.
    cana = min((grosor if crown is None else max(1e-4, crown)) * 0.55, medio * 0.9)
    relieve = cabeza == 'RELIEVE'
    # `mezcla` vale 1 en la banda y 0 en la cara del sello: ya es el desvanecido de
    # "cuánto de esto es banda". `Perfil` manda sobre la banda y `Cabeza` sobre lo
    # que rodea al sello:
    #   PLANA    — el bulto se va con `mezcla`, así que la cara de arriba es un plano.
    #   ABOMBADA — media caña también arriba, como hasta la v0.21.0.
    #   RELIEVE  — el cuerpo ES la banda (la placa se suma aparte, ver `lomo`), así
    #              que lleva la media caña de la banda entera.
    banda = cana if perfil in ('MEDIA_CANA', 'CONFORT') else 0.0
    if cabeza == 'ABOMBADA':
        bulto = cana * (1.0 - mezcla) + banda * mezcla
    else:
        bulto = banda if relieve else banda * mezcla
    chaflan = min(grosor * 0.35, medio * 0.35) * mezcla if perfil == 'BISELADO' else 0.0
    # El interior de confort NO se apaga bajo el sello: es la superficie que toca
    # el dedo y tiene que ser igual en toda la vuelta.
    confort = min(0.25, grosor * 0.2) if perfil == 'CONFORT' else 0.0
    borde = max(0.0, 1.0 - chaflan / medio) if chaflan else 1.0

    if huella:
        q0 = min(max(huella[0], y0), y1)
        q1 = min(max(huella[1], y0), y1)
    else:  # sin sello no hay plano que corte, y la cara plana es un punto al medio
        q0 = q1 = centro
        r_placa = None
    base = r_ext if r_placa is None or relieve else r_placa
    # El marco baja a 45°. Ni él ni el bulto ni el chaflán pueden comerse la
    # sección: se SUMAN en el lomo, y en una cabeza fina y ancha —un sello de 10 mm
    # sobre una banda de 1,6 mm de grosor— llegaban a apoyarse contra el agujero y
    # el costado salía en escalones.
    # En relieve el marco bordea la placa y no el canto de la sección (ver `lomo`).
    hondo = 0.0 if relieve else marco
    sobra = (base - r_int) * 0.85 / max(1e-9, hondo + bulto + chaflan)
    if sobra < 1.0:
        hondo, bulto, chaflan = hondo * sobra, bulto * sobra, chaflan * sobra
    # El sello puede ser asimétrico (giro, corazón, escudo), así que cada mitad se
    # resuelve por su cuenta. Las dos entran al eje con pendiente 0, así que ahí no
    # queda arruga.
    eje = (q0 + q1) / 2.0
    mitades = []
    for q, w in ((q1 - eje, max(1e-9, y1 - eje)), (eje - q0, max(1e-9, eje - y0))):
        # El marco va SIEMPRE pegado al canto de la sección, no al borde del sello:
        # bajo el sello los dos coinciden porque la sección es la huella más el
        # marco, pero pasado el borde el sello ya no existe y anclarlo ahí dejaba
        # la cinta corriendo por el MEDIO del hombro, con una muesca donde se
        # topaba con la del sello. Pegada al canto, es una sola cinta.
        m = min(marco, max(0.0, w - q))
        t = min(1.0, q / w)
        mitades.append((w, m, t, min(1.0, (w - m) / w), math.sqrt(max(0.0, 1.0 - t * t))))

    def lomo(y):
        i = 0 if y >= eje else 1
        w, m, t, s_m, arco = mitades[i]
        v = min(1.0, abs(y - eje) / w)
        r = base
        if arco > 1e-6 and v > t:
            r -= bulto * arco * arco * (1.0 - math.sqrt(max(0.0, 1.0 - v * v)) / arco)
        u = (v - s_m) / max(1e-9, 1.0 - s_m)
        if v > s_m:
            r -= hondo * u
            # El chaflán del perfil se mide DESDE el marco, no desde el eje: si no,
            # en un sello asimétrico entra por debajo de la cara plana y se la come.
            r -= chaflan * max(0.0, u - borde) / max(1e-9, 1.0 - borde)
        r = max(r, r_int + 0.02)
        if r_placa is None:
            return r
        if not relieve:
            return min(r, r_placa)
        # El relieve: la placa se para SOBRE el cuerpo donde la huella la tapa, con
        # el marco biselando su borde hacia adentro. Afuera manda el cuerpo, y el
        # salto entre los dos es la pared del sello.
        # El marco se suma AFUERA de la huella, igual que en los otros dos modos:
        # la cara del sello conserva la medida que pide la perilla y el bisel la
        # bordea. Metiéndolo hacia adentro, un marco de 0,6 se comía entera la cara
        # de un sello de 1 mm.
        if q0 - marco <= y <= q1 + marco:
            d = min(y - q0 + marco, q1 + marco - y)
            return max(r, r_placa - marco + min(marco, d))
        return r

    n_lado = max(3, n_y // 2)
    n_hueco = max(2, n_y // 3)
    if relieve:
        # El marco bordea la huella, así que sus quiebres son los del sello y no los
        # del canto de la sección.
        cortes = (y0, max(y0, q0 - marco), q0, q1, min(y1, q1 + marco), y1)
    else:
        cortes = (y0, eje - mitades[1][3] * mitades[1][0], q0, q1,
                  eje + mitades[0][3] * mitades[0][0], y1)
    ys = _muestras_y(cortes, 2 * n_y - n_hueco - 2 * n_lado)
    if relieve:
        # Dos muestras pegadas por AFUERA del borde de la huella: sin ellas el salto
        # de la placa al cuerpo se reparte sobre el primer tramo libre —casi un
        # milímetro— y la pared del relieve sale como un chaflán. Van en TODAS las
        # secciones (sin sello caen sobre el centro y no molestan) porque el
        # puenteado cíclico exige el mismo conteo de vértices en todas.
        ys = sorted(ys + [max(y0, q0 - marco - 1e-4), min(y1, q1 + marco + 1e-4)])

    def flanco(y_ext, hacia_arriba):
        """Cuarto de elipse entre el punto más ancho del lomo y el agujero.

        Tangente vertical del lado del lomo, así que el punto más ancho del anillo
        no es una arista: es un máximo suave, como en la referencia.

        Muestreado por ÁNGULO y no por altura: con altura, en una cabeza fina y
        ancha —el sello sobresale 3 mm a cada lado y la pared mide 0,3— todo el
        recorrido en Y caía en el último tramo y el costado salía en escalones.
        """
        signo = 1.0 if y_ext >= centro else -1.0
        r_borde = lomo(y_ext)
        ancho = abs(y_ext - centro) - w_b
        pasos = range(n_lado, 0, -1) if hacia_arriba else range(1, n_lado + 1)
        return [(centro + signo * (w_b + ancho * math.cos(f)),
                 r_borde - (r_borde - r_int) * math.sin(f))
                for f in (i / n_lado * math.pi / 2.0 for i in pasos)]

    pts = flanco(y0, True) + [(y, lomo(y)) for y in ys] + flanco(y1, False)
    for i in range(1, n_hueco + 1):  # el agujero, de vuelta y sin repetir los bordes
        y = centro + w_b - 2.0 * w_b * i / (n_hueco + 1)
        u = abs(y - centro) / max(1e-9, w_b)
        pts.append((y, r_int + confort * (1.0 - math.sqrt(max(0.0, 1.0 - u * u)))))
    return pts


def construir(p):
    """bmesh cerrado del anillo descrito por `p` (un SIRO_PG_ring).

    Devuelve `(bm, huella_partida)`: lo segundo avisa que el sello elegido no se
    puede representar a este ángulo.
    """
    r_int = DIAMETRO[p.talla] / 2.0

    def w_banda(a):
        """Semiancho de la banda en ese ángulo.

        `afinado` la adelgaza hacia el fondo del aro y la deja entera arriba, así
        que `Ancho` sigue significando el ancho bajo el sello — la medida que se
        mira. Es el mismo criterio que `Refuerzo` con `Grosor`."""
        return p.ancho / 2.0 * (1.0 - p.afinado * (1.0 - math.cos(a)) / 2.0)

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
    y0_top = y1_top = z_placa = 0.0
    if con_top:
        contorno = contorno_top(p.top, p.top_largo, p.top_ancho, p.redondeo, p.giro)
        x_min = min(q[0] for q in contorno)
        x_max = max(q[0] for q in contorno)
        eps = 1e-6 * max(1e-4, x_max - x_min)
        z_placa = r_banda(0.0) + p.top_alto
        # Los extremos del contorno: es lo que `masa` sostiene alrededor del sello.
        y0_top = min(q[1] for q in contorno)
        y1_top = max(q[1] for q in contorno)

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
            # La huella EN el borde: pasado `lim` el sello deja de existir, pero
            # el ancho no puede caer de golpe de ahí a nada. El rectángulo llega al
            # borde con 6 mm de huella y ese salto era un vértice en planta.
            b0, b1 = _huella(s * x_ext)
            lados[s] = (lim, a_t, r0, -b0, b1)
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
        # Ángulo con signo al tope. Sin el `%`: sumar y restar π le comía un ulp a
        # `th`, y el borde del sello —que se metió como paso EXACTO— caía del lado
        # de afuera. El escudo girado 90° perdía la sección del borde entera y
        # dejaba 1,5 mm de escalón. Tercera vez que un ulp muerde en este archivo.
        d = th if th <= math.pi else th - 2.0 * math.pi
        a = abs(d)
        huella = r_placa = None
        mezcla, marco = 1.0, 0.0
        w_b = w_banda(a)
        if not con_top:
            y0, y1, r_ext = -w_b, w_b, r_banda(a)
        else:
            lim, a_t, r0, borde0, borde1 = lados[1 if d >= 0 else -1]
            if p.cabeza == 'RELIEVE':
                # El sello deja de ser una cabeza con hombros y pasa a ser un
                # relieve parado sobre la banda: el cuerpo es la banda de siempre y
                # la placa se SUMA encima donde la huella la tapa. Por eso la pared
                # sale vertical en todo el contorno —los extremos incluidos— y no
                # hay hombro que `Masa` o `Cintura` puedan mover.
                r_ext = r_banda(a)
                if a <= lim + 1e-9:
                    huella = _huella(z_placa * math.tan(d))
                    r_placa = z_placa / math.cos(a)
                    marco = p.marco
                    k = min(SUAVIZADO_PLANTA, w_b)
                    y0 = -_maximo_suave(-huella[0] + marco, w_b, k)
                    y1 = _maximo_suave(huella[1] + marco, w_b, k)
                else:
                    y0, y1 = -w_b, w_b
            elif a >= a_t:
                y0, y1, r_ext = -w_b, w_b, r_banda(a)
            else:
                mezcla = _suave(a / a_t)
                r_placa = z_placa / math.cos(a)
                # El anillo es tan ancho como el sello donde el sello es ancho, y
                # como la banda donde no: en planta el contorno ABRAZA la forma en
                # vez de mantener un ladrillo del ancho del sello hasta el borde.
                # `masa` sostiene el ancho entero del sello el primer tramo —el
                # bloque macizo de los sellos clásicos— y después lo suelta.
                sost = 0.0 if masa <= 0.0 else 1.0 - _suave(min(1.0, a / a_t / masa))
                if a <= lim + 1e-9:  # holgura por el ulp del paso exacto del borde
                    # El marco mide lo que dice la perilla en TODO el contorno del
                    # sello. Desvanecerlo con `mezcla` —que ya vale 0,34 en el borde—
                    # lo dejaba en 0,395 de los 0,600 pedidos justo en la punta, y
                    # como `mezcla` no es lineal en θ también curvaba el contorno.
                    marco = p.marco
                    huella = _huella(z_placa * math.tan(d))
                    # La cresta del cuerpo sale del plano del sello. En `lim`
                    # coincide con la tangente por construcción —la recta se trazó
                    # justo por ahí— y ahí es donde muere el escalón.
                    r_ext = r_placa
                    alto0, alto1 = -huella[0], huella[1]
                else:
                    r_placa = None
                    uu = (a - lim) / (a_t - lim)
                    suelta = 1.0 - _suave(uu)
                    alto0, alto1 = borde0 * suelta, borde1 * suelta
                    # El desvanecido del marco va acá, en el hombro: sin él el bisel
                    # de la banda muere bajo el sello y deja una muesca en V. En `lim`
                    # vale `p.marco` como la rama de arriba y en `a_t` llega a 0.
                    marco = p.marco * suelta
                    recta = r0 / math.cos(a_t - a)
                    # `cintura` tira la recta hacia la banda con un bombo que vale
                    # 0 en los dos extremos: ni el borde del sello ni el punto de
                    # tangencia se mueven, así no se pierde la continuidad.
                    r_ext = recta - p.cintura * (recta - r_banda(a)) * math.sin(math.pi * uu)
                    r_ext = max(r_ext, r_banda(a))
                    # Pasado el borde la huella no desaparece de golpe: se achica.
                    # Si no, el lomo pasa de estar sostenido casi hasta el canto a
                    # ser una media caña entera, y eso es una cornisa de 2,7 mm —
                    # el rectángulo llega al borde con la huella casi entera.
                    huella = (-alto0, alto1)
                # El marco se suma AFUERA de la huella: la cara del sello
                # conserva la medida que pide la perilla y el bisel la bordea.
                k = min(SUAVIZADO_PLANTA, w_b)
                y0 = -_maximo_suave(max(alto0, -y0_top * sost) + marco, w_b, k)
                y1 = _maximo_suave(max(alto1, y1_top * sost) + marco, w_b, k)
        r_max = max(r_ext, r_int + 0.05)
        # `pared`: cuánto baja recta la pared de la cabeza bajo el contorno del
        # sello antes de afinarse hacia la banda. En 0 la cabeza es un cono y el
        # aro no llega a cubrir el borde de la forma; en 1 baja a plomo.
        base_y = w_b + ((y1 - y0) / 2.0 - w_b) * p.pared
        sec = _seccion(p.perfil, r_int, y0, y1, r_max, n_y, base_y, marco, mezcla,
                       huella, r_placa if r_placa is not None else
                       (r_max if huella else None), p.cabeza, r_banda(a) - r_int)
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
    # Donde un tramo de la sección mide cero —la placa llena la sección entera—
    # las muestras de cupo fijo caen encima y dejan caras de área cero.
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # `recalc` deja las normales coherentes pero elige el lado de afuera con una
    # heurística, y a veces se equivoca: el corazón biselado salía con la malla
    # dada vuelta y volumen negativo, que es lo que el resto del pipeline usa para
    # decidir si una pieza sirve. En un cerrado manifold el signo del volumen NO
    # es una heurística, así que manda él.
    volumen = bm.calc_volume(signed=True)
    if volumen < 0.0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    # Sombreado suave con las aristas vivas marcadas. No es cosmético: el anillo
    # es una superficie barrida y en plano se ve como una escalera de facetas —
    # tres pasadas se fueron persiguiendo "escalones" que en la malla no existían.
    # Las aristas de verdad (la cara del sello, los dos bordes del marco, el canto
    # del aro) se marcan y siguen saliendo vivas.
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > 0.35:  # 20°
            e.smooth = False
    return bm, partida, abs(volumen)


def _reconstruir(self, context):
    """Callback de cada propiedad. El objeto dueño sale de `id_data`, no del contexto:
    el panel puede estar dibujando otro objeto cuando esto corre."""
    obj = self.id_data
    if not self.activo or obj is None or obj.type != 'MESH':
        return
    bm, partida, volumen = construir(self)
    bm.to_mesh(obj.data)  # la misma malla: conserva transform, materiales y selección
    bm.free()
    obj.data.update()
    # Ojo con el acceso crudo: `self.aviso_huella = ...` volvería a disparar el
    # callback `update=` y entraría en bucle. Escribir por clave toca la
    # ID-property directo y no dispara nada.
    self["aviso_huella"] = partida
    # `calc_volume` mide la malla LOCAL: si el objeto está escalado, el peso real no
    # es ése. El determinante de la matriz de mundo es el factor de escala al cubo,
    # que es justo lo que hay que multiplicar.
    self["volumen"] = volumen * abs(obj.matrix_world.determinant())


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
    pared: bpy.props.FloatProperty(
        name="Pared",
        description="Cuánto baja a plomo la pared de la cabeza bajo el contorno del sello. "
                    "En 0 la cabeza se afina hasta el ancho de la banda y el aro no llega a "
                    "cubrir el borde de la forma; en 1 baja recta",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR', update=_reconstruir,
    )
    cabeza: bpy.props.EnumProperty(
        name="Cabeza",
        description="Qué es la cara de arriba de la cabeza por fuera de la huella del sello",
        items=CABEZAS, default='PLANA', update=_reconstruir,
    )
    afinado: bpy.props.FloatProperty(
        name="Afinado",
        description="Adelgaza la banda hacia el fondo del aro. `Ancho` sigue siendo el ancho "
                    "bajo el sello, igual que `Grosor` es el fondo del aro",
        default=0.0, min=0.0, max=0.7, subtype='FACTOR', update=_reconstruir,
    )
    marco: bpy.props.FloatProperty(
        name="Marco",
        description="Ancho del bisel que bordea la cara del sello y baja por los hombros. "
                    "En 0 el sello va a canto vivo. La cara conserva Largo × Ancho: el marco va por afuera",
        default=0.6, min=0.0, soft_max=3.0, unit='LENGTH', update=_reconstruir,
    )
    redondeo: bpy.props.FloatProperty(
        name="Redondeo",
        description="Radio de las esquinas del sello. Exacto en el rectángulo, el hexágono "
                    "y el canto del escudo. Sin efecto en óvalo, círculo y corazón",
        default=1.5, min=0.0, soft_max=8.0, unit='LENGTH', update=_reconstruir,
    )
    giro: bpy.props.FloatProperty(
        name="Giro", description="Gira el sello sobre la cara del anillo. 90° pone a lo ancho lo que estaba a lo largo",
        default=0.0, min=-math.pi, max=math.pi, subtype='ANGLE', update=_reconstruir,
    )
    masa: bpy.props.FloatProperty(
        name="Masa", description="Cuánto sostiene el hombro el ancho del sello, medido desde el tope del anillo, antes de cerrarse hacia la banda. Sube para el bloque macizo de los sellos clásicos",
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
    volumen: bpy.props.FloatProperty(
        name="Volumen", description="mm³ de la última reconstrucción", default=0.0,
        options={'HIDDEN'},
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
