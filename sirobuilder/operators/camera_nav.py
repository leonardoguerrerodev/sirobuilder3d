import bpy

_kmis = []  # [(keymap, keymap_item)]


def nav_active():
    return bool(_kmis) and _kmis[0][1].active


def register_keymap():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:  # modo background, sin keymaps
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    for op, button in (("view3d.rotate", 'LEFTMOUSE'), ("view3d.move", 'RIGHTMOUSE')):
        kmi = km.keymap_items.new(op, button, 'CLICK_DRAG')
        kmi.active = False
        _kmis.append((km, kmi))


def unregister_keymap():
    for km, kmi in _kmis:
        km.keymap_items.remove(kmi)
    _kmis.clear()


class SIRO_OT_cam_mode(bpy.types.Operator):
    """Modo Cámara estilo 3D Builder: arrastrar con botón izquierdo orbita, con el derecho hace pan, la rueda hace zoom. El clic normal sigue seleccionando"""
    bl_idname = "siro.cam_mode"
    bl_label = "Modo Cámara"

    def execute(self, context):
        if not _kmis:
            self.report({'ERROR'}, "Keymap no disponible")
            return {'CANCELLED'}
        state = not nav_active()
        for _, kmi in _kmis:
            kmi.active = state
        return {'FINISHED'}
