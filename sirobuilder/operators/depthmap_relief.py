import bmesh
import bpy
from bpy_extras.io_utils import ImportHelper

RES_MOD = "SiroResolucion"
DISP_MOD = "SiroRelieve"


class SIRO_OT_depthmap_relief(bpy.types.Operator, ImportHelper):
    """Crea un plano con relieve a partir de una imagen en escala de grises (depthmap)"""
    bl_idname = "siro.depthmap_relief"
    bl_label = "Nuevo relieve desde imagen"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp",
        options={'HIDDEN'},
    )

    def execute(self, context):
        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError:
            self.report({'ERROR'}, f"No pude cargar la imagen: {self.filepath}")
            return {'CANCELLED'}
        # espacio de color: se queda en sRGB (decidido en el plan), que es el default al cargar

        bpy.ops.mesh.primitive_plane_add(size=20.0)  # 20 mm de partida con la escena en mm
        obj = context.active_object
        obj.name = "Relieve"
        if img.size[0] and img.size[1]:
            obj.scale.y = img.size[1] / img.size[0]  # respeta la proporción de la imagen

        sub = obj.modifiers.new(RES_MOD, 'SUBSURF')
        sub.subdivision_type = 'SIMPLE'
        sub.levels = sub.render_levels = 7  # ponytail: resolución = subsurf simple; grid real si algún día hace falta malla no uniforme

        tex = bpy.data.textures.new(img.name, 'IMAGE')
        tex.image = img
        tex.extension = 'CLIP'
        tex.filter_size = 6.0  # "Suavizado" — valor de partida cercano al 6.22 de referencia

        disp = obj.modifiers.new(DISP_MOD, 'DISPLACE')
        disp.texture = tex
        disp.texture_coords = 'UV'
        disp.mid_level = 0.0  # negro = base del plano, blanco = altura máxima
        disp.strength = 2.0   # mm
        return {'FINISHED'}


class SIRO_OT_apply_relief(bpy.types.Operator):
    """Convierte el relieve en malla real, lista para recortar el contorno y unir al resto de la pieza"""
    bl_idname = "siro.apply_relief"
    bl_label = "Aplicar relieve"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and DISP_MOD in obj.modifiers

    def execute(self, context):
        obj = context.active_object
        for name in (RES_MOD, DISP_MOD):
            if name in obj.modifiers:
                bpy.ops.object.modifier_apply(modifier=name)

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {'FINISHED'}
