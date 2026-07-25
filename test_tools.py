# Correr con: blender -b -P test_tools.py
import pathlib
import sys
import tempfile

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

bpy.ops.siro.apply_relief()

assert not relief.modifiers, "aplicar relieve debía consumir los modifiers"
zs = [v.co.z for v in relief.data.vertices]
assert max(zs) - min(zs) > 0.2, f"el relieve no generó altura: rango z = {max(zs) - min(zs)}"
bm = bmesh.new()
bm.from_mesh(relief.data)
abiertas = sum(1 for e in bm.edges if not e.is_manifold)
bm.free()
assert abiertas == 0, f"el relieve aplicado quedó abierto ({abiertas} aristas) — no es fusionable"

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

# --- modo acople: toggle de snapping cara a cara ---
ts = bpy.context.scene.tool_settings
bpy.ops.siro.snap_dock()
assert ts.use_snap and ts.snap_elements == {'FACE'} and ts.use_snap_align_rotation, "acople no se activó"
bpy.ops.siro.snap_dock()
assert not ts.use_snap, "acople no se desactivó"

# --- alinear a la base: z mínimo mundial queda en 0 ---
from mathutils import Vector

bpy.ops.mesh.primitive_cube_add(size=2, location=(20, 0, 3.7))
acube = bpy.context.active_object
bpy.ops.siro.align_base()
bpy.context.view_layer.update()
min_z = min((acube.matrix_world @ Vector(c)).z for c in acube.bound_box)
assert abs(min_z) < 1e-5, f"alinear a la base dejó z mínimo en {min_z}"

# --- corte libre: contorno cuadrado sobre un cubo = galleta 1×1×2 sellada ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(30, 0, 0))
fcube = bpy.context.active_object
cdata = bpy.data.curves.new("SiroContorno", 'CURVE')
cdata.dimensions = '3D'
spline = cdata.splines.new('POLY')
spline.points.add(4)  # termina cerca del inicio → se detecta como contorno cerrado
square = ((29.5, -0.5, 2, 1), (30.5, -0.5, 2, 1), (30.5, 0.5, 2, 1), (29.5, 0.5, 2, 1), (29.5, -0.45, 2, 1))
for pt, co in zip(spline.points, square):
    pt.co = co
cobj = bpy.data.objects.new("SiroContorno", cdata)
bpy.context.collection.objects.link(cobj)
cobj["siro_target"] = fcube.name

bpy.ops.siro.free_cut(mode='A')
bpy.context.view_layer.update()

assert "SiroContorno" not in bpy.data.objects, "el contorno debía borrarse tras recortar"
assert "SiroPrisma" not in bpy.data.objects, "el prisma cortador debía borrarse"
d = fcube.dimensions
assert abs(d.x - 1) < 0.01 and abs(d.y - 1) < 0.01 and abs(d.z - 2) < 0.01, f"corte libre dims {tuple(d)}"
bm = bmesh.new()
bm.from_mesh(fcube.data)
assert all(e.is_manifold for e in bm.edges), "el corte libre no quedó sellado/manifold"
bm.free()

# --- trazo denso: se simplifica antes del boolean y el corte no se cuelga ---
import math

from sirobuilder.operators import free_cut as fc

bpy.ops.mesh.primitive_cube_add(size=2, location=(50, 0, 0))
dcube = bpy.context.active_object
cdata2 = bpy.data.curves.new("SiroContorno", 'CURVE')
cdata2.dimensions = '3D'
sp2 = cdata2.splines.new('POLY')
sp2.points.add(719)
for i, pt in enumerate(sp2.points):
    ang = 2 * math.pi * i / 720
    pt.co = (50 + 0.6 * math.cos(ang), 0.6 * math.sin(ang), 2, 1)
cobj2 = bpy.data.objects.new("SiroContorno", cdata2)
bpy.context.collection.objects.link(cobj2)
cobj2["siro_target"] = dcube.name

assert len(fc._stroke_points(cobj2)) < 80, "el RDP no simplificó el trazo denso"

