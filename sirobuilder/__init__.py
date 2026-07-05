import bpy

from .operators import align_base, cut, depthmap_relief, free_cut, mirror, repair, simplify, snap_dock
from .ui import overlay, panels

_classes = (
    cut.SIRO_OT_add_cut_plane,
    cut.SIRO_OT_cut,
    free_cut.SIRO_OT_free_cut,
    repair.SIRO_OT_repair,
    simplify.SIRO_OT_simplify,
    mirror.SIRO_OT_mirror,
    snap_dock.SIRO_OT_snap_dock,
    align_base.SIRO_OT_align_base,
    depthmap_relief.SIRO_OT_depthmap_relief,
    depthmap_relief.SIRO_OT_apply_relief,
    overlay.SIRO_OT_toggle_dims,
    panels.SIRO_OT_scene_mm,
    panels.SIRO_PT_main,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    overlay.remove_handler()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
