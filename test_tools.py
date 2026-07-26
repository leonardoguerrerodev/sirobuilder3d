# Correr con: blender -b -P test_tools.py
import math
import pathlib
import sys
import tempfile
import time

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
import addon_utils

try:
    addon_utils.disable("bl_ext.user_default.sirobuilder", default_set=False)
except Exception:
    pass

import sirobuilder

sirobuilder.register()

# --- reparar: cubo con una cara borrada debe quedar manifold ---
bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(cube.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES')
bm.to_mesh(cube.data)
bm.free()

bpy.ops.siro.repair()

bm = bmesh.new()
bm.from_mesh(cube.data)
assert all(e.is_manifold for e in bm.edges), "reparar no cerró el agujero"
bm.free()

# --- simplificar: cubo subdividido debe bajar de caras ---
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.subdivide(number_cuts=4)
bpy.ops.object.mode_set(mode='OBJECT')
before = len(cube.data.polygons)

bpy.ops.siro.simplify(ratio=0.5)

after = len(cube.data.polygons)
assert after < before, f"simplificar no redujo caras: {before} → {after}"
assert not cube.modifiers, "el modifier Decimate debía quedar aplicado"

# --- reparar: pared interior (residuo típico de boolean) debe desaparecer ---
from sirobuilder.operators.repair import _mesh_stats

bpy.ops.mesh.primitive_cube_add(size=2, location=(160, 0, 0))
w1 = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=2, location=(162, 0, 0))
w2 = bpy.context.active_object
w1.select_set(True)
bpy.context.view_layer.objects.active = w1
bpy.ops.object.join()  # dos cubos pegados en un solo objeto: pared interior en x=161
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0001)
bpy.ops.object.mode_set(mode='OBJECT')
assert _mesh_stats(w1)[1] > 0, "el test necesita una pared interior no-manifold"

bpy.ops.siro.repair()

agujeros, no_manifold = _mesh_stats(w1)
assert no_manifold == 0, f"reparar no quitó la pared interior: {no_manifold} aristas no-manifold"
assert abs(w1.dimensions.x - 4) < 1e-4, f"reparar deformó la pieza: ancho {w1.dimensions.x}"

# --- reparar: el feedback debe contar los agujeros reales (2 caras borradas = 2) ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(170, 0, 0))
h = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(h.data)
bm.faces.ensure_lookup_table()
opuestas = [f for f in bm.faces if abs(f.normal.z) > 0.9]  # tapa y base: 2 agujeros separados
bmesh.ops.delete(bm, geom=opuestas, context='FACES')
bm.to_mesh(h.data)
bm.free()
assert _mesh_stats(h)[0] == 2, f"stats contó {_mesh_stats(h)[0]} agujeros, esperaba 2"

bpy.ops.siro.repair()

assert _mesh_stats(h) == (0, 0), f"reparar dejó {_mesh_stats(h)} (agujeros, no-manifold)"

# --- simplificar: malla con ngons (residuo de boolean) también debe reducir ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(150, 0, 0))
ng_a = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.subdivide(number_cuts=6)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.mesh.primitive_cube_add(size=2, location=(151, 0, 0))
ng_b = bpy.context.active_object
ng_a.select_set(True)
bpy.context.view_layer.objects.active = ng_a
bpy.ops.siro.boolean(operation='DIFFERENCE', solver='EXACT')
ngons = sum(1 for p in ng_a.data.polygons if len(p.vertices) > 4)
assert ngons > 0, "el test necesita ngons del boolean"

from sirobuilder.operators.simplify import _tri_count

ng_before = _tri_count(ng_a)

bpy.ops.siro.simplify(ratio=0.5)

assert _tri_count(ng_a) < ng_before, \
    f"simplificar no redujo la malla con ngons: {ng_before} → {_tri_count(ng_a)} triángulos"

# --- relieve: gradiente horizontal debe generar altura creciente ---
img = bpy.data.images.new("depthmap_test", 32, 32)
pixels = []
for y in range(32):
    for x in range(32):
        v = x / 31
        pixels += [v, v, v, 1.0]
img.pixels = pixels
img_path = str(pathlib.Path(tempfile.mkdtemp()) / "depthmap_test.png")
img.filepath_raw = img_path
img.file_format = 'PNG'
img.save()

bpy.ops.siro.depthmap_relief(filepath=img_path)
relief = bpy.context.active_object
assert "SiroRelieve" in relief.modifiers, "falta el modifier Displace"
assert "SiroResolucion" not in relief.modifiers, "no debía quedar Subsurf en vivo"
assert len(relief.data.vertices) == 607 * 607, f"malla horneada esperaba 607×607 verts, tiene {len(relief.data.vertices)}"

_n_cara = len(relief.data.vertices)  # la cara de arriba, antes de que Solidify la duplique
bpy.ops.siro.apply_relief()

assert not relief.modifiers, "aplicar relieve debía consumir los modifiers"
zs = [v.co.z for v in relief.data.vertices]
assert max(zs) - min(zs) > 0.2, f"el relieve no generó altura: rango z = {max(zs) - min(zs)}"
bm = bmesh.new()
bm.from_mesh(relief.data)
abiertas = sum(1 for e in bm.edges if not e.is_manifold)
volumen = bm.calc_volume(signed=True)
bm.free()
assert abiertas == 0, f"el relieve aplicado quedó abierto ({abiertas} aristas) — no es fusionable"

# la base tiene que ser una placa plana debajo del relieve. Solidify sola la
# desplazaba por la normal: sobre una pieza de 5 mm arrastraba la base 2,5 mm de
# costado, dejaba 0,03 mm de grosor y auto-intersecaba la malla (volumen negativo)
_arriba = [relief.data.vertices[i].co for i in range(_n_cara)]
_base = [relief.data.vertices[i].co for i in range(_n_cara, 2 * _n_cara)]
_lat = max((a.xy - b.xy).length for a, b in zip(_arriba, _base))
assert _lat < 1e-5, f"la base se arrastró de costado {_lat:.3f} mm en vez de bajar recta"
_z_base = [v.z for v in _base]
assert max(_z_base) - min(_z_base) < 1e-5, f"la base no quedó plana: varía {max(_z_base) - min(_z_base):.3f} mm"
_grosor = min(a.z - b.z for a, b in zip(_arriba, _base))
assert abs(_grosor - 1.0) < 1e-4, f"el grosor de base pedido era 1.0 mm y quedó en {_grosor:.3f} mm"
assert volumen > 0, f"la malla quedó auto-intersecada: volumen con signo {volumen:.3f}"

# --- preparar depthmap: de imagen a color a silueta abombada ---
import numpy as np

from sirobuilder.operators import depthmap_relief as dm

N = 96
_yy, _xx = np.mgrid[0:N, 0:N]
disco = ((_xx - N / 2) ** 2 + (_yy - N / 2) ** 2) < (N * 0.35) ** 2
px = np.zeros((N, N, 4), np.float32)
px[..., :3] = (0.8, 0.8, 0.2)   # fondo plano
px[disco, :3] = (0.1, 0.2, 0.9)  # pieza
px[..., 3] = 1.0                 # sin alpha útil: tiene que adivinar por el color

