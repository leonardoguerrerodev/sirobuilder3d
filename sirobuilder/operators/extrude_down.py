"""Extrudir hacia abajo, la herramienta de Microsoft 3D Builder.

**No corta nada.** La pieza queda entera y se le AGREGA material: se mira la
pieza de arriba en proyección ortográfica y todo lo que se ve se baja recto
hasta la placa. Una esfera queda como domo sobre un cilindro; una "C" queda con
el hueco entre los brazos relleno, porque hay pieza por encima de ese hueco;
el agujero de un toro sigue abierto, porque por ahí no se ve nada. Es lo que
deja una pieza con base plana lista para fundición.

**Cómo se saca esa "altura visible", y por qué así.** Una grilla por encima de
la pieza con un Shrinkwrap en modo PROJECT hacia abajo: cada vértice cae sobre
la superficie más alta de su columna, y los que no tocan nada recortan la
silueta. Es la proyección ortográfica de 3D Builder, y Blender la resuelve en
C: 0,2 s contra una malla de 245 000 caras.

La primera versión barría cara a cara el volumen bajo el plano, y eso no
escalaba: la sombra que produce **se auto-interseca** en cuanto hay voladizos, y
resolver eso crece bastante peor que lineal — 10 240 caras tardaban 6,6 s y
40 960 tardaban 55 s, o sea que un cráneo importado eran minutos. Lo que estaba
mal era el planteo, no el tamaño de la pieza: un boolean exacto contra un target
de 245 000 caras y un operando simple tarda 1,8 s. La sombra proyectada es **de
un solo valor por columna**, así que no se auto-interseca, y eso además habilita
el solver `MANIFOLD` —que con la sombra vieja daba resultados mal— y baja el
caso pesado a 2,2 s.

El precio es que la silueta queda muestreada en la grilla: en una pieza de 30 mm,
128 son pasos de 0,23 mm, 256 de 0,12 mm y 512 de 0,06 mm.
"""

import bmesh
import bpy
from mathutils import Vector

from . import cut, ghost_preview
from .boolean_ops import (
    _apply_bool,
    _apply_pending_modifiers,
    _make_single_user,
    _open_edge_count,
)

SOMBRA_NAME = "SiroSombra"

# Tiempos y peso medidos sobre una pieza real de 220 000 caras. Lo que limita
# no es el tiempo sino la malla que sale: a 2048 son 6 millones de caras, con
# las que después no se puede trabajar, así que ese escalón no se ofrece.
RESOLUCIONES = (
    ('128', "Rápido", "El más liviano; para tantear antes de decidir"),
    ('256', "Normal", "Buen punto medio: ~2 s y una malla manejable"),
    ('512', "Fino", "El doble de detalle: ~6 s y 3 veces más caras"),
    ('1024', "Máximo", "Cuatro veces el detalle: ~18 s y 10 veces más caras — solo si el borde se nota"),
)


def _encuadre(obj):
    """Centro XY, lado y techo del cuadro donde se muestrea la pieza"""
    esquinas = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    minx = min(p.x for p in esquinas)
    maxx = max(p.x for p in esquinas)
    miny = min(p.y for p in esquinas)
    maxy = max(p.y for p in esquinas)
    lado = max(maxx - minx, maxy - miny) * 1.05
    return (minx + maxx) / 2, (miny + maxy) / 2, lado, max(p.z for p in esquinas)


def paso_silueta(obj, res):
    """Tamaño del cuadro de muestreo para esta pieza, en unidades de escena
    (mm en la escala del addon). Es lo que se ve como escalonado en el borde."""
    return _encuadre(obj)[2] / res


def z_range(obj):
    """Alto de la pieza en Z de mundo (mín, máx), medido sobre su bounding box"""
    zs = [(obj.matrix_world @ Vector(c)).z for c in obj.bound_box]
    return min(zs), max(zs)


