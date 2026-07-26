# Correr con: blender -b -P test_clip_plane.py
import pathlib
import sys

import bmesh
import bpy

sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
import addon_utils

try:
    addon_utils.disable("bl_ext.user_default.sirobuilder", default_set=False)
except Exception:
    pass

import sirobuilder

sirobuilder.register()

bpy.ops.mesh.primitive_cube_add(size=2)  # cubo z en [-1, 1]
cube = bpy.context.active_object

bpy.ops.siro.add_cut_plane()
cutter = bpy.data.objects["SiroCutter"]
ghost_mod = cube.modifiers.get("SiroGhostPreview")
assert ghost_mod is not None and ghost_mod.type == 'NODES', "falta el modifier de preview (Geometry Nodes) en la pieza"
assert cube.show_transparent, "la pieza necesita show_transparent para que el fantasma se vea en Solid"
assert cutter.show_transparent, "el plano cortador necesita show_transparent para verse translúcido en Solid"
cutter.location.z = 0.5  # normal +Z: se conserva la parte superior
bpy.context.view_layer.update()

bpy.ops.siro.cut()

assert "SiroCutter" not in bpy.data.objects, "SiroCutter debía borrarse tras el corte"
assert cube.modifiers.get("SiroGhostPreview") is None, "el modifier de preview debía quitarse tras el corte"
assert "SiroGhostFantasma" not in cube.data.materials, "el material fantasma debía quitarse tras el corte"

bm = bmesh.new()
bm.from_mesh(cube.data)
zs = [v.co.z for v in bm.verts]
assert min(zs) >= 0.5 - 1e-5, f"quedó geometría bajo el plano: z min = {min(zs)}"
assert max(zs) > 0.9, "se perdió la parte que debía conservarse"
assert all(len(e.link_faces) == 2 for e in bm.edges), "malla no manifold: el corte no quedó sellado"
bm.free()

# conservar abajo: se queda la parte inferior (la pieza ahora ocupa z en [0.5, 1])
bpy.ops.siro.add_cut_plane()
bpy.data.objects["SiroCutter"].location.z = 0.75
bpy.context.view_layer.update()
bpy.ops.siro.cut(side='BACK')

bm = bmesh.new()
bm.from_mesh(cube.data)
assert max(v.co.z for v in bm.verts) <= 0.75 + 1e-5, "side=BACK no conservó la parte inferior"
assert all(len(e.link_faces) == 2 for e in bm.edges), "malla no manifold tras corte BACK"
bm.free()

# ambas partes: divide en dos objetos sellados
bpy.ops.mesh.primitive_cube_add(size=2, location=(5, 0, 0))
cube2 = bpy.context.active_object
bpy.ops.siro.add_cut_plane()
bpy.data.objects["SiroCutter"].location.z = 0.3
bpy.context.view_layer.update()

before = set(bpy.data.objects)
bpy.ops.siro.cut(side='BOTH')
new = [o for o in set(bpy.data.objects) - before]
assert len(new) == 1, f"side=BOTH debía crear 1 objeto nuevo, creó {len(new)}"
other = new[0]

for obj, is_top in ((cube2, True), (other, False)):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    zs = [v.co.z for v in bm.verts]
    if is_top:
        assert min(zs) >= 0.3 - 1e-5, "la mitad superior tiene geometría bajo el plano"
    else:
        assert max(zs) <= 0.3 + 1e-5, "la mitad inferior tiene geometría sobre el plano"
    assert all(len(e.link_faces) == 2 for e in bm.edges), f"{obj.name} no quedó manifold"
    bm.free()

# --- el plano cayendo sobre vértices que YA existen ---
# `add_cut_plane` deja el plano en el centro del bounding box, que en una esfera
# es el ecuador y en un toro el medio: justo donde ya hay un anillo de vértices.
# Ahí bisect_plane devuelve en `geom_cut` aristas que ya tienen dos caras, y el
# agujero real es otro; tapar `geom_cut` a ciegas dejaba 32 aristas de borde, 32
# no-manifold y 32 caras de área cero en la esfera (48 y 48 en el toro). Un cubo
# no lo dispara nunca — por eso este test no usa un cubo.
for nombre, crear, vol_entero in (
    ("esfera", lambda: bpy.ops.mesh.primitive_uv_sphere_add(
        radius=8.0, segments=32, ring_count=16, location=(20, 0, 0)), 2110.4),
    ("toro", lambda: bpy.ops.mesh.primitive_torus_add(
        major_radius=10, minor_radius=3, location=(40, 0, 0)), 1691.6),
):
    crear()
    pieza = bpy.context.active_object
    bpy.ops.siro.add_cut_plane()
    bpy.context.view_layer.update()
    bpy.ops.siro.cut(side='FRONT')

    bm = bmesh.new()
    bm.from_mesh(pieza.data)
    borde = sum(1 for e in bm.edges if e.is_boundary)
    no_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    degeneradas = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    volumen = bm.calc_volume(signed=True)
    bm.free()
    assert borde == 0, f"{nombre} cortada por su centro quedó abierta ({borde} aristas de borde)"
    assert no_manifold == 0, f"{nombre}: {no_manifold} aristas no-manifold tras cortar por el centro"
    assert degeneradas == 0, f"{nombre}: quedaron {degeneradas} caras de área cero"
    assert abs(volumen - vol_entero / 2) / (vol_entero / 2) < 0.02, \
        f"{nombre}: el corte por el centro debía dejar la mitad, dejó {volumen:.1f} de {vol_entero}"