alto, hubo_alpha = dm.calcular_depth(px, domo=1.0)
assert not hubo_alpha, "sin alpha, calcular_depth debía avisar que adivinó la silueta"
assert alto[0, 0] == 0.0 and alto[-1, -1] == 0.0, f"el fondo debía quedar plano en 0, dio {alto[0, 0]}"
_centro = float(alto[N // 2, N // 2])
_borde = float(alto[N // 2, int(N / 2 - N * 0.30)])
assert _centro > _borde > 0.0, f"el domo no sube hacia adentro: centro {_centro}, borde {_borde}"

alto_inv, _ = dm.calcular_depth(px, domo=1.0, invertir=True)
assert abs(float(alto_inv[N // 2, N // 2]) - (1.0 - _centro)) < 1e-6, "invertir no dio vuelta la altura"
assert alto_inv[0, 0] == 0.0, "invertir levantó el fondo: tiene que quedar plano igual"

px_alpha = px.copy()
px_alpha[..., 3] = disco.astype(np.float32)
_, hubo_alpha = dm.calcular_depth(px_alpha, domo=1.0)
assert hubo_alpha, "con alpha en la imagen, la silueta no se adivina: se usa el alpha"

# el depthmap no puede salir más grande que lo que el grid del relieve puede consumir
grande = np.zeros((1600, 1600, 4), np.float32)
grande[..., 3] = 1.0
_yy, _xx = np.mgrid[0:1600, 0:1600]
grande[((_xx - 800) ** 2 + (_yy - 800) ** 2) < 80 ** 2, :3] = 1.0
alto_g, _ = dm.calcular_depth(grande, domo=1.0)
assert max(alto_g.shape) <= dm.RES_DEPTH, f"el depthmap no se submuestreó: {alto_g.shape}"

# el operador completo, contra un relieve vivo
color = bpy.data.images.new("prep_test", N, N)
color.pixels.foreach_set(px.ravel())
rel = dm.crear_relieve(bpy.context, color)
bpy.context.view_layer.objects.active = rel
bpy.ops.siro.prep_depthmap()

gen = rel.modifiers[dm.DISP_MOD].texture.image
assert gen.colorspace_settings.name == 'Non-Color', \
    f"el depthmap generado quedó en {gen.colorspace_settings.name}: lo desplazaría con una gamma de más"
assert gen.get("siro_source") == "prep_test", "el generado no recuerda de qué imagen salió"
a1 = np.empty(gen.size[0] * gen.size[1] * 4, np.float32)
gen.pixels.foreach_get(a1)

bpy.ops.siro.prep_depthmap()  # de nuevo: debe partir del original, no del generado
a2 = np.empty(gen.size[0] * gen.size[1] * 4, np.float32)
rel.modifiers[dm.DISP_MOD].texture.image.pixels.foreach_get(a2)
assert np.array_equal(a1, a2), "preparar dos veces compuso el efecto: se perdió siro_source"

# --- relieve desde pieza 3D: profundidad real medida sobre la malla ---
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_uv_sphere_add(radius=15.0, location=(400, 0, 0))
esfera = bpy.context.active_object
bpy.ops.siro.bake_depthmap()

depth = bpy.data.images[f"{esfera.name}_depth"]
assert depth.colorspace_settings.name == 'Non-Color', "el bake tiene que salir Non-Color"
buf = np.empty(dm.RES_DEPTH * dm.RES_DEPTH * 4, np.float32)
depth.pixels.foreach_get(buf)
zmap = buf.reshape(dm.RES_DEPTH, dm.RES_DEPTH, 4)[..., 0]
assert zmap[0, 0] == 0.0 and zmap[-1, -1] == 0.0, "las esquinas no tocan la esfera: deben quedar de fondo"
_c = dm.RES_DEPTH // 2
assert zmap[_c, _c] > 0.99, f"el polo de la esfera debía ser el máximo, dio {zmap[_c, _c]}"

rel3d = bpy.context.active_object
assert dm.DISP_MOD in rel3d.modifiers, "el bake debía dejar el relieve armado"
# el rango 0–1 son 15 mm: la media esfera vista desde arriba va de 0 en el borde al polo
assert abs(rel3d.modifiers[dm.DISP_MOD].strength - 15.0) < 0.5, \
    f"la profundidad no quedó a escala real: {rel3d.modifiers[dm.DISP_MOD].strength} mm, esperaba 15"
assert abs(rel3d.dimensions.x - 31.5) < 0.5, \
    f"el relieve no salió del ancho de la pieza: {rel3d.dimensions.x} mm, esperaba 31,5"

for op in ("SIRO_OT_prep_depthmap", "SIRO_OT_bake_depthmap"):
    assert hasattr(bpy.types, op), f"{op} no quedó registrado"

# --- espejo: refleja la pieza en su lugar, sin duplicarla ---
def _volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol


bpy.ops.mesh.primitive_cube_add(size=2, location=(10, 0, 0))
mcube = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(mcube.data)
bm.verts.ensure_lookup_table()
bm.verts[0].co.x = -0.2  # muesca asimétrica en el lado -X para poder ver el reflejo
mella = bm.verts[0].co.copy()
bm.to_mesh(mcube.data)
bm.free()
verts_before = len(mcube.data.vertices)
dims_before = mcube.dimensions.copy()
vol_before = _volume(mcube)
assert mella.x < 0 and vol_before > 0, "el test necesita muesca en -X y volumen positivo"

bpy.ops.siro.mirror(axis='X')
bpy.context.view_layer.update()

assert len(mcube.data.vertices) == verts_before, "el espejo duplicó geometría en vez de reflejar"
assert not mcube.modifiers, "el espejo no debía dejar modificadores"
xs = [v.co.x for v in mcube.data.vertices]
assert any(abs(x - 0.2) < 1e-5 for x in xs), "la muesca no pasó al lado +X: no se reflejó"
assert not any(abs(x + 0.2) < 1e-5 for x in xs), "la muesca sigue en -X"
assert (mcube.dimensions - dims_before).length < 1e-5, "el espejo movió/deformó la pieza"
assert _volume(mcube) > 0, f"el espejo dejó las normales invertidas (volumen {_volume(mcube)})"

# el eje es el de MUNDO, el que muestra el gizmo y del que los botones toman su
# color: con la pieza rotada, reflejar sobre el eje local usaba otro plano
bpy.ops.mesh.primitive_cube_add(size=2, location=(50, 0, 0))
mrot = bpy.context.active_object
mrot.data.vertices[0].co.x -= 0.4          # una marca asimétrica
mrot.rotation_euler = (0.0, 0.0, 0.785398)  # 45° en Z
bpy.context.view_layer.update()
_centro_w = mrot.matrix_world @ (sum((Vector(c) for c in mrot.bound_box), Vector()) / 8)
_antes_w = [mrot.matrix_world @ v.co for v in mrot.data.vertices]
bpy.ops.siro.mirror(axis='X')
bpy.context.view_layer.update()
_despues_w = sorted((round(p.x, 4), round(p.y, 4), round(p.z, 4))
                    for p in (mrot.matrix_world @ v.co for v in mrot.data.vertices))
_esperado_global = sorted((round(2 * _centro_w.x - p.x, 4), round(p.y, 4), round(p.z, 4))
                          for p in _antes_w)
assert _despues_w == _esperado_global, \
    "el espejo no usó el eje X global (el que muestra el gizmo y el color del botón)"

# --- modo acople: enciende, y al apagar DEVUELVE lo que el usuario tenía ---
ts = bpy.context.scene.tool_settings
ts.use_snap = True
ts.snap_elements = {'VERTEX'}
ts.use_snap_align_rotation = False
_previo = (ts.use_snap, set(ts.snap_elements), ts.use_snap_align_rotation)
bpy.ops.siro.snap_dock()
assert ts.use_snap and ts.snap_elements == {'FACE'} and ts.use_snap_align_rotation, "acople no se activó"
bpy.ops.siro.snap_dock()
# apagar no es imponer valores fijos: antes te dejaba el snap apagado y en
# 'INCREMENT' aunque hubieras estado trabajando con snap a vértices
assert (ts.use_snap, set(ts.snap_elements), ts.use_snap_align_rotation) == _previo, \
    f"acople no devolvió la config del usuario: {_previo} → {(ts.use_snap, set(ts.snap_elements), ts.use_snap_align_rotation)}"

# --- marcar selección: al apagar devuelve el color que tenía cada pieza ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(60, 0, 0))
_pintado = bpy.context.active_object
_pintado.color = (0.1, 0.9, 0.3, 1.0)
bpy.ops.siro.select_mark()
assert tuple(_pintado.color) != (0.1, 0.9, 0.3, 1.0), "el modo no llegó a teñir la pieza"
bpy.ops.siro.select_mark()
assert max(abs(a - b) for a, b in zip(_pintado.color, (0.1, 0.9, 0.3, 1.0))) < 1e-4, \
    f"marcar selección borró el color del usuario: quedó en {tuple(_pintado.color)}"

# --- alinear a la base: z mínimo mundial queda en 0, también con la pieza rotada ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(20, 0, 3.7))
acube = bpy.context.active_object
bpy.ops.siro.align_base()
bpy.context.view_layer.update()
min_z = min((acube.matrix_world @ Vector(c)).z for c in acube.bound_box)
assert abs(min_z) < 1e-5, f"alinear a la base dejó z mínimo en {min_z}"

# rotada: `bound_box` es la caja LOCAL y al rotarla cae más abajo que la malla,
# así que medir sobre ella dejaba la pieza flotando (4,30 mm en un toro rotado)
bpy.ops.mesh.primitive_torus_add(major_radius=10, minor_radius=3, location=(40, 0, 12))
arot = bpy.context.active_object
arot.rotation_euler = (0.7, 0.3, 0.0)
bpy.context.view_layer.update()
bpy.ops.siro.align_base()
bpy.context.view_layer.update()
min_z_rot = min((arot.matrix_world @ v.co).z for v in arot.data.vertices)
assert abs(min_z_rot) < 1e-4, f"pieza rotada quedó flotando: z mínimo real {min_z_rot}"

# --- restar y fusionar (booleans de 3D Builder) ---
def _two_cubes(x):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(x, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=2, location=(x + 1, 0, 0))
    b = bpy.context.active_object
    a.select_set(True)
    bpy.context.view_layer.objects.active = a  # activa = la que recibe el resultado
    return a, b

a, b = _two_cubes(70)
b_name = b.name
bpy.ops.siro.boolean(operation='DIFFERENCE')
bpy.context.view_layer.update()
assert b_name not in bpy.data.objects, "restar debía borrar la pieza usada"
assert abs(a.dimensions.x - 1) < 1e-4, f"restar dejó ancho {a.dimensions.x}, esperaba 1"

a, b = _two_cubes(80)
bpy.ops.siro.boolean(operation='UNION')
bpy.context.view_layer.update()
assert abs(a.dimensions.x - 3) < 1e-4, f"fusionar dejó ancho {a.dimensions.x}, esperaba 3"
bm = bmesh.new()
bm.from_mesh(a.data)
assert all(e.is_manifold for e in bm.edges), "la fusión no quedó manifold"
bm.free()

# --- fusionar 3 piezas: queda 1 objeto manifold con el ancho total ---
cubes = []
for i in range(3):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(110 + i, 0, 0))
    cubes.append(bpy.context.active_object)
for c in cubes:
    c.select_set(True)
bpy.context.view_layer.objects.active = cubes[0]
names = [c.name for c in cubes[1:]]

bpy.ops.siro.boolean(operation='UNION')
bpy.context.view_layer.update()

assert not any(n in bpy.data.objects for n in names), "fusionar 3 debía dejar 1 solo objeto"
assert abs(cubes[0].dimensions.x - 4) < 1e-4, f"fusión de 3 dejó ancho {cubes[0].dimensions.x}, esperaba 4"
bm = bmesh.new()
bm.from_mesh(cubes[0].data)
assert all(e.is_manifold for e in bm.edges), "la fusión de 3 no quedó manifold"
bm.free()

# --- fusionar con malla multi-usuario (copia enlazada): no explota ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(120, 0, 0))
mu_a = bpy.context.active_object
mu_b = mu_a.copy()  # comparte data → modifier_apply se negaría
bpy.context.collection.objects.link(mu_b)
mu_b.location.x = 121
assert mu_a.data.users > 1, "el test necesita malla compartida"
mu_a.select_set(True)
mu_b.select_set(True)
bpy.context.view_layer.objects.active = mu_a

bpy.ops.siro.boolean(operation='UNION')
bpy.context.view_layer.update()

assert abs(mu_a.dimensions.x - 3) < 1e-4, f"fusión multi-usuario dejó ancho {mu_a.dimensions.x}, esperaba 3"

# --- fusionar con una pieza abierta: la pieza NO se borra (se conserva con aviso) ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(130, 0, 0))
op_a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=2, location=(131, 0, 0))
op_b = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(op_b.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES')  # lámina abierta
bm.to_mesh(op_b.data)
bm.free()
op_b_name = op_b.name
op_a.select_set(True)
op_b.select_set(True)
bpy.context.view_layer.objects.active = op_a

_verts_a = len(op_a.data.vertices)
_bm = bmesh.new(); _bm.from_mesh(op_a.data)
_nm_a = sum(1 for e in _bm.edges if not e.is_manifold); _bm.free()

try:
    bpy.ops.siro.boolean(operation='UNION')
    raise AssertionError("con una malla abierta el boolean debía cancelarse, no seguir")
except RuntimeError as err:
    assert "Malla abierta" in str(err), f"el aviso no explica el problema: {err}"
bpy.context.view_layer.update()

assert op_b_name in bpy.data.objects, "la pieza de malla abierta no debía desaparecer"
# y el target tampoco se toca: antes se le aplicaba el boolean igual y quedaba
# peor que antes (no-manifold de 0 a 12) mientras el aviso decía "conservadas"
_bm = bmesh.new(); _bm.from_mesh(op_a.data)
_nm_despues = sum(1 for e in _bm.edges if not e.is_manifold); _bm.free()
assert len(op_a.data.vertices) == _verts_a and _nm_despues == _nm_a, \
    f"la pieza activa se modificó: verts {_verts_a}→{len(op_a.data.vertices)}, no-manifold {_nm_a}→{_nm_despues}"

# --- fusionar con un relieve vivo en el target: el relieve entra en el resultado ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(140, 0, 0))
rel_a = bpy.context.active_object
disp = rel_a.modifiers.new("SiroRelieve", 'DISPLACE')
disp.mid_level = 0.0
disp.strength = 2.0  # infla el cubo a ±2.1547 por vértice
bpy.ops.mesh.primitive_cube_add(size=2, location=(142, 0, 0))
rel_b = bpy.context.active_object
rel_a.select_set(True)
rel_b.select_set(True)
bpy.context.view_layer.objects.active = rel_a

bpy.ops.siro.boolean(operation='UNION')
bpy.context.view_layer.update()

assert not rel_a.modifiers, "el relieve pendiente debía hornearse antes del boolean"
assert abs(rel_a.dimensions.x - 5.1547) < 0.02, \
    f"la fusión perdió el relieve: ancho {rel_a.dimensions.x}, esperaba 5.15"

# --- agrupar: seleccionar una pieza del grupo selecciona el resto ---
from sirobuilder.operators import group

bpy.ops.mesh.primitive_cube_add(size=1, location=(40, 0, 0))
g1 = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(42, 0, 0))
g2 = bpy.context.active_object
g1.select_set(True)

bpy.ops.siro.group()
assert g1.get(group.GROUP_KEY) == g2.get(group.GROUP_KEY) is not None, "agrupar no marcó las piezas"

bpy.ops.object.select_all(action='DESELECT')
g1.select_set(True)
group._sync_selection(bpy.context.scene)
assert g2.select_get(), "seleccionar una pieza del grupo no seleccionó la otra"

bpy.ops.siro.ungroup()
assert group.GROUP_KEY not in g1.keys() and group.GROUP_KEY not in g2.keys(), "desagrupar no limpió"

# --- ghost preview: no se muere al escalar ni al renombrar la pieza ---
from sirobuilder.operators import ghost_preview as gp


def _ghost_faces(obj):
    """Caras marcadas como 'se descarta' en la malla evaluada (lo que se ve en pantalla)"""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    idx = len(obj.data.materials) - 1  # el slot fantasma es el último
    n = sum(1 for p in me.polygons if p.material_index == idx)
    ev.to_mesh_clear()
    return n


bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(180, 0, 0))
sph = bpy.context.active_object
bpy.ops.siro.add_cut_plane()
cutter = bpy.data.objects[gp.CUTTER_NAME]
cutter.location.z = 180 * 0 + 0.5  # plano descentrado: el reparto no es 50/50
bpy.context.view_layer.update()

g0 = _ghost_faces(sph)
assert 0 < g0 < len(sph.data.polygons), f"el preview no marcó un lado: {g0} caras fantasma"

sph.scale.z = 2.0  # escalar debe re-evaluar el driver (antes quedaba congelado)
bpy.context.view_layer.update()
g1 = _ghost_faces(sph)
assert g1 != g0, f"escalar la pieza dejó el preview congelado ({g0} → {g1} caras fantasma)"

sph.name = "Colgante Sol"  # renombrar rompía el driver en silencio
bpy.context.view_layer.update()
g2 = _ghost_faces(sph)
assert g2 == g1, f"renombrar la pieza rompió el preview ({g1} → {g2} caras fantasma)"

# y cortar sigue encontrando la pieza aunque el nombre guardado ya no exista
verts_pre = len(sph.data.vertices)
bpy.ops.siro.cut(side='FRONT')
bpy.context.view_layer.update()
assert len(sph.data.vertices) != verts_pre, "cortar no encontró la pieza renombrada"
assert gp.MODIFIER_NAME not in sph.modifiers, "el preview debía limpiarse tras cortar"

# --- UI: primitivas de ~30 mm, íconos válidos y paneles registrados ---
from sirobuilder.operators import extrude_down, shape_cut
from sirobuilder.ui import panels as P

# Por el camino REAL del panel: `_boton` resetea las propiedades del operador
# antes de aplicar las del addon. Llamar al operador con solo `**props` —como
# hacía este test— esquivaba justo el bug: `_boton` también pisaba `scale`, cuyo
# default (0,0,0) es un centinela que significa "sin escala", y la primitiva
# nacía colapsada en un punto (64 vértices, 0 mm de lado, invisible).
for idname, texto, icono, props in P.PRIMITIVAS:
    modulo, op = idname.split(".")
    operador = getattr(getattr(bpy.ops, modulo), op)
    reseteadas = {
        p.identifier: p.default
        for p in operador.get_rna_type().properties
        if p.identifier != "rna_type" and not p.is_readonly
        and p.identifier not in P._PROPS_DE_CONTEXTO
    }
    operador(location=(200, 0, 0), **{**reseteadas, **props})
    d = bpy.context.active_object.dimensions
    assert 28 <= max(d) <= 33, f"{texto} sale de {max(d):.1f} mm, se esperaba ~30"

# y las de contexto no se tocan nunca. Esto es lo que pasa si `scale` vuelve a
# entrar: `_boton` hace setattr(op, "scale", prop.default) y el default de un
# array es un escalar, así que Blender lo expande a (0,0,0) — "sin escala" como
# centinela, pero escrito literalmente multiplica la geometría por cero.
assert "scale" in P._PROPS_DE_CONTEXTO, \
    "`scale` tiene que quedar fuera de _boton: su default (0,0,0) colapsa la primitiva"

bpy.ops.mesh.primitive_cube_add(size=30.0, location=(240, 0, 0), scale=(0.0, 0.0, 0.0))
_colapsado = bpy.context.active_object
assert max(_colapsado.dimensions) < 1e-6 and len(_colapsado.data.vertices) == 8, \
    ("el centinela cambió de comportamiento: scale=(0,0,0) ya no colapsa la primitiva "
     f"(mide {max(_colapsado.dimensions)}) — revisar si _PROPS_DE_CONTEXTO sigue haciendo falta")
bpy.data.objects.remove(_colapsado, do_unlink=True)

iconos = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items.keys()

# Un ícono inexistente revienta draw() y el panel sale VACÍO, sin error visible:
# hay que barrer el fuente entero, no solo los íconos que el test conoce de nombre.
import re

for modulo in (P, shape_cut, extrude_down):
    fuente = pathlib.Path(modulo.__file__).read_text()
    # `icon=` cubre botones y etiquetas; los avisos pasan el ícono por posición
    # y se escapaban del barrido — justo el patrón que dejó el panel vacío
    for patron in (r"icon\s*=\s*'([A-Z0-9_]+)'", r"_aviso\([^)]*,\s*'([A-Z0-9_]+)'\s*\)"):
        for icono in re.findall(patron, fuente):
            assert icono in iconos, f"{pathlib.Path(modulo.__file__).name}: ícono inválido '{icono}'"
# Una sola pestaña y secciones al ras: ni pestaña de laboratorio ni panel
# contenedor que repita el nombre de la pestaña y coma ancho al anidar.
secciones = (P.SIRO_PT_main, P.SIRO_PT_add, P.SIRO_PT_transform, P.SIRO_PT_cut,
             P.SIRO_PT_shape_cut, P.SIRO_PT_extrude, P.SIRO_PT_mesh,
             P.SIRO_PT_place, P.SIRO_PT_relief)
for cls in secciones:
    assert hasattr(bpy.types, cls.__name__), f"{cls.__name__} no quedó registrado"
    assert cls.bl_category == "SiroBuilder", f"{cls.__name__} quedó fuera de la pestaña SiroBuilder"
    assert not getattr(cls, "bl_parent_id", ""), f"{cls.__name__} volvió a anidarse en otro panel"
    assert cls.bl_icon in iconos, f"{cls.__name__}: ícono inválido '{cls.bl_icon}'"
assert len({c.bl_icon for c in secciones}) == len(secciones), "dos secciones comparten ícono"

# el corte por forma reemplazó al corte libre de dos pasos: no pueden convivir
for viejo in ("SIRO_OT_draw_contour", "SIRO_OT_free_cut"):
    assert not hasattr(bpy.types, viejo), f"{viejo} sigue registrado; el corte por forma lo reemplaza"

# Las letras de eje son iconos propios porque Blender no deja colorear texto.
# Headless NO se puede mirar el `icon_id`: sin interfaz Blender no asigna IDs y
# devuelve 0 siempre (comprobado). Lo que sí se puede comprobar es que los
# píxeles quedaron cargados, que los tres glifos son distintos y que cada uno
# lleva el color de SU eje — que es donde estaría el bug de copiar y pegar.
from sirobuilder.ui import iconos as ico

assert ico._coleccion is not None, "la colección de iconos no se registró"
for eje in P.EJES:
    prev = ico._coleccion[eje]
    assert prev.is_icon_custom, f"el icono del eje {eje} no quedó marcado como propio"
    assert tuple(prev.icon_size) == (ico._LADO, ico._LADO), f"eje {eje}: tamaño {tuple(prev.icon_size)}"
    assert len(prev.icon_pixels_float) == ico._LADO * ico._LADO * 4, f"eje {eje}: faltan píxeles"

pintados = {}
for eje in P.EJES:
    px = list(ico._coleccion[eje].icon_pixels_float)
    opacos = [tuple(px[i:i + 3]) for i in range(0, len(px), 4) if px[i + 3] > 0.5]
    assert opacos, f"el glifo del eje {eje} salió completamente transparente"
    assert len(set(opacos)) == 1, f"el glifo del eje {eje} tiene más de un color"
    pintados[eje] = (opacos[0], len(opacos))

assert len({c for c, _ in pintados.values()}) == 3, "dos ejes comparten color"
assert len({n for _, n in pintados.values()}) == 3, "dos ejes dibujan el mismo glifo"
for eje, (color, _) in pintados.items():
    esperado = ico._color_eje(eje)
    assert max(abs(a - b) for a, b in zip(color, esperado)) < 1e-4, \
        f"el eje {eje} no lleva su color de tema: {color} vs {esperado}"

# --- cortador por forma: cerrado y manifold en ortográfica y en perspectiva ---
def _ortho_rays(cuadro, z=50.0):
    """Rayos paralelos mirando hacia -Z, como una vista ortográfica desde arriba"""
    return [(Vector((x, y, z)), Vector((0.0, 0.0, -1.0))) for x, y in cuadro]


def _persp_rays(cuadro, ojo=Vector((0.0, 0.0, 50.0))):
    """Rayos que divergen desde un ojo, como una vista en perspectiva"""
    return [((ojo.copy()), (Vector((x, y, 0.0)) - ojo).normalized()) for x, y in cuadro]


def _cerrado(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    abiertas = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return abiertas, vol


cuadro = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
bpy.ops.mesh.primitive_cube_add(size=2, location=(210, 0, 0))
sc_cube = bpy.context.active_object

for etiqueta, rays in (("ortográfica", _ortho_rays(cuadro)), ("perspectiva", _persp_rays(cuadro))):
    rays = [(o + Vector((210, 0, 0)), d) for o, d in rays]
    cutter = shape_cut.build_cutter(rays, sc_cube)
    assert cutter is not None, f"{etiqueta}: no se construyó el cortador"
    abiertas, vol = _cerrado(cutter)
    assert abiertas == 0, f"{etiqueta}: el cortador quedó abierto ({abiertas} aristas)"
    assert vol > 0, f"{etiqueta}: el cortador quedó del revés (volumen {vol})"
    # tiene que atravesar la pieza de lado a lado, no quedarse corto
    lo = min((cutter.matrix_world @ Vector(c)).z for c in cutter.bound_box)
    hi = max((cutter.matrix_world @ Vector(c)).z for c in cutter.bound_box)
    assert lo < -1 and hi > 1, f"{etiqueta}: el cortador no cubre la pieza (z {lo:.1f}..{hi:.1f})"
    bpy.data.objects.remove(cutter, do_unlink=True)

# un lazo cóncavo (forma de C) también tiene que cerrar bien
ce = [(-1, -1), (1, -1), (1, -0.6), (-0.4, -0.6), (-0.4, 0.6), (1, 0.6), (1, 1), (-1, 1)]
cutter = shape_cut.build_cutter([(o + Vector((210, 0, 0)), d) for o, d in _ortho_rays(ce)], sc_cube)
abiertas, vol = _cerrado(cutter)
assert abiertas == 0, f"lazo cóncavo: cortador abierto ({abiertas} aristas)"
assert vol > 0, f"lazo cóncavo: cortador del revés (volumen {vol})"
bpy.data.objects.remove(cutter, do_unlink=True)

assert shape_cut.build_cutter([], sc_cube) is None, "contorno vacío debía devolver None"

# --- aplicar el corte: Recortar deja 1 pieza sellada, Partir deja 2 ---
medio = [(-5, -5), (0, -5), (0, 5), (-5, 5)]  # media pieza en X


def _cubo_y_rayos(x, cuadro=medio):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(x, 0, 0))
    obj = bpy.context.active_object
    rays = [(o + Vector((x, 0, 0)), d) for o, d in _ortho_rays(cuadro)]
    return obj, rays


obj, rays = _cubo_y_rayos(220)
res = shape_cut.apply_shape_cut(bpy.context, obj, rays, action='TRIM', keep='IN')
bpy.context.view_layer.update()
assert res == [obj], f"Recortar debía dejar 1 pieza, dejó {res}"
assert abs(obj.dimensions.x - 1) < 1e-4, f"Recortar (interior) dejó ancho {obj.dimensions.x}, esperaba 1"
assert _cerrado(obj)[0] == 0, "Recortar no dejó la pieza sellada"

obj, rays = _cubo_y_rayos(230)
shape_cut.apply_shape_cut(bpy.context, obj, rays, action='TRIM', keep='OUT')
bpy.context.view_layer.update()
assert abs(obj.dimensions.x - 1) < 1e-4, f"Recortar (exterior) dejó ancho {obj.dimensions.x}, esperaba 1"
xs = [(obj.matrix_world @ v.co).x for v in obj.data.vertices]
assert min(xs) > 230 - 1e-4, "Recortar (exterior) se quedó con el lado equivocado"

obj, rays = _cubo_y_rayos(240)
res = shape_cut.apply_shape_cut(bpy.context, obj, rays, action='SPLIT')
bpy.context.view_layer.update()
assert len(res) == 2, f"Partir debía dejar 2 piezas, dejó {len(res)}"
for mitad in res:
    assert _cerrado(mitad)[0] == 0, f"la mitad {mitad.name} no quedó sellada"
    assert abs(mitad.dimensions.x - 1) < 1e-4, f"{mitad.name} quedó de ancho {mitad.dimensions.x}"
assert res[0].data is not res[1].data, "las dos mitades comparten malla"

# malla multi-usuario: modifier_apply se negaría, hay que desligarla antes
bpy.ops.mesh.primitive_cube_add(size=2, location=(250, 0, 0))
mu = bpy.context.active_object
gemelo = mu.copy()  # comparte data
bpy.context.collection.objects.link(gemelo)
gemelo.location.x = 253
assert mu.data.users > 1, "el test necesita malla compartida"
rays = [(o + Vector((250, 0, 0)), d) for o, d in _ortho_rays(medio)]
shape_cut.apply_shape_cut(bpy.context, mu, rays, action='TRIM', keep='IN')
bpy.context.view_layer.update()
assert abs(mu.dimensions.x - 1) < 1e-4, f"corte multi-usuario dejó ancho {mu.dimensions.x}"
assert abs(gemelo.dimensions.x - 2) < 1e-4, "el corte se llevó puesta la copia enlazada"

# relieve vivo: el corte tiene que hornearlo, no aplicarse sobre la malla base
bpy.ops.mesh.primitive_cube_add(size=2, location=(260, 0, 0))
rv = bpy.context.active_object
disp = rv.modifiers.new("SiroRelieve", 'DISPLACE')
disp.mid_level, disp.strength = 0.0, 2.0  # infla el cubo a ±2.1547 por vértice
ancho = [(-9, -9), (0, -9), (0, 9), (-9, 9)]
rays = [(o + Vector((260, 0, 0)), d) for o, d in _ortho_rays(ancho)]
shape_cut.apply_shape_cut(bpy.context, rv, rays, action='TRIM', keep='IN')
bpy.context.view_layer.update()
assert not rv.modifiers, "el relieve pendiente debía hornearse antes del corte"
assert abs(rv.dimensions.z - 4.3094) < 0.02, \
    f"el corte perdió el relieve: alto {rv.dimensions.z}, esperaba 4.31"

# --- esfera con la forma CENTRADA: el eje del corte pasa por los polos ---
# Con el solver FLOAT esto devolvía la pieza en volumen 0 y 12 vértices, y en
# Exterior la dejaba con 6 aristas no-manifold sin que se notara. Un cubo nunca
# lo disparaba: por eso hace falta la esfera acá.
_centrado = [(-4, -4), (4, -4), (4, 4), (-4, 4)]
_partes = {}
for _keep in ('IN', 'OUT'):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=8.0, segments=32, ring_count=16,
                                         location=(300, 0, 0))
    _esf = bpy.context.active_object
    _rays = [(o + Vector((300, 0, 0)), d) for o, d in _ortho_rays(_centrado, z=60.0)]
    shape_cut.apply_shape_cut(bpy.context, _esf, _rays, action='TRIM', keep=_keep)
    _abiertas, _vol = _cerrado(_esf)
    assert _abiertas == 0, f"esfera centrada ({_keep}): quedó con {_abiertas} aristas no-manifold"
    assert _vol > 1.0, f"esfera centrada ({_keep}): la pieza se destruyó (volumen {_vol})"
    _partes[_keep] = _vol
    bpy.data.objects.remove(_esf, do_unlink=True)
# las dos mitades tienen que sumar la esfera entera: 4/3·π·8³ ≈ 2144, y la malla
# de 32 segmentos da 2110,4
assert abs(_partes['IN'] + _partes['OUT'] - 2110.4) < 2.0, \
    f"Interior + Exterior = {_partes['IN'] + _partes['OUT']:.1f}, esperaba la esfera entera (2110.4)"

# --- modos de forma: contornos 2D cerrados y coherentes ---
import math as _math

ANCHO, ALTO = 800, 600

rect = shape_cut.shape_points('RECT', [(100, 100), (300, 250)], ANCHO, ALTO)
assert len(rect) == 4, f"Rectángulo debía dar 4 esquinas, dio {len(rect)}"
assert set(rect) == {(100, 100), (300, 100), (300, 250), (100, 250)}, f"esquinas mal: {rect}"

eli = shape_cut.shape_points('ELLIPSE', [(100, 100), (300, 200)], ANCHO, ALTO)
assert len(eli) > 8, "Elipse con muy pocos segmentos"
cx = sum(x for x, _ in eli) / len(eli)
cy = sum(y for _, y in eli) / len(eli)
assert abs(cx - 200) < 1 and abs(cy - 150) < 1, f"Elipse descentrada: ({cx:.1f}, {cy:.1f})"
radios = [((x - 200) / 100.0, (y - 150) / 50.0) for x, y in eli]
assert all(abs(_math.hypot(u, v) - 1) < 1e-6 for u, v in radios), "Elipse deformada"

linea = shape_cut.shape_points('LINE', [(400, 300), (500, 300)], ANCHO, ALTO)
assert len(linea) == 4, f"Línea debía cerrar con 4 puntos, dio {len(linea)}"
assert min(x for x, _ in linea) < 0 and max(x for x, _ in linea) > ANCHO, \
    f"la línea-cuchillo no se extiende fuera de la región: {linea}"
assert not shape_cut.shape_points('LINE', [(10, 10), (10, 10)], ANCHO, ALTO), \
    "línea degenerada (mismo punto) debía devolver contorno vacío"

# lazo denso: se simplifica, no repite el punto de cierre y conserva la forma
circulo = [(400 + 100 * _math.cos(t), 300 + 100 * _math.sin(t))
           for t in (2 * _math.pi * i / 720 for i in range(721))]
lazo = shape_cut.shape_points('LASSO', circulo, ANCHO, ALTO)
assert 8 < len(lazo) < 200, f"el lazo no se simplificó: {len(lazo)} puntos de 721"
assert (Vector(lazo[0]) - Vector(lazo[-1])).length > 1.0, "el lazo repite el punto de cierre"
assert all(abs(_math.hypot(x - 400, y - 300) - 100) < 5 for x, y in lazo), "el lazo perdió la forma"

poli = shape_cut.shape_points('POLYGON', [(0, 0), (10, 0), (10, 10), (0, 0)], ANCHO, ALTO)
assert len(poli) == 3, f"Polígono debía descartar el clic de cierre, dio {poli}"

# --- máquina de estados del trazo: el ciclo de eventos, sin viewport ---
def _estado(shape='LASSO'):
    return shape_cut.StrokeState(shape, ANCHO, ALTO)


# EL bug: el operador se lanza desde un botón del panel, así que el RELEASE de
# ESE clic llega al modal recién instalado. Si se toma como fin del trazo, la
# herramienta se cancela sola y "no hace nada".
st = _estado()
assert st.event('LEFTMOUSE', 'RELEASE', (10, 10)) == 'IGNORE', \
    "el RELEASE del clic que abrió la herramienta no debe aplicar nada"
assert st.anclas == [], "ese RELEASE tampoco debe dejar anclas sueltas"
assert st.event('LEFTMOUSE', 'PRESS', (10, 10)) == 'DRAW', "tras ignorarlo debe poder trazarse"

# lazo: press → moves → release aplica
st = _estado('LASSO')
assert st.event('LEFTMOUSE', 'PRESS', (10, 10)) == 'DRAW'
for i in range(5):
    assert st.event('MOUSEMOVE', 'PRESS', (20 + i * 10, 40)) == 'DRAW'
assert st.event('LEFTMOUSE', 'RELEASE', (10, 40)) == 'APPLY'
assert len(st.anclas) == 7, f"el lazo perdió puntos del recorrido: {len(st.anclas)}"

# formas de dos anclas: el movimiento arrastra la segunda, no acumula
st = _estado('RECT')
st.event('LEFTMOUSE', 'PRESS', (100, 100))
for destino in ((150, 150), (200, 200), (300, 250)):
    st.event('MOUSEMOVE', 'PRESS', destino)
assert len(st.anclas) == 2, f"Rectángulo debía guardar 2 anclas, guardó {len(st.anclas)}"
assert st.event('LEFTMOUSE', 'RELEASE', (300, 250)) == 'APPLY'
assert len(st.contour()) == 4, "el rectángulo no salió de 4 esquinas"

# polígono: se cierra con Enter, no al soltar, y deja orbitar entre clics
st = _estado('POLYGON')
st.event('LEFTMOUSE', 'PRESS', (10, 10))
assert st.event('LEFTMOUSE', 'RELEASE', (10, 10)) == 'IGNORE', "el polígono no se cierra al soltar"
assert st.event('MOUSEMOVE', 'PRESS', (50, 50)) == 'IGNORE', "el polígono debe dejar orbitar"
st.event('LEFTMOUSE', 'PRESS', (100, 10))
st.event('LEFTMOUSE', 'PRESS', (100, 100))
assert st.event('RET', 'PRESS', (0, 0)) == 'APPLY', "Enter debía cerrar el polígono"
assert len(st.contour()) == 3

# Enter sin haber trazado nada no dispara un corte
assert _estado('POLYGON').event('RET', 'PRESS', (0, 0)) == 'IGNORE'
# escape y clic derecho cancelan siempre
for tipo in ('ESC', 'RIGHTMOUSE'):
    assert _estado().event(tipo, 'PRESS', (0, 0)) == 'CANCEL', f"{tipo} debía cancelar"

# el preview del lazo no pasa por el RDP (se redibuja en cada frame)
st = _estado('LASSO')
st.event('LEFTMOUSE', 'PRESS', (0, 0))
for i in range(200):
    st.event('MOUSEMOVE', 'PRESS', (i, i))
assert len(st.preview()) == 201, "el preview del lazo debe ser el trazo crudo"
assert len(st.contour()) < 201, "el contorno final sí debe simplificarse"

# reset deja la herramienta lista para el corte siguiente
st.reset()
assert st.anclas == [] and not st.armado, "reset no dejó la herramienta limpia"

# --- corte por forma: registrado y con íconos válidos ---
assert hasattr(bpy.types, "SIRO_OT_shape_cut"), "el operador de corte por forma no quedó registrado"
for ident, nombre, desc, icono in shape_cut.SHAPES:
    assert icono in iconos, f"forma {ident}: ícono inválido '{icono}'"
for prop in ("siro_action", "siro_base_z", "siro_keep"):
    assert hasattr(bpy.context.scene, prop), f"falta la propiedad de escena {prop}"

# Cada forma tiene que ARRANCAR la herramienta, no solo elegirla: cuando las
# formas eran un selector, se clickeaban y no pasaba nada (verificado en el
# Blender de Leo: siro_shape en 'RECT' y ningún corte hecho).
fuente_lab = pathlib.Path(P.__file__).read_text()
assert 'grid.operator("siro.shape_cut"' in fuente_lab, \
    "las formas de SiroLab deben ser botones que lanzan el corte"
assert "siro_shape" not in fuente_lab, "quedó el selector de forma viejo, que no hacía nada"


# --- extrudir hacia abajo: RELLENA hacia abajo, no corta ---
def _medir(obj):
    """Volumen, rango de Z, aristas abiertas y la distancia al eje de la pieza
    del vértice más cercano. Todo en mundo, salvo el radio, que se mide desde
    el origen de la pieza (las del test están corridas en X para no pisarse)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    eje = obj.matrix_world.translation
    zs = [v.co.z for v in bm.verts]
    datos = (
        bm.calc_volume(),
        min(zs), max(zs),
        sum(1 for e in bm.edges if not e.is_manifold),
        min(((v.co - eje).xy.length for v in bm.verts), default=0.0),
    )
    bm.free()
    return datos


ctx = bpy.context
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_uv_sphere_add(radius=15.0, location=(400, 0, 15))
esfera = bpy.context.active_object
assert extrude_down.extrude_down(ctx, esfera, 15.0, 0.0), "el relleno devolvió False en el caso normal"
vol, zmin, zmax, abiertas, _ = _medir(esfera)
# media esfera arriba + el cilindro que queda al rellenar bajo el ecuador. La
# esfera entera son 14137 mm³, así que el assert distingue "rellenó" de "nada".
esperado = 2 / 3 * math.pi * 15 ** 3 + math.pi * 15 ** 2 * 15
assert abs(vol - esperado) / esperado < 0.05, f"volumen {vol:.1f} mm³, se esperaba ~{esperado:.1f}"
assert abs(zmin) < 1e-4, f"el fondo no quedó plano en Z=0 ({zmin})"
assert abs(zmax - 30) < 1e-3, f"la parte de arriba del plano se movió ({zmax})"
assert abiertas == 0, f"el relleno dejó la malla abierta ({abiertas} aristas no-manifold)"

# LA "C" DE LEO: el caso que distingue rellenar de cortar. Un cubo de 30 mm con
# una muesca lateral: como hay pieza por ENCIMA de la muesca, el relleno la
# tapa y el resultado vuelve a ser el cubo entero. La versión que cortaba en el
# plano daba bastante menos.
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(size=30.0, location=(400, 100, 15))
ce = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(415, 100, 15))
muesca = bpy.context.active_object
muesca.scale = (10.0, 20.0, 5.0)  # se lleva x∈[405,415], z∈[10,20] del cubo
bpy.context.view_layer.update()
ce.select_set(True)
bpy.context.view_layer.objects.active = ce
bpy.ops.siro.boolean(operation='DIFFERENCE', solver='EXACT')
assert abs(_medir(ce)[0] - 24000) < 500, f"la 'C' de prueba salió mal: {_medir(ce)[0]:.1f} mm³"

assert extrude_down.extrude_down(ctx, ce, 30.0, 0.0), "la 'C': el relleno devolvió False"
vol_ce, zmin_ce, zmax_ce, abiertas_ce, _ = _medir(ce)
assert abs(vol_ce - 27000) / 27000 < 0.05, \
    f"la muesca no se rellenó: {vol_ce:.1f} mm³, se esperaba 27000 (el cubo entero)"
assert abs(zmin_ce) < 1e-4 and abs(zmax_ce - 30) < 1e-3, f"la 'C' cambió de alto ({zmin_ce}, {zmax_ce})"
assert abiertas_ce == 0, f"la 'C' quedó abierta ({abiertas_ce} aristas)"

# el complemento: por el agujero de un toro NO hay pieza arriba, así que no se
# rellena. Es lo que separa "rellenar bajo la pieza" de "extruir la silueta".
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_torus_add(major_radius=12.0, minor_radius=4.0, location=(400, 200, 8))
toro = bpy.context.active_object
assert extrude_down.extrude_down(ctx, toro, 12.0, 0.0), "toro: el relleno devolvió False"
vol_toro, zmin_toro, _, abiertas_toro, rmin_toro = _medir(toro)
assert abs(zmin_toro) < 1e-4 and abiertas_toro == 0, "toro: fondo o malla mal cerrados"
assert rmin_toro > 7.5, f"se tapó el agujero del toro (hay geometría a {rmin_toro:.2f} mm del eje)"
assert vol_toro < 9000, f"toro: {vol_toro:.1f} mm³, demasiado para tener el agujero abierto"

# una pieza rotada rellena igual de vertical: el cálculo va en espacio mundo
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(size=30.0, location=(400, 300, 25))
cubo_rot = bpy.context.active_object
cubo_rot.rotation_euler = (0.0, math.radians(30), 0.0)
bpy.context.view_layer.update()
alto_rot = _medir(cubo_rot)[2]
assert extrude_down.extrude_down(ctx, cubo_rot, alto_rot, 0.0), "cubo rotado: el relleno devolvió False"
_, zmin_rot, zmax_rot, abiertas_rot, _ = _medir(cubo_rot)
assert abs(zmin_rot) < 1e-4, f"cubo rotado: el fondo no quedó en Z=0 ({zmin_rot})"
assert abs(zmax_rot - alto_rot) < 1e-3, f"cubo rotado: se movió la parte de arriba ({zmax_rot})"
assert abiertas_rot == 0, f"cubo rotado: malla abierta ({abiertas_rot})"

# casos borde: no debe tocar la malla si el plano no sirve
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_uv_sphere_add(radius=15.0, location=(400, 400, 15))
intacta = bpy.context.active_object
n_verts = len(intacta.data.vertices)
assert not extrude_down.extrude_down(ctx, intacta, 0.0, 0.0), "plano en el fondo de la pieza debía dar False"
assert not extrude_down.extrude_down(ctx, intacta, 5.0, 5.0), "fondo == plano debía dar False"
assert not extrude_down.extrude_down(ctx, intacta, 5.0, 9.0), "fondo por encima del plano debía dar False"
assert len(intacta.data.vertices) == n_verts, "la malla se tocó pese a devolver False"

# el escalón que muestra el panel tiene que ser el que se usa para muestrear:
# el número abstracto de la grilla no le dice nada a nadie, porque depende del
# tamaño de la pieza (la misma resolución en un colgante de 4 mm y en uno de
# 40 mm da escalones diez veces distintos)
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(size=30.0, location=(600, 200, 15))
medida = bpy.context.active_object
paso256 = extrude_down.paso_silueta(medida, 256)
assert abs(paso256 - 30 * 1.05 / 256) < 1e-6, f"el escalón de una pieza de 30 mm a 256 dio {paso256}"
assert abs(extrude_down.paso_silueta(medida, 512) - paso256 / 2) < 1e-9, \
    "duplicar la resolución debería partir el escalón a la mitad"

# EL CASO QUE DESTRABA A LEO: una pieza pesada tiene que rellenarse en segundos.
# La primera versión barría cara a cara y su sombra se auto-intersecaba, así que
# esto eran minutos y quedaba rechazado por un techo de caras. Este assert es lo
# que impide volver a ese planteo.
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=7, radius=15.0, location=(400, 500, 15))
pesada = bpy.context.active_object
caras_pesada = len(pesada.data.polygons)
# con estas caras hacia arriba, el barrido cara a cara tardaba 55 s medidos
assert caras_pesada > 50000, f"la malla de prueba tiene {caras_pesada} caras, hacen falta bastantes más"
t0 = time.time()
assert extrude_down.extrude_down(ctx, pesada, 30.0, 0.0), "malla pesada: el relleno devolvió False"
tardo = time.time() - t0
vol_p, zmin_p, _, abiertas_p, _ = _medir(pesada)
assert tardo < 30, f"rellenar {caras_pesada} caras tardó {tardo:.1f}s — el método no escala"
assert abs(zmin_p) < 1e-4, f"malla pesada: el fondo no quedó en Z=0 ({zmin_p})"
assert abiertas_p == 0, f"malla pesada: malla abierta ({abiertas_p})"
esperado_p = 2 / 3 * math.pi * 15 ** 3 + math.pi * 15 ** 2 * 15
assert abs(vol_p - esperado_p) / esperado_p < 0.05, f"malla pesada: volumen {vol_p:.1f} mm³"

# el plano de altura nace ARRIBA, horizontal, sin poder inclinarse y sin poder
# salirse de la pieza
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(size=30.0, location=(500, 0, 20))
pieza = bpy.context.active_object
bpy.ops.siro.extrude_plane()
plano = bpy.context.scene.objects.get(gp.CUTTER_NAME)
assert plano is not None, "el plano de altura no se creó"
assert abs(plano.location.z - 35.0) < 1e-4, f"el plano debía nacer en el tope de la pieza ({plano.location.z})"
assert all(abs(a) < 1e-6 for a in plano.rotation_euler), "el plano de altura debía salir horizontal"
assert all(plano.lock_rotation), "el plano de altura debía quedar bloqueado en rotación"

for intento, tope in ((999.0, 35.0), (-999.0, 5.0)):
    plano.location.z = intento
    bpy.context.view_layer.update()
    real = plano.matrix_world.translation.z
    assert abs(real - tope) < 1e-4, \
        f"el plano se salió de la pieza: pedido {intento}, quedó en {real}, se esperaba {tope}"

# y el operador completo rellena hasta el fondo de la escena sin recortar nada
bpy.context.scene.siro_base_z = 0.0
plano.location.z = 30.0
bpy.context.view_layer.update()
bpy.ops.siro.extrude_down()
assert bpy.context.scene.objects.get(gp.CUTTER_NAME) is None, "el plano debía limpiarse tras rellenar"
vol_op, zmin_op, zmax_op, abiertas_op, _ = _medir(pieza)
assert abs(zmin_op) < 1e-4, f"el operador no rellenó hasta Z=0 ({zmin_op})"
assert abs(zmax_op - 35) < 1e-3, f"el operador movió la parte de arriba ({zmax_op})"
assert abs(vol_op - 30 * 30 * 35) / (30 * 30 * 35) < 0.02, \
    f"el operador no rellenó el cubo entero hasta la base ({vol_op:.1f} mm³)"
assert abiertas_op == 0, f"el operador dejó la malla abierta ({abiertas_op})"

# rellenar necesita una malla cerrada: sobre una abierta el boolean de unión no
# puede dar un resultado correcto, así que tiene que decirlo en vez de intentarlo
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(size=30.0, location=(600, 0, 15))
rota = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(rota.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES')
bm.to_mesh(rota.data)
bm.free()
bpy.ops.siro.extrude_plane()
verts_rota = len(rota.data.vertices)
try:
    bpy.ops.siro.extrude_down()
    raise SystemExit("rellenar una malla abierta debía dar error")
except RuntimeError as err:
    assert "aristas abiertas" in str(err), f"el error no explica la malla abierta: {err}"
assert len(rota.data.vertices) == verts_rota, "la malla abierta se tocó pese al error"
bpy.ops.siro.cancel_cut()

# --- reparar pellizcos: la forma exacta del defecto del cráneo de Leo ---
# Dos cubos que se tocan por una sola arista: al soldarlos, esa arista queda
# compartida por 4 caras. No es un agujero ni una cara interior, así que la
# pasada de Reparar no lo veía — y el mensaje aconsejaba subir el soldado, que
# ahí no arregla nada.
from sirobuilder.operators.repair import _pinched_edges

bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(size=10.0, location=(700, 0, 5))
p1 = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=10.0, location=(710, 10, 5))
p2 = bpy.context.active_object
p1.select_set(True)
bpy.context.view_layer.objects.active = p1
bpy.ops.object.join()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0001)
bpy.ops.object.mode_set(mode='OBJECT')
assert _pinched_edges(p1) > 0, "el test necesita una arista pellizcada (compartida por 4 caras)"

bpy.ops.siro.repair()

assert _pinched_edges(p1) == 0, f"reparar dejó {_pinched_edges(p1)} aristas pellizcadas"
assert _mesh_stats(p1)[1] == 0, f"reparar dejó la malla no-manifold: {_mesh_stats(p1)}"

# --- reparar no puede dejar la pieza PEOR de lo que llegó ---
# Una pieza rellenada está cerrada pero llena de caras de área cero (las deja el
# boolean de unión). El soldado y la disolución, sobre eso, borran caras y abren
# la superficie: medido, una esfera rellenada sana salía con 3064 aristas de
# borde donde no había ninguna, tras 23,5 s de trabajo.
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_uv_sphere_add(radius=8.0, segments=32, ring_count=16, location=(800, 0, 12))
_rell = bpy.context.active_object
bpy.context.view_layer.objects.active = _rell
assert extrude_down.extrude_down(bpy.context, _rell, 20.0, 0.0, 256), "el test necesita la pieza rellenada"
_bm = bmesh.new(); _bm.from_mesh(_rell.data)
_degeneradas = sum(1 for f in _bm.faces if f.calc_area() < 1e-9)
_vol_antes = _bm.calc_volume(signed=True)
_bm.free()
assert _degeneradas > 0, "el test necesita las caras de área cero que deja el relleno"
assert _mesh_stats(_rell)[1] == 0, "la pieza rellenada tenía que llegar sana"

bpy.ops.object.select_all(action='DESELECT')
_rell.select_set(True)
bpy.context.view_layer.objects.active = _rell
bpy.ops.siro.repair()

_bm = bmesh.new(); _bm.from_mesh(_rell.data)
_vol_despues = _bm.calc_volume(signed=True)
_bm.free()
assert _mesh_stats(_rell)[1] == 0, \
    f"reparar rompió una pieza que llegó sana: {_mesh_stats(_rell)[1]} aristas no-manifold"
assert abs(_vol_despues - _vol_antes) < 1e-4, \
    f"reparar cambió una pieza que no necesitaba reparación: {_vol_antes:.1f} → {_vol_despues:.1f}"

# el corte por forma empuja su propio paso de deshacer: sin esto, Ctrl+Z se
# come el paso anterior en vez del corte (no se puede probar headless, el undo
# global está apagado en background)
assert "ed.undo_push" in pathlib.Path(shape_cut.__file__).read_text(), \
    "el corte por forma debe empujar un paso de deshacer por corte"

# Los botones de la toolbar no pueden heredar las propiedades de la última
# corrida: Leo bajó el ratio de Simplificar a 1 en el panel de rehacer y el
# botón quedó inservible sin ninguna pista. _boton las resetea a su default.
for idname in ("siro.simplify", "siro.repair", "siro.boolean", "siro.mirror", "siro.align_base",
               "siro.prep_depthmap", "siro.bake_depthmap"):
    assert f'"{idname}"' in fuente_lab, f"{idname} debería estar en el panel"
    assert f'.operator("{idname}"' not in fuente_lab, \
        f"{idname} se dibuja con layout.operator: heredaría las props de la última vez"
    # y el supuesto sobre el que se apoya _boton: toda propiedad escribible del
    # operador tiene un default legible que se le puede volver a asignar. El
    # draw() no se puede correr headless, pero esto sí, y es lo que podría
    # reventarlo (un draw() que revienta deja el panel VACÍO, sin error visible)
    clase = getattr(bpy.types, "SIRO_OT_" + idname.split(".")[1])
    for prop in clase.bl_rna.properties:
        if prop.identifier == "rna_type" or prop.is_readonly:
            continue
        assert hasattr(prop, "default"), f"{idname}.{prop.identifier} no tiene default legible"

for op in ("SIRO_OT_extrude_plane", "SIRO_OT_extrude_down"):
    assert hasattr(bpy.types, op), f"{op} no quedó registrado"

print("OK tools")
