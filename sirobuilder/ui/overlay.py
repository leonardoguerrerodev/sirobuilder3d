import blf
import bpy

_handler = None


def handler_active():
    return _handler is not None


def _draw():
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return
    scale = bpy.context.scene.unit_settings.scale_length
    mm = [d * scale * 1000.0 for d in obj.dimensions]
    font_id = 0
    blf.size(font_id, 18)
    blf.position(font_id, 20, 20, 0)
    blf.color(font_id, 1.0, 0.6, 0.2, 1.0)
    blf.draw(font_id, "%.2f × %.2f × %.2f mm" % tuple(mm))


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
