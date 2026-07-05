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
assert max(zs) - min(zs) > 0.5, f"el relieve no generó altura: rango z = {max(zs) - min(zs)}"

print("OK tools")
