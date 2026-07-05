import bpy


class SIRO_OT_simplify(bpy.types.Operator):
    """Reduce la cantidad de polígonos preservando la forma (Decimate Collapse)"""
    bl_idname = "siro.simplify"
    bl_label = "Simplificar"
    bl_options = {'REGISTER', 'UNDO'}

    ratio: bpy.props.FloatProperty(
        name="Proporción",
        description="0.5 = deja la mitad de los polígonos",
        default=0.5,
        min=0.01,
        max=1.0,
        subtype='FACTOR',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        before = len(obj.data.polygons)
        mod = obj.modifiers.new("SiroDecimate", 'DECIMATE')
        mod.ratio = self.ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)
        self.report({'INFO'}, f"Caras: {before} → {len(obj.data.polygons)}")
        return {'FINISHED'}