def _sombra(context, obj, plane_z, base_z, res):
    """Lo que se ve de `obj` desde arriba, bajado recto hasta `base_z`.

    Devuelve una bmesh cerrada en espacio mundo, o None si la proyección no
    tocó la pieza en ningún lado.
    """
    cx, cy, lado, top = _encuadre(obj)
    # la grilla arranca bien por encima de la pieza: si un vértice naciera
    # adentro, el rayo saldría por la cara de abajo y la altura sería la
    # equivocada
    altura = top + lado

    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=res, y_subdivisions=res, size=lado,
        location=(cx, cy, altura),
    )
    grilla = context.active_object
    mod = grilla.modifiers.new("SiroProyeccion", 'SHRINKWRAP')
    mod.wrap_method = 'PROJECT'
    mod.use_project_z = True
    mod.use_negative_direction = True   # hacia abajo
    mod.use_positive_direction = False
    mod.target = obj
    context.view_layer.objects.active = grilla
    bpy.ops.object.modifier_apply(modifier=mod.name)

    bm = bmesh.new()
    bm.from_mesh(grilla.data)
    bm.transform(grilla.matrix_world)
    bpy.data.objects.remove(grilla, do_unlink=True)

    # los que no tocaron nada se quedaron a la altura de la grilla: son los que
    # recortan la silueta
    fallaron = {v for v in bm.verts if v.co.z > altura - 1e-4}
    fuera = [f for f in bm.faces if any(v in fallaron for v in f.verts)]
    if fuera:
        bmesh.ops.delete(bm, geom=fuera, context='FACES')
    if not bm.faces:
        bm.free()
        return None

    # el plano sigue mandando cuánto participa: lo que asoma por encima se recorta
    for v in bm.verts:
        if v.co.z > plane_z:
            v.co.z = plane_z

    ext = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:] + bm.edges[:])
    for v in (g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)):
        v.co.z = base_z
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _unir(context, obj, sombra_bm):
    """Une la sombra a la pieza y borra la temporal.

    Solver `MANIFOLD`: la sombra es de un solo valor por columna y la pieza está
    cerrada (lo exige el operador), así que las dos son mallas válidas para el
    solver rápido. Medido, da el mismo volumen que el exacto y baja el caso
    pesado de 25 s a 2,2 s.
    """
    me = bpy.data.meshes.new(SOMBRA_NAME)
    sombra_bm.to_mesh(me)
    sombra_bm.free()
    sombra = bpy.data.objects.new(SOMBRA_NAME, me)
    context.collection.objects.link(sombra)
    try:
        _apply_bool(context, obj, sombra, 'UNION', 'MANIFOLD')
    finally:
        bpy.data.objects.remove(sombra, do_unlink=True)
        if not me.users:
            bpy.data.meshes.remove(me)


def extrude_down(context, obj, plane_z, base_z=0.0, res=256):
    """Rellena `obj` hacia abajo: lo que se ve desde arriba, recortado a
    `plane_z`, se baja hasta `base_z` y se une a la pieza, sin cortarle ni
    borrarle nada. Devuelve False si el plano no sirve o si no tocó la pieza.
    """
    if base_z >= plane_z:
        return False
    lo, _hi = z_range(obj)
    if plane_z <= lo:
        return False

    sombra = _sombra(context, obj, plane_z, base_z, res)
    if sombra is None:
        return False
    _unir(context, obj, sombra)
    return True


