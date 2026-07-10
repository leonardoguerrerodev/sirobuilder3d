import blf
import bpy
from mathutils import Vector

from ..operators.group import GROUP_KEY

_handler = None


def handler_active():
    return _handler is not None


def _dimensions_mm(obj, context):
    """Dimensiones en mm de la pieza activa; si pertenece a un grupo, devuelve
    el bounding box combinado de todo el grupo (piezas agrupadas se miden como
    un conjunto, no cada una por separado)"""
    scale = context.scene.unit_settings.scale_length
    gid = obj.get(GROUP_KEY)
    if gid is not None:
        mn = mx = None
        for other in context.scene.objects:
            if other.type != 'MESH' or other.get(GROUP_KEY) != gid:
                continue
            for corner in other.bound_box:
                world_co = other.matrix_world @ Vector(corner)
                if mn is None:
                    mn, mx = world_co.copy(), world_co.copy()
                else:
                    mn.x, mn.y, mn.z = min(mn.x, world_co.x), min(mn.y, world_co.y), min(mn.z, world_co.z)
                    mx.x, mx.y, mx.z = max(mx.x, world_co.x), max(mx.y, world_co.y), max(mx.z, world_co.z)
        if mn is not None:
            return [d * scale * 1000.0 for d in (mx - mn)], True
    return [d * scale * 1000.0 for d in obj.dimensions], False


def _draw():
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return
    mm, is_group = _dimensions_mm(obj, bpy.context)
    font_id = 0
    blf.size(font_id, 18)
    blf.position(font_id, 20, 20, 0)
    blf.color(font_id, 1.0, 0.6, 0.2, 1.0)
    label = "%.2f × %.2f × %.2f mm" % tuple(mm)
    if is_group:
        label += " (grupo)"
    blf.draw(font_id, label)


class SIRO_OT_toggle_dims(bpy.types.Operator):
    """Muestra u oculta las dimensiones de la pieza activa en el viewport"""
    bl_idname = "siro.toggle_dims"
    bl_label = "Dimensiones en pantalla"

    def execute(self, context):
        global _handler
        if _handler is None:
            _handler = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')
        else:
            remove_handler()
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


def remove_handler():
    global _handler
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        _handler = None
