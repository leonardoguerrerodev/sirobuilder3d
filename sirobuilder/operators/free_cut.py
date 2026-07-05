import bpy

from .cut import CONTOUR_NAME


class SIRO_OT_draw_contour(bpy.types.Operator):
    """Paso 1: dibuja a mano alzada el contorno de corte sobre la pieza (mantén presionado el botón izquierdo).
Cuando termines, pulsa Recortar con contorno"""
    bl_idname = "siro.draw_contour"
    bl_label = "Dibujar contorno"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        target = context.active_object
        old = context.scene.objects.get(CONTOUR_NAME)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)

        data = bpy.data.curves.new(CONTOUR_NAME, 'CURVE')
        data.dimensions = '3D'
        curve = bpy.data.objects.new(CONTOUR_NAME, data)
        context.collection.objects.link(curve)
        curve["siro_target"] = target.name

        bpy.ops.object.select_all(action='DESELECT')
        curve.select_set(True)
        context.view_layer.objects.active = curve
        bpy.ops.object.mode_set(mode='EDIT')

        paint = context.scene.tool_settings.curve_paint_settings
        paint.depth_mode = 'SURFACE'  # el trazo se apoya sobre la pieza
        paint.curve_type = 'POLY'
        bpy.ops.wm.tool_set_by_id(name="builtin.draw")

        self.report({'INFO'}, "Dibuja el contorno sobre la pieza y pulsa Recortar con contorno")
        return {'FINISHED'}


class SIRO_OT_free_cut(bpy.types.Operator):
    """Paso 2: proyecta el contorno dibujado sobre la pieza desde la vista actual y recorta"""
    bl_idname = "siro.free_cut"
    bl_label = "Recortar con contorno"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Conservar",
        items=(
            ('INSIDE', "Interior del contorno", "Borra lo que queda fuera del contorno"),
            ('OUTSIDE', "Exterior del contorno", "Borra lo que queda dentro del contorno"),
            ('MARK', "Solo marcar el corte", "Corta las aristas sin borrar nada"),
        ),
        default='INSIDE',
    )

    @classmethod
    def poll(cls, context):
        return (
            context.scene.objects.get(CONTOUR_NAME) is not None
            or (context.active_object is not None and context.active_object.type == 'MESH')
        )

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        contour = context.scene.objects.get(CONTOUR_NAME)
        if contour is not None:
            if not any(len(s.points) or len(s.bezier_points) for s in contour.data.splines):
                self.report({'ERROR'}, "El contorno está vacío — pulsa Dibujar contorno y traza sobre la pieza")
                return {'CANCELLED'}
            target = context.scene.objects.get(contour.get("siro_target", ""))
            if target is None or target.type != 'MESH':
                self.report({'ERROR'}, "No encuentro la pieza — vuelve a Dibujar contorno con la pieza activa")
                return {'CANCELLED'}
            cutter = contour
        else:
            # sin contorno dibujado: usar el par seleccionado (contorno + pieza activa)
            target = context.active_object
            others = [o for o in context.selected_objects if o is not target]
            if len(others) != 1 or others[0].type not in {'CURVE', 'MESH'}:
                self.report({'ERROR'}, "Primero pulsa Dibujar contorno (o selecciona contorno + pieza)")
                return {'CANCELLED'}
            cutter = others[0]

        bpy.ops.object.select_all(action='DESELECT')
        cutter.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        try:
            # proyecta el contorno desde la vista y corta a través; deja
            # seleccionadas las caras dentro de la silueta
            bpy.ops.mesh.knife_project(cut_through=True)
            if self.mode == 'INSIDE':
                bpy.ops.mesh.select_all(action='INVERT')
            if self.mode != 'MARK':
                bpy.ops.mesh.delete(type='FACE')
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')

        if cutter.name.startswith(CONTOUR_NAME):
            data = cutter.data
            bpy.data.objects.remove(cutter, do_unlink=True)
            if not data.users:
                bpy.data.curves.remove(data)
        return {'FINISHED'}
