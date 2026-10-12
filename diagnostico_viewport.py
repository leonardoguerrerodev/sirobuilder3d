"""SiroBuilder - diagnostico del fantasma en TU sesion real de Blender.

Los tests headless ya dieron TODO OK: el modificador marca bien las caras. Lo
que ellos no pueden ver es lo que pasa con TU pieza real y en TU viewport. Este
script solo LEE (no cambia nada de la escena) y mide justo eso:

  - si el plano atraviesa de verdad la pieza o nace en su borde (hipotesis 5)
  - cuantas caras fantasma salen en la pieza real, y cuanto tarda
  - la pila de modificadores y los slots de material de la pieza
  - el shading de cada viewport: Solid/Material Preview, Color, X-Ray (hip. 3)
  - el material fantasma y el color de fondo (hip. 4)

Como correrlo, en la interfaz de Blender:
  1. Abre tu .blend con la pieza real.
  2. Selecciona la pieza y pulsa "Anadir plano de corte" del addon, como siempre.
     NO muevas el plano: queremos verlo donde nace.
  3. Cambia un area a "Text Editor" > Open > este archivo > Run Script (Alt+P).
  4. El resultado queda en ~/diag_viewport.txt y en el texto "diag_viewport".
     Pasamelo. Si puedes, una captura del viewport tal como lo ves.
  5. Opcional: mueve el plano al medio de la pieza y corre el script otra vez.

No guardes el .blend despues: el script crea un bloque de texto "diag_viewport".
"""

import os
import time
import traceback

import bpy
from mathutils import Vector

CUTTER = "SiroCutter"
MOD = "SiroGhostPreview"
GHOST = "SiroGhostFantasma"

L = []
PISTAS = []


def log(*a):
    L.append(" ".join(str(x) for x in a))


def pista(texto):
    PISTAS.append(texto)


def seccion(titulo, fn):
    log("")
    log("=" * 70)
    log(titulo)
    log("=" * 70)
    try:
        fn()
    except Exception:  # noqa: BLE001
        log("!!! excepcion en esta seccion:")
        log(traceback.format_exc())


def redondear(v, n=3):
    try:
        return tuple(round(x, n) for x in v)
    except TypeError:
        return round(v, n)


def leer_inputs(mod):
    out = {}
    ng = getattr(mod, "node_group", None)
    if ng is None:
        return {"node_group": None}
    for it in ng.interface.items_tree:
        if it.item_type != 'SOCKET' or it.in_out != 'INPUT':
            continue
        try:
            if hasattr(mod, "properties"):
                v = getattr(mod.properties.inputs, it.identifier).value
            else:
                v = mod[it.identifier]
        except Exception as e:  # noqa: BLE001
            v = f"<error {type(e).__name__}: {e}>"
        if hasattr(v, "name"):
            v = f"objeto '{v.name}'"
        elif hasattr(v, "__len__") and not isinstance(v, str):
            v = redondear(v)
        out[it.name] = v
    return out


# ---------------------------------------------------------------- secciones

def s_entorno():
    log(f"Blender {bpy.app.version_string}")
    log(f"archivo: {bpy.data.filepath or '(sin guardar)'}")
    log(f"Auto Run Python Scripts: {'ON' if bpy.context.preferences.filepaths.use_scripts_auto_execute else 'OFF'}")
    log(f"modo actual: {bpy.context.mode}")
    ao = bpy.context.active_object
    log(f"objeto activo: {ao.name if ao else None}")
    log(f"unidades: scale_length={bpy.context.scene.unit_settings.scale_length}")


def encontrar():
    cutters = [o for o in bpy.data.objects if o.name.startswith(CUTTER)]
    targets = [o for o in bpy.data.objects if o.type == 'MESH' and MOD in o.modifiers]
    return cutters, targets


def s_objetos():
    cutters, targets = encontrar()
    log(f"objetos '{CUTTER}*': {[o.name for o in cutters]}")
    log(f"piezas con modificador {MOD}: {[o.name for o in targets]}")
    if not cutters:
        pista("No hay SiroCutter: pulsa 'Anadir plano de corte' antes de correr el script.")
        return
    if not targets:
        pista("No hay ninguna pieza con el modificador fantasma: el boton no lo puso.")
    c = bpy.data.objects.get(CUTTER) or cutters[0]
    log(f"\nPLANO '{c.name}':")
    log(f"  posicion mundo : {redondear(c.matrix_world.translation)}")
    log(f"  rotacion (euler): {redondear(c.rotation_euler)}  escala: {redondear(c.scale)}")
    log(f"  vertices        : {len(c.data.vertices)} (22 = ya trae la flecha de la v0.26.0; 4 = version vieja)")
    log(f"  visible         : hide_viewport={c.hide_viewport} hide_get={c.hide_get()} visible_get={c.visible_get()}")
    log(f"  show_transparent={c.show_transparent} show_in_front={c.show_in_front} display_type={c.display_type}")
    log(f"  padre={c.parent.name if c.parent else None}  constraints={[k.type for k in c.constraints]}")
    if len(cutters) > 1:
        pista(f"Hay {len(cutters)} objetos SiroCutter*: sobran planos de intentos anteriores.")


