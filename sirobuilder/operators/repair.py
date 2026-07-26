import bmesh
import bpy

from .boolean_ops import _make_single_user


def _nonmanifold_edges(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return count


def _pinched_edges(obj):
    """Aristas compartidas por MÁS de dos caras: la superficie se toca consigo
    misma. Es un defecto distinto del agujero y no se arregla soldando — el
    cráneo de Leo tenía exactamente una, y el consejo de subir la distancia de
    soldado no servía para nada."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.free()
    return count


def _mesh_stats(obj):
    """(agujeros, aristas no-manifold). Un agujero = un contorno cerrado de
    aristas de borde, que es lo que un usuario cuenta como "hueco" en la pieza"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    no_manifold = sum(1 for e in bm.edges if not e.is_manifold)

    pendientes = {e for e in bm.edges if e.is_boundary}
    agujeros = 0
    while pendientes:
        agujeros += 1
        frente = [pendientes.pop()]
        while frente:  # camina el contorno por vértices compartidos
            arista = frente.pop()
            for vert in arista.verts:
                for vecina in vert.link_edges:
                    if vecina in pendientes:
                        pendientes.remove(vecina)
                        frente.append(vecina)
    bm.free()
    return agujeros, no_manifold


class SIRO_OT_repair(bpy.types.Operator):
    """Repara la malla: borra geometría suelta, degenerada e interior, suelda vértices, tapa agujeros y corrige normales"""
    bl_idname = "siro.repair"
    bl_label = "Reparar malla"
    bl_options = {'REGISTER', 'UNDO'}

    merge_distance: bpy.props.FloatProperty(
        name="Distancia de soldado",
        description="Vértices más cercanos que esto se fusionan",
        default=0.0001,
        min=0.0,
        precision=5,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def _pasada(self):
        for op in (
            lambda: bpy.ops.mesh.delete_loose(),
            lambda: bpy.ops.mesh.dissolve_degenerate(),
            lambda: bpy.ops.mesh.remove_doubles(threshold=self.merge_distance),
        ):
            bpy.ops.mesh.select_all(action='SELECT')
            op()
        # caras interiores: residuo típico de booleans, dejan la pieza
        # no-manifold aunque por fuera se vea cerrada
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_interior_faces()
        bpy.ops.mesh.delete(type='FACE')
        # Pellizcos: aristas con más de dos caras y vértices en reloj de arena,
        # donde la superficie se toca consigo misma. Se borran los VÉRTICES
        # ofensores y el fill_holes de abajo cierra el hueco chico que dejan.
        #
        # Dos detalles medidos contra el cráneo de Leo, que tenía exactamente
        # una arista de estas: select_non_manifold necesita modo vértice, y
        # devuelve vértices sueltos —2, sin ninguna cara completa— así que un
        # delete(type='FACE') no borra absolutamente nada. Borrar por vértice
        # es además lo más conservador: se llevó 7 caras de 174 138.
        # `use_boundary=False` a propósito: el borde de un agujero legítimo lo
        # tapa fill_holes, borrarlo solo agrandaría el agujero.
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold(
            extend=False, use_wire=True, use_boundary=False,
            use_multi_face=True, use_non_contiguous=True, use_verts=True,
        )
        bpy.ops.mesh.delete(type='VERT')
        for op in (
            lambda: bpy.ops.mesh.fill_holes(sides=0),
            lambda: bpy.ops.mesh.normals_make_consistent(inside=False),
        ):
            bpy.ops.mesh.select_all(action='SELECT')
            op()

    def execute(self, context):
        obj = context.active_object
        _make_single_user(obj)
        agujeros_antes, nm_antes = _mesh_stats(obj)

        # Una malla ya cerrada no tiene nada que reparar, y pasarle igual el
        # soldado y la disolución le hace daño: son operaciones que colapsan
        # geometría, y sobre las caras de área cero que deja el relleno —que
        # están integradas en una superficie cerrada— borran caras y abren el
        # hueco en vez de coser. Medido sobre una esfera rellenada sana: salía
        # con 3064 aristas de borde donde no había ninguna, y tardaba 23,5 s.
        if nm_antes == 0:
            self.report({'INFO'}, f"La malla ya está cerrada ({len(obj.data.polygons)} caras) — imprimible ✓")
            return {'FINISHED'}

        # Red de seguridad: reparar puede intentar lo que quiera, pero no puede
        # devolver la pieza peor de lo que llegó. La copia es gratis (Blender la
        # hace por copy-on-write: 0,000 s medido sobre 373 000 caras).
        respaldo = obj.data.copy()

        # la etapa de pellizcos necesita modo vértice; el modo de selección del
        # usuario se devuelve como estaba
        modo_seleccion = tuple(context.scene.tool_settings.mesh_select_mode)

        bpy.ops.object.mode_set(mode='EDIT')
        self._pasada()
        bpy.ops.object.mode_set(mode='OBJECT')
        if _nonmanifold_edges(obj):
            # una segunda pasada: tapar agujeros puede destapar caras interiores
            # que la primera no veía, y viceversa
            bpy.ops.object.mode_set(mode='EDIT')
            self._pasada()
            bpy.ops.object.mode_set(mode='OBJECT')
        context.scene.tool_settings.mesh_select_mode = modo_seleccion

        agujeros, no_manifold = _mesh_stats(obj)
        if no_manifold > nm_antes:
            peor = obj.data
            obj.data = respaldo
            bpy.data.meshes.remove(peor)
            self.report(
                {'WARNING'},
                f"Reparar habría dejado la pieza peor ({nm_antes} → {no_manifold} aristas "
                "no-manifold): se deshizo el cambio y la pieza quedó como estaba",
            )
            return {'FINISHED'}
        bpy.data.meshes.remove(respaldo)

        if no_manifold == 0:
            estado = "imprimible ✓"
        elif agujeros:
            # el consejo tiene que apuntar al defecto que quedó: soldar cierra
            # costuras separadas, pero no hace nada contra un pellizco
            estado = "aún NO imprimible ✗ — quedan agujeros, prueba subir la distancia de soldado"
        else:
            estado = (
                f"aún NO imprimible ✗ — quedan {_pinched_edges(obj)} aristas pellizcadas "
                "(la superficie se toca consigo misma); soldar no las arregla"
            )
        self.report(
            {'INFO'} if no_manifold == 0 else {'WARNING'},
            f"Agujeros: {agujeros_antes} → {agujeros} · "
            f"aristas no-manifold: {nm_antes} → {no_manifold} — {estado}",
        )
        return {'FINISHED'}