# --- cortar una pieza que YA traía caras de área cero ---
# Las que deja el boolean del relleno. La limpieza del corte tiene que tocar solo
# las aristas de su propio plano: disolver degeneradas en toda la malla abre esas
# piezas (21 aristas de borde y 60 no-manifold, medido) porque ahí no cose, borra.
from sirobuilder.operators import extrude_down as _ed

bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_uv_sphere_add(radius=8.0, segments=32, ring_count=16, location=(60, 0, 12))
_pieza = bpy.context.active_object
bpy.context.view_layer.objects.active = _pieza
assert _ed.extrude_down(bpy.context, _pieza, 20.0, 0.0, 256), "el test necesita la pieza rellenada"

bm = bmesh.new()
bm.from_mesh(_pieza.data)
_deg_previas = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
bm.free()
assert _deg_previas > 0, "el test necesita las caras de área cero que deja el relleno"

bpy.ops.object.select_all(action='DESELECT')
_pieza.select_set(True)
bpy.context.view_layer.objects.active = _pieza
bpy.ops.siro.add_cut_plane()
bpy.context.view_layer.update()
bpy.ops.siro.cut(side='FRONT')

bm = bmesh.new()
bm.from_mesh(_pieza.data)
_borde = sum(1 for e in bm.edges if e.is_boundary)
_nm = sum(1 for e in bm.edges if not e.is_manifold)
bm.free()
assert _borde == 0 and _nm == 0, \
    f"cortar una pieza rellenada la abrió: {_borde} aristas de borde, {_nm} no-manifold"

from sirobuilder.operators import ghost_preview as _gp

# --- cancelar devuelve el foco a la pieza ---
# El plano nace activo y como ÚNICO objeto seleccionado, así que borrarlo sin
# más dejaba la escena con activo=None y sin selección. Y sin selección el gizmo
# se dibuja —lo posiciona el objeto activo— pero no mueve nada, porque
# transform.translate opera sobre lo seleccionado: los ejes aparecen y
# arrastrarlos no hace nada, hasta que algo fuerza un refresco.
for etiqueta, poner_plano in (("plano de corte", "add_cut_plane"),
                              ("plano de altura", "extrude_plane")):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add(size=10.0, location=(80, 0, 0))
    _p = bpy.context.active_object
    _p.select_set(True)
    bpy.context.view_layer.objects.active = _p
    getattr(bpy.ops.siro, poner_plano)()
    assert bpy.context.view_layer.objects.active.name == _gp.CUTTER_NAME, \
        f"{etiqueta}: el plano debía quedar activo"

    bpy.ops.siro.cancel_cut()

    _activo = bpy.context.view_layer.objects.active
    assert _activo is not None, f"{etiqueta}: cancelar dejó la escena sin objeto activo"
    assert _activo == _p, f"{etiqueta}: cancelar no devolvió el foco a la pieza ({_activo.name})"
    assert _activo.select_get(), \
        f"{etiqueta}: la pieza quedó activa pero sin seleccionar — el gizmo se dibuja y no mueve"
    bpy.data.objects.remove(_p, do_unlink=True)

# --- la función de los drivers sobrevive a abrir un .blend ---
# Blender VACÍA bpy.app.driver_namespace en cada carga de archivo. Inyectarla
# solo en register() no alcanza: al abrir cualquier .blend los seis drivers del
# fantasma quedan is_valid=False, los sockets se quedan en cero y con la normal
# del plano en (0,0,0) ninguna cara se marca. Medido en la sesión de Leo sobre
# una pieza real: 0 caras fantasma de 250 185, con el addon bien habilitado.
from sirobuilder.operators import ghost_preview as _gp

# ojo: @persistent marca la función con `_bpy_persistent = None`, así que se
# comprueba que el atributo EXISTA, no su valor
assert hasattr(_gp._reponer_driver, "_bpy_persistent"), \
    "el handler tiene que ser @persistent, o se borra en la primera carga"
assert _gp._reponer_driver in bpy.app.handlers.load_post, \
    "falta el handler load_post que repone la función de los drivers"

bpy.ops.wm.read_homefile(use_empty=True)  # vacía el namespace y dispara load_post
assert _gp._DRIVER_NS_KEY in bpy.app.driver_namespace, \
    "tras cargar un archivo, la función de los drivers no se repuso"
assert _gp._reponer_driver in bpy.app.handlers.load_post, \
    "el handler no sobrevivió a la carga: no era persistente"

print("OK clip_plane")