def s_pieza():
    cutters, targets = encontrar()
    for t in targets:
        log(f"\nPIEZA '{t.name}':")
        log(f"  caras en la malla base: {len(t.data.polygons):,}")
        log(f"  modo del objeto: {t.mode}")
        log(f"  visible         : hide_viewport={t.hide_viewport} hide_get={t.hide_get()} visible_get={t.visible_get()}")
        log(f"  display_type={t.display_type}  show_transparent={t.show_transparent}  color={redondear(t.color)}")
        if t.display_type != 'TEXTURED':
            pista(f"display_type de la pieza es {t.display_type}: con eso Blender no dibuja materiales.")
        if t.mode == 'EDIT':
            pista("La pieza esta en Modo Edicion: el fantasma solo se ve en Modo Objeto.")
        log("  pila de modificadores (en orden):")
        for i, m in enumerate(t.modifiers):
            log(f"    {i}: {m.name:<22} tipo={m.type:<10} viewport={m.show_viewport} edit={m.show_in_editmode} render={m.show_render}")
            if m.name == MOD:
                log(f"       grupo de nodos: {m.node_group.name if m.node_group else None}")
                log(f"       inputs: {leer_inputs(m)}")
                if not m.show_viewport:
                    pista("El modificador fantasma tiene el ojo (viewport) APAGADO.")
        if t.animation_data and t.animation_data.drivers:
            log(f"  drivers en la pieza: {len(t.animation_data.drivers)} (la v0.26.0 no deberia dejar ninguno)")
        log("  slots de material:")
        for i, s in enumerate(t.material_slots):
            log(f"    {i}: link={s.link:<6} material={s.material.name if s.material else None}")
        if len(t.material_slots) != len(t.data.materials):
            pista("Los slots del objeto y los de la malla no coinciden: revisar 'link' de los slots.")


def s_material():
    m = bpy.data.materials.get(GHOST)
    if m is None:
        log(f"No existe el material {GHOST}")
        pista("No existe el material fantasma.")
        return
    log(f"material {GHOST}: usuarios={m.users}")
    log(f"  diffuse_color (lo que usa Solid) = {redondear(m.diffuse_color)}")
    if hasattr(m, "surface_render_method"):
        log(f"  surface_render_method = {m.surface_render_method}")
    if hasattr(m, "blend_method"):
        log(f"  blend_method = {m.blend_method}")
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                log(f"  Principled: Base Color={redondear(n.inputs['Base Color'].default_value)} Alpha={round(n.inputs['Alpha'].default_value, 3)}")
    a = m.diffuse_color[3]
    if a < 0.2:
        pista(f"El alfa del fantasma en Solid es {a:.2f}: sobre fondo claro casi no se distingue (hip. 4). "
              "El alfa 0.25 de la v0.26.0 solo aplica a materiales NUEVOS; este ya existia en el archivo.")


