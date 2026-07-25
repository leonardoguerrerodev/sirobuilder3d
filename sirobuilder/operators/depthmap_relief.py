import bmesh
import bpy
from bpy_extras.io_utils import ImportHelper

DISP_MOD = "SiroRelieve"
# densidad calcada de depth_maps.blend (malla horneada de 607×607 verts, sin
# Subsurf): un Subsurf nivel 9 en vivo + Displace encima obliga a Blender a
# recalcular ~262k caras por CPU en cada evaluación (Displace después de
# Subsurf desactiva el subdivision rápido por GPU). Hornear la densidad una
# sola vez al crear el plano es lo que hace fluido a depth_maps.blend.
GRID_RES = 607


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

        # tamaño base 2 (local -1..1): con coords LOCAL la imagen mapea el plano completo,
        # igual que en depth_maps.blend; el tamaño real se da con la escala del objeto.
        # Grid ya horneado a la densidad final (nada de Subsurf en vivo) — ver GRID_RES arriba.
        # x/y_subdivisions son cortes, no vértices: -1 para dar GRID_RES vértices por lado
        bpy.ops.mesh.primitive_grid_add(
            x_subdivisions=GRID_RES - 1, y_subdivisions=GRID_RES - 1, size=2.0
        )
        obj = context.active_object
        obj.name = "Relieve"
        # proporción real de la imagen cargada — nunca hardcodeada (a diferencia
        # del .blend de referencia, que sí la tiene fija)
        aspect = img.size[1] / img.size[0] if img.size[0] and img.size[1] else 1.0
        obj.scale = (2.5, 2.5 * aspect, 1.0)  # 25% del tamaño original (5 mm de ancho)

        # valores calcados de depth_maps.blend (referencia de Leo)
        tex = bpy.data.textures.new(img.name, 'IMAGE')
        tex.image = img
        tex.extension = 'CLIP'
        tex.filter_size = 6.22  # "Suavizado"

        disp = obj.modifiers.new(DISP_MOD, 'DISPLACE')
        disp.texture = tex
        disp.texture_coords = 'LOCAL'
        disp.mid_level = 0.5
        disp.strength = 1.0
        return {'FINISHED'}


class SIRO_OT_apply_relief(bpy.types.Operator):
    """Convierte el relieve en malla real y cerrada, lista para recortar el contorno y unir al resto de la pieza"""
    bl_idname = "siro.apply_relief"
    bl_label = "Aplicar relieve"
    bl_options = {'REGISTER', 'UNDO'}

    base_thickness: bpy.props.FloatProperty(
        name="Grosor de base (mm)",
        description="Espesor que se le da a la lámina para que sea un sólido fusionable",
        default=1.0,
        min=0.1,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and DISP_MOD in obj.modifiers

    def execute(self, context):
        obj = context.active_object
        if DISP_MOD in obj.modifiers:
            bpy.ops.object.modifier_apply(modifier=DISP_MOD)

        # el grid desplazado es una lámina abierta: sin volumen, fusionarlo con
        # una pieza da basura no-manifold (EXACT) o no hace nada (MANIFOLD)
        solid = obj.modifiers.new("SiroGrosor", 'SOLIDIFY')
        solid.thickness = self.base_thickness
        solid.offset = -1.0  # crece hacia abajo, la cara con relieve no se mueve
        bpy.ops.object.modifier_apply(modifier=solid.name)

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {'FINISHED'}
