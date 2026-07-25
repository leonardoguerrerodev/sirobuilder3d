import bmesh
import bpy

from .boolean_ops import _make_single_user


def _nonmanifold_edges(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = sum(1 for e in bm.edges if not e.is_manifold)
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

        bpy.ops.object.mode_set(mode='EDIT')
        self._pasada()
        bpy.ops.object.mode_set(mode='OBJECT')
        if _nonmanifold_edges(obj):
            # una segunda pasada: tapar agujeros puede destapar caras interiores
            # que la primera no veía, y viceversa
            bpy.ops.object.mode_set(mode='EDIT')
            self._pasada()
            bpy.ops.object.mode_set(mode='OBJECT')

        agujeros, no_manifold = _mesh_stats(obj)
        estado = "imprimible ✓" if no_manifold == 0 else "aún NO imprimible ✗ — prueba subir la distancia de soldado"
        self.report(
            {'INFO'} if no_manifold == 0 else {'WARNING'},
            f"Agujeros: {agujeros_antes} → {agujeros} · "
            f"aristas no-manifold: {nm_antes} → {no_manifold} — {estado}",
        )
        return {'FINISHED'}
