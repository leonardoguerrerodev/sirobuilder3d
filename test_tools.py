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
assert "SiroRelieve" in relief.modifiers and "SiroResolucion" in relief.modifiers

bpy.ops.siro.apply_relief()

assert not relief.modifiers, "aplicar relieve debía consumir los modifiers"
zs = [v.co.z for v in relief.data.vertices]
assert max(zs) - min(zs) > 0.2, f"el relieve no generó altura: rango z = {max(zs) - min(zs)}"

# --- espejo: duplica la geometría fusionada en espejo ---
bpy.ops.mesh.primitive_cube_add(size=1, location=(10, 0, 0))
mcube = bpy.context.active_object
mcube.data.transform(__import__("mathutils").Matrix.Translation((1, 0, 0)))  # aleja del origen para que no se solape
verts_before = len(mcube.data.vertices)

bpy.ops.siro.mirror(axis='X')

assert len(mcube.data.vertices) == 2 * verts_before, "espejo no duplicó la geometría"
assert not mcube.modifiers, "el modifier Mirror debía quedar aplicado"
xs = [v.co.x for v in mcube.data.vertices]
assert min(xs) < 0 < max(xs), "el espejo no quedó a ambos lados del eje"

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

print("OK tools")
