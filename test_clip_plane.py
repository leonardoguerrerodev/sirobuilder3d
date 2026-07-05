# Correr con: blender -b -P test_clip_plane.py
import pathlib
import sys

import bmesh
import bpy

sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
import sirobuilder

sirobuilder.register()

bpy.ops.mesh.primitive_cube_add(size=2)  # cubo z en [-1, 1]
cube = bpy.context.active_object

bpy.ops.siro.add_cut_plane()
cutter = bpy.data.objects["SiroCutter"]
cutter.location.z = 0.5  # normal +Z: se conserva la parte superior
bpy.context.view_layer.update()

bpy.ops.siro.cut()

assert "SiroCutter" not in bpy.data.objects, "el cutter debía borrarse tras el corte"

bm = bmesh.new()
bm.from_mesh(cube.data)
zs = [v.co.z for v in bm.verts]
assert min(zs) >= 0.5 - 1e-5, f"quedó geometría bajo el plano: z min = {min(zs)}"
assert max(zs) > 0.9, "se perdió la parte que debía conservarse"
assert all(len(e.link_faces) == 2 for e in bm.edges), "malla no manifold: el corte no quedó sellado"
bm.free()

# invertir lado: se conserva la parte inferior (la pieza ahora ocupa z en [0.5, 1])
bpy.ops.siro.add_cut_plane()
bpy.data.objects["SiroCutter"].location.z = 0.75
bpy.context.view_layer.update()
bpy.ops.siro.cut(invert=True)

bm = bmesh.new()
bm.from_mesh(cube.data)
assert max(v.co.z for v in bm.verts) <= 0.75 + 1e-5, "invertir lado no conservó la parte inferior"
assert all(len(e.link_faces) == 2 for e in bm.edges), "malla no manifold tras corte invertido"
bm.free()

print("OK clip_plane")