bpy.ops.siro.free_cut(mode='A')
bpy.context.view_layer.update()
d = dcube.dimensions
assert abs(d.x - 1.2) < 0.05 and abs(d.z - 2) < 0.01, f"corte circular dims {tuple(d)}"
bm = bmesh.new()
bm.from_mesh(dcube.data)
assert all(e.is_manifold for e in bm.edges), "el corte circular no quedó manifold"
bm.free()

# --- cuchillo: línea abierta de lado a lado parte el cubo en dos mitades selladas ---
bpy.ops.mesh.primitive_cube_add(size=2, location=(60, 0, 0))
kcube = bpy.context.active_object
kdata = bpy.data.curves.new("SiroContorno", 'CURVE')
kdata.dimensions = '3D'
ksp = kdata.splines.new('POLY')
ksp.points.add(2)
for pt, co in zip(ksp.points, ((60, -2, 2, 1), (60, 0, 2, 1), (60, 2, 2, 1))):
    pt.co = co
kobj = bpy.data.objects.new("SiroContorno", kdata)
bpy.context.collection.objects.link(kobj)
kobj["siro_target"] = kcube.name

before = set(bpy.data.objects)
bpy.ops.siro.free_cut(mode='BOTH')
bpy.context.view_layer.update()
new = list(set(bpy.data.objects) - before)
assert len(new) == 1, f"el cuchillo BOTH debía crear 1 objeto nuevo, creó {len(new)}"
for half in (kcube, new[0]):
    bm = bmesh.new()
    bm.from_mesh(half.data)
    xs = [v.co.x + half.location.x for v in bm.verts]
    assert all(e.is_manifold for e in bm.edges), f"mitad {half.name} no quedó sellada"
    assert (max(xs) <= 60 + 1e-4) or (min(xs) >= 60 - 1e-4), f"mitad {half.name} cruza la línea de corte"
    bm.free()

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

bpy.ops.siro.boolean(operation='UNION')
bpy.context.view_layer.update()

assert op_b_name in bpy.data.objects, "la pieza de malla abierta no debía desaparecer"

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
from sirobuilder.ui import panels as P

for idname, texto, icono, props in P.PRIMITIVAS:
    modulo, op = idname.split(".")
    getattr(getattr(bpy.ops, modulo), op)(location=(200, 0, 0), **props)
    d = bpy.context.active_object.dimensions
    assert 28 <= max(d) <= 33, f"{texto} sale de {max(d):.1f} mm, se esperaba ~30"

iconos = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items.keys()
secciones = (P.SIRO_PT_add, P.SIRO_PT_transform, P.SIRO_PT_cut,
             P.SIRO_PT_mesh, P.SIRO_PT_place, P.SIRO_PT_relief)
for cls in (P.SIRO_PT_main, *secciones):
    assert hasattr(bpy.types, cls.__name__), f"{cls.__name__} no quedó registrado"
for cls in secciones:
    assert cls.bl_icon in iconos, f"{cls.__name__}: ícono inválido '{cls.bl_icon}'"
assert len({c.bl_icon for c in secciones}) == len(secciones), "dos secciones comparten ícono"

# --- cortador por forma: cerrado y manifold en ortográfica y en perspectiva ---
from sirobuilder.operators import shape_cut


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

# --- pestaña SiroLab: registrada aparte, sin tocar el toolbar principal ---
assert hasattr(bpy.types, "SIRO_PT_lab"), "el panel de SiroLab no quedó registrado"
assert P.SIRO_PT_lab.bl_category == "SiroLab", "SiroLab debía ir en pestaña aparte"
assert P.SIRO_PT_main.bl_category == "SiroBuilder", "el toolbar principal no se toca"
assert hasattr(bpy.types, "SIRO_OT_shape_cut"), "el operador de corte por forma no quedó registrado"
for ident, nombre, desc, icono in shape_cut.SHAPES:
    assert icono in iconos, f"forma {ident}: ícono inválido '{icono}'"
for prop in ("siro_shape", "siro_keep", "siro_solver"):
    assert hasattr(bpy.context.scene, prop), f"falta la propiedad de escena {prop}"

print("OK tools")
