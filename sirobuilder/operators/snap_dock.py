import bpy

# Lo que el usuario tenía puesto antes de encender el modo. Va en la escena y no
# en un global de módulo a propósito: el snapping vive en `tool_settings`, que se
# guarda en el .blend, así que lo que hay que devolver tiene que sobrevivir lo
# mismo que lo que se pisó.
PREVIO_KEY = "siro_snap_previo"


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
        scene = context.scene
        ts = scene.tool_settings
        if dock_active(ts):
            # apagar es DEVOLVER lo que había, no imponer otros valores fijos:
            # antes, encender y apagar el modo te dejaba el snap apagado y en
            # 'INCREMENT' aunque hubieras estado trabajando con snap a vértices
            previo = scene.get(PREVIO_KEY)
            if previo:
                ts.use_snap = previo["use_snap"]
                ts.snap_elements = set(previo["elements"])
                ts.use_snap_align_rotation = previo["align"]
                del scene[PREVIO_KEY]
            else:
                ts.use_snap = False  # se encendió en otra sesión: no hay qué devolver
        else:
            scene[PREVIO_KEY] = {
                "use_snap": ts.use_snap,
                "elements": list(ts.snap_elements),
                "align": ts.use_snap_align_rotation,
            }
            ts.use_snap = True
            ts.snap_elements = {'FACE'}
            ts.snap_target = 'CLOSEST'
            ts.use_snap_align_rotation = True
        return {'FINISHED'}
