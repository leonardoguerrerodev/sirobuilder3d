import bpy


class SIRO_OT_boolean(bpy.types.Operator):
    """Fusionar: une las piezas seleccionadas a la activa. Restar: quita las seleccionadas de la activa.
La pieza activa (la última que clickeaste) es la que recibe el resultado"""
    bl_idname = "siro.boolean"
    bl_label = "Boolean"
    bl_options = {'REGISTER', 'UNDO'}

    operation: bpy.props.EnumProperty(
        name="Operación",
        items=(
            ('UNION', "Fusionar", "Une las piezas en un sólido único"),
            ('DIFFERENCE', "Restar", "Resta las piezas seleccionadas de la activa"),
        ),
        default='DIFFERENCE',
    )
    solver: bpy.props.EnumProperty(
        name="Calidad",
        items=(
            ('EXACT', "Exacta", "Robusta, la indicada para piezas finales"),
            ('FLOAT', "Rápida", "Liviana, para mallas muy densas"),
        ),
        default='EXACT',
    )
    delete_operands: bpy.props.BoolProperty(
        name="Borrar piezas usadas",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None and obj.type == 'MESH'
            and sum(o.type == 'MESH' for o in context.selected_objects) >= 2
        )

    def execute(self, context):
        target = context.active_object
        tools = [o for o in context.selected_objects if o is not target and o.type == 'MESH']
        for tool in tools:
            mod = target.modifiers.new("SiroBool", 'BOOLEAN')
            mod.object = tool
            mod.operation = self.operation
            mod.solver = self.solver
            bpy.ops.object.modifier_apply(modifier=mod.name)
            if self.delete_operands:
                data = tool.data
                bpy.data.objects.remove(tool, do_unlink=True)
                if not data.users:
                    bpy.data.meshes.remove(data)
        verbo = "fusionadas con" if self.operation == 'UNION' else "restadas de"
        self.report({'INFO'}, f"{len(tools)} piezas {verbo} {target.name}")
        return {'FINISHED'}