def s_evaluado():
    cutters, targets = encontrar()
    c = bpy.data.objects.get(CUTTER)
    for t in targets:
        bpy.context.view_layer.update()
        t0 = time.perf_counter()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = t.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            total = len(me.polygons)
            ghost_idx = next((i for i, m in enumerate(t.data.materials) if m and m.name == GHOST), None)
            attr = me.attributes.get("material_index")
            cuentas = {}
            if attr is not None and total:
                try:
                    import numpy as np
                    arr = np.empty(total, dtype=np.int32)
                    attr.data.foreach_get("value", arr)
                    vals, cnt = np.unique(arr, return_counts=True)
                    cuentas = {int(v): int(n) for v, n in zip(vals, cnt)}
                except ImportError:
                    vals = [0] * total
                    attr.data.foreach_get("value", vals)
                    for v in vals:
                        cuentas[v] = cuentas.get(v, 0) + 1
            dt = time.perf_counter() - t0
            n_ghost = cuentas.get(ghost_idx, 0) if ghost_idx is not None else -1
            log(f"PIEZA '{t.name}': caras evaluadas={total:,}  slot fantasma={ghost_idx}")
            log(f"  caras por indice de material: {cuentas}")
            log(f"  CARAS FANTASMA = {n_ghost:,} de {total:,} ({(n_ghost / total if total else 0):.1%})")
            log(f"  reevaluar el modificador tardo {dt * 1000:.0f} ms")
            if ghost_idx is None:
                pista("La pieza no tiene el material fantasma en sus slots.")
            elif n_ghost == 0:
                pista("0 caras fantasma en la pieza REAL: nada que dibujar (ver si el plano atraviesa la pieza).")
            elif n_ghost == total:
                pista("TODAS las caras son fantasma: el plano esta del lado equivocado o fuera de la pieza.")

            # el plano contra la caja de la pieza evaluada
            if c is not None:
                mw = ev.matrix_world
                co = c.matrix_world.translation
                no = (c.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
                dist = [(mw @ Vector(p) - co).dot(no) for p in ev.bound_box]
                lo, hi = min(dist), max(dist)
                log("\n  plano vs caja de la pieza (distancia con signo a lo largo de la normal):")
                log(f"    minimo={lo:.4f}  maximo={hi:.4f}  (la pieza mide {hi - lo:.4f} en esa direccion)")
                if lo < 0 < hi:
                    log(f"    el plano ATRAVIESA la caja, a {(-lo) / (hi - lo):.0%} de su extension")
                else:
                    log("    el plano NO atraviesa la caja de la pieza")
                    pista("El plano esta fuera de la pieza o rozando su borde (hip. 5): mueve el plano adentro.")
                centro = sum((mw @ Vector(p) for p in ev.bound_box), Vector()) / 8.0
                origen = mw.translation
                log(f"    origen de la pieza={redondear(origen)}  centro de la caja={redondear(centro)}  "
                    f"distancia={(origen - centro).length:.4f}")
                if hi > lo and (origen - centro).length > 0.25 * (hi - lo):
                    pista("El origen de la pieza esta lejos del centro de su caja. El plano nace en el ORIGEN, "
                          "asi que probablemente nace en un borde (hip. 5).")
        finally:
            ev.to_mesh_clear()


def s_viewports():
    n = 0
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for sp in area.spaces:
                if sp.type != 'VIEW_3D':
                    continue
                n += 1
                sh = sp.shading
                log(f"viewport #{n} (pantalla '{win.screen.name}'):")
                log(f"  shading.type       = {sh.type}   (SOLID / MATERIAL = Material Preview / RENDERED / WIREFRAME)")
                if sh.type == 'SOLID':
                    log(f"  color_type         = {sh.color_type}   (debe ser MATERIAL)")
                    log(f"  light              = {sh.light}   show_xray={sh.show_xray}")
                    log(f"  background_type    = {sh.background_type}")
                    if sh.color_type != 'MATERIAL':
                        pista(f"Viewport #{n}: Solid con Color = {sh.color_type}. Blender ignora el color y el alfa del "
                              "material: los dos lados se ven iguales (hip. 3).")
                    if sh.show_xray:
                        pista(f"Viewport #{n}: X-Ray activo; cambia como se ve la transparencia.")
                elif sh.type == 'MATERIAL':
                    log("  (Material Preview: usa el shader del material, no diffuse_color)")
                log(f"  overlays visibles  = {sp.overlay.show_overlays}")
    if n == 0:
        log("No encontre ningun viewport 3D abierto.")
    try:
        th = bpy.context.preferences.themes[0].view_3d.space.gradients
        log(f"\ncolor de fondo del tema (arriba) = {redondear(th.high_gradient)}  tipo={th.background_type}")
    except Exception as e:  # noqa: BLE001
        log(f"\n(no pude leer el fondo del tema: {type(e).__name__})")


def main():
    seccion("A. ENTORNO", s_entorno)
    seccion("B. PLANO", s_objetos)
    seccion("C. PIEZA", s_pieza)
    seccion("D. MATERIAL FANTASMA", s_material)
    seccion("E. LO QUE EVALUA EL MODIFICADOR EN LA PIEZA REAL", s_evaluado)
    seccion("F. VIEWPORTS", s_viewports)

    log("")
    log("=" * 70)
    log("PISTAS AUTOMATICAS (hipotesis, no certezas)")
    log("=" * 70)
    if PISTAS:
        for p in PISTAS:
            log(f"- {p}")
    else:
        log("Ninguna: el modificador marca caras, el plano atraviesa la pieza y el shading parece correcto.")
        log("Si aun asi no ves el fantasma, necesito la captura del viewport.")

    texto = "\n".join(L) + "\n"
    print(texto)
    blk = bpy.data.texts.get("diag_viewport") or bpy.data.texts.new("diag_viewport")
    blk.clear()
    blk.write(texto)
    ruta = os.path.join(os.path.expanduser("~"), "diag_viewport.txt")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f">> Guardado en {ruta}")
    except OSError as e:
        print(f">> No pude escribir {ruta}: {e}")


main()
