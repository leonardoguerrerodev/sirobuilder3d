import bpy

from .operators import (
    align_base,
    boolean_ops,
    camera_nav,
    cut,
    depthmap_relief,
    extrude_down,
    ghost_preview,
    group,
    mirror,
    repair,
    select_mark,
    shape_cut,
    simplify,
    snap_dock,
)
from .ui import iconos, overlay, panels

_classes = (
    cut.SIRO_OT_add_cut_plane,
    cut.SIRO_OT_cut,
    cut.SIRO_OT_cancel_cut,
    shape_cut.SIRO_OT_shape_cut,
    extrude_down.SIRO_OT_extrude_plane,
    extrude_down.SIRO_OT_extrude_down,
    camera_nav.SIRO_OT_cam_mode,
    select_mark.SIRO_OT_select_mark,
    group.SIRO_OT_group,
    group.SIRO_OT_ungroup,
    boolean_ops.SIRO_OT_boolean,
    repair.SIRO_OT_repair,
    simplify.SIRO_OT_simplify,
    mirror.SIRO_OT_mirror,
    snap_dock.SIRO_OT_snap_dock,
    align_base.SIRO_OT_align_base,
    depthmap_relief.SIRO_OT_depthmap_relief,
    depthmap_relief.SIRO_OT_apply_relief,
    overlay.SIRO_OT_toggle_dims,
    panels.SIRO_OT_scene_mm,
    # Una sola pestaña y secciones al ras: el orden de registro ES el orden en
    # que se dibujan, y sigue el flujo de trabajo — acciones → añadir →
    # transformar → cortar (plano, forma) → rellenar → malla → colocar → relieve.
    panels.SIRO_PT_main,
    panels.SIRO_PT_add,
    panels.SIRO_PT_transform,
    panels.SIRO_PT_cut,
    panels.SIRO_PT_shape_cut,
    panels.SIRO_PT_extrude,
    panels.SIRO_PT_mesh,
    panels.SIRO_PT_place,
    panels.SIRO_PT_relief,
)


def register():
    for cls in _classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            # Ya estaba registrada (versión previa del addon quedó cargada en memoria);
            # la limpiamos y volvemos a registrar la nuestra.
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)
    panels._register_props()
    iconos.register()
    camera_nav.register_keymap()
    group.register_handler()
    ghost_preview.register_driver_function()


def unregister():
    ghost_preview.unregister_driver_function()
    overlay.remove_handler()
    select_mark.disable()
    camera_nav.unregister_keymap()
    group.unregister_handler()
    iconos.unregister()
    panels._unregister_props()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
