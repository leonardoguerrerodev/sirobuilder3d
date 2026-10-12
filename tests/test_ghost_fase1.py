"""SiroBuilder - Fase 1: el fantasma aparece SIN drivers y SIN auto-ejecucion.

Uso (desde la raiz del repo, la carpeta que contiene `sirobuilder/`):

    blender -b --python tests/test_ghost_fase1.py

Sale con codigo 0 si todo pasa y 1 si algo falla. Correrlo SIN --enable-autoexec
es justamente el punto: con la version vieja (drivers) falla, con la nueva pasa.

Romperlo a proposito (regla de la bitacora: un test que nunca fallo no prueba
nada). Con el arbol limpio:

    git checkout 702c029 -- sirobuilder      # version con drivers
    blender -b --python tests/test_ghost_fase1.py     # DEBE fallar
    git checkout HEAD -- sirobuilder         # volver a la nueva
    blender -b --python tests/test_ghost_fase1.py     # DEBE pasar
"""

import math
import os
import sys
import traceback

import bpy
from mathutils import Vector

RAIZ = os.environ.get("SIRO_REPO", os.getcwd())
sys.path.insert(0, RAIZ)

FALLOS = []


def check(nombre, ok, detalle=""):
    print(f"  [{'OK ' if ok else 'FALLA'}] {nombre} {detalle}")
    if not ok:
        FALLOS.append(nombre)


def contar_fantasma(obj):
    from sirobuilder.operators import ghost_preview as gp
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        total = len(me.polygons)
        idx = next((i for i, m in enumerate(obj.data.materials)
                    if m is not None and m.name == gp.GHOST_MAT_NAME), None)
        attr = me.attributes.get("material_index")
        if idx is None or attr is None:
            return 0, total
        vals = [0] * total
        attr.data.foreach_get("value", vals)
        return sum(1 for v in vals if v == idx), total
    finally:
        ev.to_mesh_clear()


def frac(obj):
    n, t = contar_fantasma(obj)
    return (n / t if t else 0.0), n, t


def cerca(valor, esperado, tol=0.01):
    return abs(valor - esperado) < tol


def oraculo(pieza, plano):
    """Fraccion de caras al otro lado del plano, calculada en Python puro sobre
    el mesh ORIGINAL (centro de cada cara -> mundo, dot con la normal). No usa
    nodos, asi que es una vara independiente para el modificador.

    Se compara por cara, no por area: una esfera UV tiene caras mas chicas
    hacia los polos, y a z=+-0.5 da 67 %/33 % y no 75 %/25 %."""
    mw = pieza.matrix_world
    co = plano.matrix_world.translation
    no = (plano.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    polys = pieza.data.polygons
    n = sum(1 for p in polys if (mw @ p.center - co).dot(no) < 0.0)
    return n / len(polys)


def main():
    from sirobuilder.operators import cut, ghost_preview as gp

    print(f"Blender {bpy.app.version_string}")
    auto = bpy.context.preferences.filepaths.use_scripts_auto_execute
    print(f"Auto Run Python Scripts: {'ON' if auto else 'OFF'}")
    if auto:
        print("AVISO: el test vale mas con la auto-ejecucion OFF (no pases --enable-autoexec)")

    try:
        bpy.utils.register_class(cut.SIRO_OT_add_cut_plane)
    except ValueError:
        pass
    # la version vieja necesitaba esto; la nueva ya no existe
    if hasattr(gp, "register_driver_function"):
        gp.register_driver_function()

    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=1.0)
    pieza = bpy.context.active_object
    pieza.name = "Pieza"
    bpy.ops.siro.add_cut_plane()
    plano = bpy.data.objects[cut.CUTTER_NAME]

    print("\n[1] Sin Python en el camino")
    ad = pieza.animation_data
    ndr = len(ad.drivers) if ad else 0
    check("la pieza no tiene drivers", ndr == 0, f"({ndr} drivers)")
    check("hay modificador fantasma", gp.MODIFIER_NAME in pieza.modifiers)
    check("el plano tiene flecha (mas de 4 vertices)", len(plano.data.vertices) > 4,
          f"({len(plano.data.vertices)} vertices)")

    print("\n[2] El fantasma sigue al plano (contra el oraculo en Python puro)")

    def contra_oraculo(nombre):
        bpy.context.view_layer.update()
        f, n, t = frac(pieza)
        esp = oraculo(pieza, plano)
        check(nombre, (n > 0 or esp == 0) and cerca(f, esp),
              f"fantasma {n}/{t} = {f:.1%}, oraculo {esp:.1%}")

    for nombre, z in (("plano en el origen", 0.0), ("plano z=+0.5", 0.5), ("plano z=-0.5", -0.5)):
        plano.location.z = z
        contra_oraculo(nombre)

    plano.location.z = 0.0
    plano.rotation_euler.x = math.radians(90)
    contra_oraculo("plano girado 90 grados")

    plano.rotation_euler.x = math.radians(180)  # normal hacia -Z: se invierte
    plano.location.z = 0.5
    contra_oraculo("normal invertida (plano z=+0.5, normal -Z)")
    plano.rotation_euler.x = 0.0

    print("\n[3] Controles (el contador tiene que poder dar 0 % y 100 %)")
    plano.location.z = 100.0
    bpy.context.view_layer.update()
    check("plano muy arriba = todo fantasma", frac(pieza)[0] > 0.99)
    plano.location.z = -100.0
    bpy.context.view_layer.update()
    check("plano muy abajo = nada de fantasma", frac(pieza)[0] < 0.01)

    print("\n[4] La pieza tambien se mueve (la transform de la pieza cuenta)")
    plano.location.z = 0.0
    pieza.location.z = 1.0
    contra_oraculo("pieza desplazada +1 en Z")
    pieza.location.z = 0.5
    contra_oraculo("pieza desplazada +0.5 en Z")
    pieza.location.z = 0.0

    print("\n[5] Guardar, reabrir y volver a medir (sin handler que reponga nada)")
    plano.location.z = 0.5
    bpy.context.view_layer.update()
    ruta = os.path.join(bpy.app.tempdir or "/tmp", "siro_fase1.blend")
    bpy.ops.wm.save_as_mainfile(filepath=ruta)
    bpy.ops.wm.open_mainfile(filepath=ruta)
    pieza = bpy.data.objects["Pieza"]
    plano = bpy.data.objects[cut.CUTTER_NAME]
    contra_oraculo("tras reabrir, plano z=+0.5")

    print("\n[6] Limpieza")
    gp.remove_all_ghost_previews(bpy.context)
    check("modificador fuera", gp.MODIFIER_NAME not in pieza.modifiers)
    check("slots de material como al principio", len(pieza.data.materials) == 0,
          f"({len(pieza.data.materials)} slots)")
    check("sin drivers colgando", not (pieza.animation_data and pieza.animation_data.drivers))


try:
    main()
except Exception:  # noqa: BLE001
    traceback.print_exc()
    FALLOS.append("excepcion")

print("\n" + ("TODO OK" if not FALLOS else f"FALLARON: {FALLOS}"))
sys.exit(0 if not FALLOS else 1)
