import bpy

from .operators import cut, depthmap_relief, repair, simplify
from .ui import panels

_classes = (
    cut.SIRO_OT_add_cut_plane,
    cut.SIRO_OT_cut,
    repair.SIRO_OT_repair,
    simplify.SIRO_OT_simplify,
    depthmap_relief.SIRO_OT_depthmap_relief,
    depthmap_relief.SIRO_OT_apply_relief,
    panels.SIRO_OT_scene_mm,
    panels.SIRO_PT_main,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
