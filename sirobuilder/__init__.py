import bpy

from .operators import (
    align_base,
    camera_nav,
    cut,
    depthmap_relief,
    free_cut,
    group,
    mirror,
    repair,
    select_mark,
    simplify,
    snap_dock,
)
from .ui import overlay, panels

_classes = (
    cut.SIRO_OT_add_cut_plane,
    cut.SIRO_OT_cut,
    cut.SIRO_OT_cancel_cut,
    free_cut.SIRO_OT_draw_contour,
    free_cut.SIRO_OT_free_cut,
    camera_nav.SIRO_OT_cam_mode,
    select_mark.SIRO_OT_select_mark,
    group.SIRO_OT_group,
    group.SIRO_OT_ungroup,
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
    panels.SIRO_PT_add,
    panels.SIRO_PT_cut,
    panels.SIRO_PT_mesh,
    panels.SIRO_PT_place,
    panels.SIRO_PT_transform,
    panels.SIRO_PT_relief,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    camera_nav.register_keymap()
    group.register_handler()


def unregister():
    overlay.remove_handler()
    select_mark.disable()
    camera_nav.unregister_keymap()
    group.unregister_handler()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
