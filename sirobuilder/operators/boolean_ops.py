import bmesh
import bpy


def _apply_bool(context, obj, cortador, operation, solver):
    """Un boolean aplicado de una: lo usan el corte por forma y el relleno"""
    mod = obj.modifiers.new("SiroBool", 'BOOLEAN')
    mod.object = cortador
    mod.operation = operation
    mod.solver = solver
    context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _make_single_user(obj):
    """Copias enlazadas comparten malla y `modifier_apply` se niega a tocarlas."""
    if obj.data.users > 1:
        obj.data = obj.data.copy()


def _apply_pending_modifiers(context, obj):
    """Hornea el stack en orden antes de operar sobre la malla base.

    Sin esto, un boolean/decimate se aplica al final del stack pero sobre la
    malla base — resultado fuera de orden. El ghost preview se quita en vez de
    hornearse (aplicarlo dejaría el material fantasma pegado a la pieza).
    """
    from . import ghost_preview
    ghost_preview.remove_ghost_preview(obj)
    if not obj.modifiers:
        return
    _make_single_user(obj)
    view_layer = context.view_layer
    previo = view_layer.objects.active
    view_layer.objects.active = obj
    for name in [m.name for m in obj.modifiers]:
        try:
            bpy.ops.object.modifier_apply(modifier=name)
        except RuntimeError:
            # ponytail: un modificador que no se puede aplicar (inválido, sin
            # objeto asignado) tampoco aporta geometría — se descarta
            obj.modifiers.remove(obj.modifiers[name])
    view_layer.objects.active = previo


def _mesh_fingerprint(obj):
    """Huella barata de la malla: si no cambia, el boolean no hizo nada.

    Contar vértices no alcanza — restar media pieza de un cubo deja los mismos
    8 vértices en otras posiciones — por eso va la suma de coordenadas.
    """
    me = obj.data
    co = [0.0] * (len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return len(me.vertices), len(me.polygons), round(sum(co), 5)


def _open_edge_count(obj):
    """Aristas de borde o no-manifold: >0 significa malla abierta (no fusionable limpio)"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return count


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

        _make_single_user(target)
        _apply_pending_modifiers(context, target)
        for tool in tools:
            _make_single_user(tool)
            _apply_pending_modifiers(context, tool)

        abiertas = [o.name for o in (target, *tools) if _open_edge_count(o)]
        # con entradas cerradas, MANIFOLD garantiza salida manifold; con alguna
        # abierta produce un no-op silencioso, así que ahí se respeta lo elegido
        solver = 'MANIFOLD' if self.solver == 'EXACT' and not abiertas else self.solver
        # con mallas abiertas el resultado no es confiable: no se borra nada,
        # que es justo lo que hacía desaparecer piezas sin resultado a cambio
        borrar = self.delete_operands and not abiertas

        context.view_layer.objects.active = target
        hechas, sin_efecto = [], []
        for tool in tools:
            antes = _mesh_fingerprint(target)
            mod = target.modifiers.new("SiroBool", 'BOOLEAN')
            mod.object = tool
            mod.operation = self.operation
            mod.solver = solver
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except RuntimeError:
                target.modifiers.remove(mod)
                sin_efecto.append(tool.name)
                continue
            if _mesh_fingerprint(target) == antes:
                # el boolean no cambió nada: la pieza NO se borra, si no
                # desaparecería sin haber aportado al resultado
                sin_efecto.append(tool.name)
                continue
            hechas.append(tool.name)
            if borrar:
                data = tool.data
                bpy.data.objects.remove(tool, do_unlink=True)
                if not data.users:
                    bpy.data.meshes.remove(data)

        verbo = "fusionadas con" if self.operation == 'UNION' else "restadas de"
        msg = f"{len(hechas)} piezas {verbo} {target.name}"
        nivel = 'INFO'
        if sin_efecto:
            nivel = 'WARNING'
            msg += f" · sin efecto (conservadas): {', '.join(sin_efecto)}"
        if abiertas:
            nivel = 'WARNING'
            msg += (f" · malla abierta: {', '.join(abiertas)} — piezas conservadas,"
                    " pasa Reparar malla (o Aplicar relieve) primero")
        self.report({nivel}, msg)
        return {'FINISHED'}
