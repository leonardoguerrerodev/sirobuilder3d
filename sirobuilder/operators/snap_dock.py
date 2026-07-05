import bpy


def dock_active(tool_settings):
    return (
        tool_settings.use_snap
        and 'FACE' in tool_settings.snap_elements
        and tool_settings.use_snap_align_rotation
    )


class SIRO_OT_snap_dock(bpy.types.Operator):
    """Modo Acople: al mover una pieza (G) cerca de otra, se pega cara a cara y alinea la rotación"""
    bl_idname = "siro.snap_dock"
    bl_label = "Modo Acople"

    def execute(self, context):
        ts = context.scene.tool_settings
        if dock_active(ts):
            ts.use_snap = False
            ts.snap_elements = {'INCREMENT'}
            ts.use_snap_align_rotation = False
        else:
            ts.use_snap = True
            ts.snap_elements = {'FACE'}
            ts.snap_target = 'CLOSEST'
            ts.use_snap_align_rotation = True
        return {'FINISHED'}
