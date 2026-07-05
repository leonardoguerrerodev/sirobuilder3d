import bpy


class SIRO_OT_mirror(bpy.types.Operator):
    """Duplica la pieza en espejo sobre el eje elegido y la fusiona (Mirror aplicado en un paso)"""
    bl_idname = "siro.mirror"
    bl_label = "Espejo"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(
        name="Eje",
        items=(('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")),
        default='X',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mod = obj.modifiers.new("SiroMirror", 'MIRROR')
        mod.use_axis = (self.axis == 'X', self.axis == 'Y', self.axis == 'Z')
        bpy.ops.object.modifier_apply(modifier=mod.name)
        return {'FINISHED'}