class SIRO_OT_extrude_plane(bpy.types.Operator):
    """Pone el plano de altura sobre la pieza activa; muévelo (G, o escribe la altura) y pulsa Extrudir hacia abajo"""
    bl_idname = "siro.extrude_plane"
    bl_label = "Plano de altura"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.name != cut.CUTTER_NAME

    def execute(self, context):
        target = context.active_object
        # el plano, su material y el fantasma son los mismos del corte: acá solo
        # cambia cómo se coloca y hasta dónde se lo puede mover
        bpy.ops.siro.add_cut_plane()
        cutter = cut.get_cutter(context)
        if cutter is None:
            self.report({'ERROR'}, "No se pudo crear el plano de altura")
            return {'CANCELLED'}

        esquinas = [target.matrix_world @ Vector(c) for c in target.bound_box]
        centro = sum(esquinas, Vector()) / len(esquinas)
        lo, hi = z_range(target)
        cutter.rotation_euler = (0.0, 0.0, 0.0)
        # nace arriba del todo: rellenar la pieza entera es el caso normal
        cutter.location = (centro.x, centro.y, hi)
        # el relleno siempre baja recto: un plano inclinado sería un preview que
        # miente sobre lo que va a pasar
        cutter.lock_rotation = (True, True, True)

        # y no tiene sentido fuera de la pieza. La restricción nativa frena el
        # arrastre con G además de limitar el resultado, así que la altura que
        # lee el operador ya llega acotada.
        lim = cutter.constraints.new('LIMIT_LOCATION')
        lim.use_min_z = lim.use_max_z = True
        lim.min_z, lim.max_z = lo, hi
        lim.use_transform_limit = True
        return {'FINISHED'}


class SIRO_OT_extrude_down(bpy.types.Operator):
    """Rellena hacia abajo: lo que se ve de la pieza desde arriba baja recto hasta el fondo y se une a ella, sin cortarla"""
    bl_idname = "siro.extrude_down"
    bl_label = "Extrudir hacia abajo"
    bl_options = {'REGISTER', 'UNDO'}

    resolucion: bpy.props.EnumProperty(
        name="Detalle",
        description="Con cuánto detalle se muestrea la silueta vista desde arriba",
        items=RESOLUCIONES,
        default='256',
    )

    @classmethod
    def poll(cls, context):
        return cut.get_cutter(context) is not None

    def execute(self, context):
        cutter = cut.get_cutter(context)
        # igual que al cortar: el nombre guardado es una pista, manda quién
        # tiene puesto el preview fantasma (la pieza pudo renombrarse)
        target = context.scene.objects.get(cutter.get("siro_target", ""))
        if target is None:
            target = ghost_preview.ghost_target()
        if target is None or target.type != 'MESH':
            self.report({'ERROR'}, "No encuentro la pieza; vuelve a poner el plano de altura")
            return {'CANCELLED'}

        plane_z = cutter.matrix_world.translation.z
        base_z = context.scene.siro_base_z
        # las comprobaciones van ANTES de tocar nada: si el plano está mal
        # puesto, la pieza no debe quedar con los modificadores ya horneados
        if base_z >= plane_z:
            self.report({'ERROR'}, f"El fondo ({base_z:.2f} mm) tiene que quedar debajo del plano ({plane_z:.2f} mm)")
            return {'CANCELLED'}
        lo, hi = z_range(target)
        if not (lo < plane_z <= hi + 1e-4):
            self.report({'ERROR'}, f"El plano está fuera de la pieza (va de {lo:.2f} a {hi:.2f} mm)")
            return {'CANCELLED'}
        # el solver rápido necesita las dos mallas cerradas, y una malla abierta
        # no tiene "adentro": el resultado no podría ser correcto
        abiertas = _open_edge_count(target)
        if abiertas:
            self.report(
                {'ERROR'},
                f"La pieza tiene {abiertas} aristas abiertas o pellizcadas: rellenar "
                "necesita una malla cerrada. Pasa Reparar malla primero.",
            )
            return {'CANCELLED'}

        cut.remove_preview(context)
        _make_single_user(target)
        _apply_pending_modifiers(context, target)

        try:
            ok = extrude_down(context, target, plane_z, base_z, int(self.resolucion))
        except RuntimeError as err:
            self.report({'ERROR'}, f"No se pudo rellenar: {err}")
            return {'CANCELLED'}
        if not ok:
            self.report({'ERROR'}, "El plano no llegó a cruzar la pieza — no se rellenó nada")
            return {'CANCELLED'}

        bpy.data.objects.remove(cutter, do_unlink=True)
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        context.view_layer.objects.active = target
        self.report({'INFO'}, f"Rellenado desde {plane_z:.2f} mm hasta {base_z:.2f} mm")
        return {'FINISHED'}
