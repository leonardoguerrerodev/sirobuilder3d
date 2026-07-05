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
assert "SiroGhost" in bpy.data.objects and "SiroCutterVol" in bpy.data.objects, "falta el preview del corte"
assert cube.modifiers.get("SiroPreview") is not None, "falta el modifier de preview en la pieza"
cutter.location.z = 0.5  # normal +Z: se conserva la parte superior
bpy.context.view_layer.update()

bpy.ops.siro.cut()

for leftover in ("SiroCutter", "SiroGhost", "SiroCutterVol"):
    assert leftover not in bpy.data.objects, f"{leftover} debía borrarse tras el corte"
assert not cube.modifiers, "el modifier de preview debía quitarse tras el corte"

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

print("OK clip_plane")
