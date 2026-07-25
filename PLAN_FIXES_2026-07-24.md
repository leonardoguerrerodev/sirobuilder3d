# SiroBuilder — Reparar Fusionar / Simplificar / Reparar malla + tamaños de Añadir

> Plan de trabajo del 2026-07-24. Diagnóstico verificado empíricamente (Blender 5.1.2 headless). Ejecutar las fases en orden marcando los checks del registro de avances al final.

## Contexto

Leo reporta 7 problemas en SiroBuilder (`~/Documentos/!GitHub/!Obsedium/!SiroBuilder(Blender)/`, Blender 5.1.2):

1. **Fusionar**: resultado con huecos/artefactos, y a veces "de 3 piezas me deja 1 y las demás desaparecen".
2. **Simplificar**: no reduce nada, no hace nada.
3. **Reparar malla**: sigue sin ser imprimible, deja la pieza igual; además quiere **feedback**: cuántos agujeros tiene la malla y cómo queda tras reparar.
4. **Añadir formas**: salen con tamaño default de Blender; quiere **~30 mm** por lado/diámetro (convención del addon: 1 unidad Blender = 1 mm, ver `depthmap_relief.py:45`).
5. **Ghost preview del plano de corte**: a veces "se bugea y no renderiza dónde voy a cortar" (el lado a descartar deja de marcarse).
6. **UI**: se siente desordenada; quiere más símbolos/íconos, aspecto más profesional y organizado.
7. **Espejo X/Y/Z**: hoy duplica la geometría en espejo (modificador Mirror aplicado); Leo quiere que **la pieza misma se refleje**, sin generar geometría extra.

Leo confirma que **fusionar relieves (depthmap) con piezas es parte del flujo**.

## Causas raíz (verificadas empíricamente, headless Blender 5.1.2)

| # | Causa | Evidencia |
|---|-------|-----------|
| C1 | El relieve es una **lámina abierta** (grid + Displace, sin volumen). Union sólido+lámina con EXACT → 840 aristas no-manifold (basura); con MANIFOLD → **no-op silencioso** (la pieza queda igual) | T7, T12 |
| C2 | `boolean_ops.py` **borra los operandos aunque el boolean haya fallado** → "de 3 me deja 1" | lectura L49-53 |
| C3 | Malla multi-usuario (copias enlazadas) → `modifier_apply` lanza error "Modifiers cannot be applied to multi-user data" | T2 |
| C4 | Target con modificador pendiente (p. ej. `SiroRelieve` vivo) → el boolean/decimate se aplica **fuera de orden** sobre la malla base → resultado incorrecto | T3 |
| C5 | Decimate COLLAPSE **sin triangular no colapsa nada** en mallas con ngons (las que dejan los booleans EXACT): 12→12 caras con ratio 0.5 | T5 |
| C6 | Reparar **no borra caras interiores** (residuo típico de booleans) → sigue no-manifold tras reparar | T10 |
| C7 | Primitivas con defaults de Blender (2 BU) en vez de ~30 mm | T6 |
| C8 | Ghost preview: los drivers declaran dependencia solo de LOC/ROT — **escalar la pieza deja el preview congelado** (no se re-evalúa) | G3 |
| C9 | Ghost preview: los drivers guardan los **nombres como texto** en la expresión; si la pieza se renombra (o Blender le agrega `.001`), `_plane_component` no la encuentra y devuelve 0.0 → normal (0,0,0) → **ninguna cara se marca, preview muerto en silencio** | G4 |

Datos extra verificados: el solver MANIFOLD (nuevo en 5.x) da resultados limpios y garantizado-manifold con entradas cerradas (T11); el chequeo de malla abierta con bmesh cuesta 0.18 s en 366k caras (T13); Solidify sobre un grid desplazado lo deja cerrado/manifold (T14).

## Plan de implementación

Todos los archivos bajo `sirobuilder/`.

### 1. `operators/boolean_ops.py` — Fusionar/Restar robusto

Helpers nuevos (aquí mismo; `simplify.py` los importará):

- `_make_single_user(obj)`: si `obj.data.users > 1` → `obj.data = obj.data.copy()` (arregla C3).
- `_apply_pending_modifiers(context, obj)`: quita el ghost preview si lo hay (`ghost_preview.remove_ghost_preview(obj)` — nunca aplicarlo, hornearía el material fantasma) y aplica el resto del stack **en orden** con `modifier_apply` (arregla C4). Requiere poner `obj` como activo temporalmente.
- `_open_edge_count(obj)`: bmesh, cuenta aristas `is_boundary or not is_manifold`.

Nuevo flujo de `execute`:

1. Para target y cada tool: `_make_single_user` + `_apply_pending_modifiers`.
2. Chequear malla abierta en todos los participantes. Si el usuario eligió `EXACT` y **todos están cerrados** → usar internamente `MANIFOLD` (mejor "Exacta" en 5.x: salida garantizada manifold). Si alguno está abierto → mantener el solver elegido y reportar `WARNING` nombrando las piezas abiertas ("malla abierta — pasa Reparar primero o aplica el relieve").
3. Por cada tool: guardar `len(target.data.vertices)` antes de aplicar; si tras aplicar **no cambió**, el boolean no hizo nada → **NO borrar ese tool** y acumular warning (arregla C2 — nunca más piezas desaparecidas sin resultado).
4. Reporte final: piezas fusionadas/restadas OK + cuáles quedaron sin procesar y por qué.

### 2. `operators/depthmap_relief.py` — relieve sólido al aplicar (raíz de C1)

En `SIRO_OT_apply_relief`:

- Propiedad nueva `base_thickness: FloatProperty(name="Grosor de base (mm)", default=1.0, min=0.1)` (ajustable en el panel redo).
- Tras aplicar `SiroRelieve`: añadir modificador `SOLIDIFY` (`thickness=base_thickness`, `offset=-1.0`) y aplicarlo → el relieve queda **cerrado y fusionable** (T14). Mantener el recalc de normales existente.

### 3. `operators/simplify.py` — que reduzca de verdad

- `mod.use_collapse_triangulate = True` (arregla C5: los ngons post-boolean ya no bloquean el colapso).
- Reusar `_make_single_user` + `_apply_pending_modifiers` de boolean_ops (C3/C4: simplificar un relieve con Displace vivo hoy sale mal).
- Si `after >= before` → reporte `WARNING` "no se pudo reducir — prueba Reparar malla primero" en vez del INFO normal.

### 4. `operators/repair.py` — reparación real + feedback

- Helper `_mesh_stats(obj)` → `(agujeros, aristas_no_manifold)`. Agujeros = cantidad de **loops de borde** (caminar aristas `is_boundary` agrupándolas en contornos; walker pequeño local, mismo espíritu que `_walk_cut_loops` de cut.py).
- Pipeline en EDIT (orden estilo 3D-Print Toolbox), y si tras la primera pasada sigue no-manifold, una segunda pasada:
  1. `delete_loose`
  2. `remove_doubles(threshold)`
  3. `dissolve_degenerate`
  4. **nuevo**: `select_all(DESELECT)` → `select_interior_faces` → `delete(type='FACE')` (arregla C6)
  5. `fill_holes(sides=0)`
  6. `normals_make_consistent`
- `_make_single_user` antes de editar (no reparar sin querer todas las copias enlazadas).
- Reporte pedido por Leo: `"Agujeros: A → B · aristas no-manifold: X → Y — imprimible ✓"` (✗ si quedó >0, con sugerencia).

### 5. `ui/panels.py` — Añadir a ~30 mm

En `SIRO_PT_add`, fijar props en los botones (1 BU = 1 mm):

```python
grid.operator("mesh.primitive_cube_add", ...).size = 30.0
grid.operator("mesh.primitive_uv_sphere_add", ...).radius = 15.0
op = grid.operator("mesh.primitive_cylinder_add", ...); op.radius = 15.0; op.depth = 30.0
op = grid.operator("mesh.primitive_cone_add", ...); op.radius1 = 15.0; op.depth = 30.0
op = grid.operator("mesh.primitive_torus_add", ...); op.major_radius = 12.0; op.minor_radius = 4.0  # Ø32
grid.operator("mesh.primitive_plane_add", ...).size = 30.0
```

Nota para Leo: esto asume la convención 1 BU = 1 mm del addon ("Escena en mm"). Ojo con un dato raro del diagnóstico: hoy las primitivas salen de 2 BU = 2 mm bajo esa convención, que sería *chico*, no grande — si tus piezas actuales miden otra cosa en el panel Transformar, hay un problema de escala de las piezas aparte de este fix.

### 6. `operators/mirror.py` — Espejo refleja la pieza, no la duplica

Reemplazar el modificador Mirror por una reflexión in-place de la malla:

- Matriz `T(c) @ Scale(-1, eje) @ T(-c)` sobre `obj.data` en espacio local, con `c` = centro del bounding box local (la pieza se voltea **en su lugar**, sin saltar aunque el origen esté descentrado).
- Tras reflejar, **invertir normales** (una reflexión invierte el winding): bmesh `recalc_face_normals` como en `apply_relief`.
- Actualizar docstring/tooltip: "Refleja la pieza en el eje elegido (la voltea en su lugar)".

### 7. `operators/ghost_preview.py` (+ `cut.py`) — preview que no se muere

- **C8**: en `_add_transform_dep`, añadir `SCALE_X/Y/Z` a los canales de dependencia (hoy solo LOC/ROT) → escalar pieza o plano re-evalúa el preview.
- **C9**: dejar de pasar nombres por texto. `_plane_component(kind, axis)` resuelve los objetos por sí misma:
  - cutter = `bpy.data.objects.get("SiroCutter")` (nombre constante que pone el addon);
  - target = el objeto de la escena que tiene el modificador `SiroGhostPreview` (solo existe uno a la vez: `add_cut_plane` limpia los anteriores). Escaneo trivial, 6 drivers × O(objetos).
  Renombrar la pieza deja de romper el preview.
- Mismo fix de resolución en `SIRO_OT_cut.execute` (`cut.py:267`): hoy resuelve la pieza por `cutter["siro_target"]` (nombre guardado) — si la pieza se renombró tira "No encuentro la pieza a cortar". Fallback: el objeto con el modificador `SiroGhostPreview`.

### 8. `ui/panels.py` — UI ordenada y profesional

- **Íconos en cabeceras de sección** vía `draw_header()` en cada subpanel: Añadir `ADD`, Transformar `OBJECT_ORIGIN`, Corte `MOD_BOOLEAN`, Malla `MESH_DATA`, Espejo y Acople `MOD_MIRROR`, Relieve `MOD_DISPLACE`.
- **Reordenar secciones** por flujo de trabajo: Añadir → Transformar → Corte → Malla → Espejo y Acople → Relieve.
- **Ícono en todo botón** que hoy no tiene: los tres botones Espejo X/Y/Z (`MOD_MIRROR`), Aplicar relieve ya tiene, etc.
- **Unificar tamaños**: todos los botones de acción a `scale_y = 1.5` (hoy mezcla 1.3/1.4/1.6).
- `use_property_split = True` en Transformar (labels alineados, look nativo profesional).
- Hints de estado (los `label(..., icon='INFO')` del corte) dentro de un `box()` para que se lean como avisos y no como texto suelto.
- Sin cambios de comportamiento: solo layout, íconos y orden.

### 9. `test_tools.py` — regresiones (estilo assert existente)

Añadir al final, mismo estilo:

- Fusionar 3 piezas limpias → queda 1 objeto, manifold, dims correctas.
- Fusionar con tool multi-usuario (copy enlazada en escena) → no explota, resultado correcto.
- Fusionar con una pieza de malla abierta → la pieza abierta **sigue existiendo** (no se borró sin resultado).
- Fusionar target con `SiroRelieve` vivo → el relieve queda incluido en el resultado (dims delatan el displace).
- `apply_relief` → malla resultante toda manifold (cerrada) y sin modificadores.
- Simplificar malla con ngons (resultado de un boolean EXACT subdividido) → reduce caras.
- Reparar cubo con cara interior flotante (caso T10) → 0 no-manifold; y el reporte de agujeros funciona (2 agujeros → 0 en un cubo con 2 caras borradas).
- Ghost preview: crear plano sobre esfera → contar caras fantasma en la malla evaluada; **escalar la pieza** cambia el conteo (C8) y **renombrar la pieza** no lo deja en 0 (C9). (Réplica de los checks G1–G4 del diagnóstico.)
- **Reescribir el test de espejo existente** (`test_tools.py:76-87`, hoy asserta que duplica): ahora debe verificar que el conteo de vértices **no cambia**, que la malla quedó reflejada (asimetría marcada en un vértice de referencia) y que el volumen sigue positivo (normales bien tras el flip).

## Verificación

```bash
cd "~/Documentos/!GitHub/!Obsedium/!SiroBuilder(Blender)"
blender -b -P test_tools.py       # debe terminar en "OK tools"
blender -b -P test_clip_plane.py  # no romper el sistema de corte
```

Además, reproducir headless el flujo completo de Leo: crear relieve desde imagen → aplicar (ahora sólido) → fusionar con un cubo → verificar manifold y que el relieve esté en el resultado.

Commit en el repo SiroBuilder (working tree está limpio salvo `.directory` untracked — no mezclarlo).

## Paso a paso con checks — registro de avances

**Instrucciones para el ejecutor:** trabajar las fases EN ORDEN. Al terminar cada ítem, marcar su `[ ]` → `[x]` editando ESTE archivo. Si un check falla, detenerse, anotar el fallo en la línea `Notas:` de la fase y reportar — no replanificar ni saltar a la fase siguiente. La suite completa debe pasar al cierre de cada fase (los tests solo crecen, nunca se debilitan).

Comando de suite (desde la raíz del repo SiroBuilder):
`blender -b -P test_tools.py` → debe terminar imprimiendo `OK tools`.

### Fase 0 — Línea base
- [x] `git status` limpio (salvo `.directory` untracked, que NO se toca ni commitea)
- [x] Suite actual pasa: `blender -b -P test_tools.py` → `OK tools`
- [x] `blender -b -P test_clip_plane.py` corre sin asserts fallidos
- Notas: rama `master`, sin remote configurado. Untracked: `.directory` + este mismo plan (`PLAN_FIXES_2026-07-24.md`, sí se commitea al cierre).

### Fase 1 — Fusionar/Restar robusto (`operators/boolean_ops.py`, plan §1)
- [x] Helpers `_make_single_user`, `_apply_pending_modifiers`, `_open_edge_count` implementados
- [x] Nuevo flujo de `execute`: single-user + aplicar modificadores pendientes + MANIFOLD si todo cerrado + no borrar tools cuyo boolean no cambió nada + reporte con detalle
- [x] Tests nuevos en `test_tools.py`: fusionar 3 piezas → 1 objeto manifold · tool multi-usuario no explota · pieza abierta sobrevive con warning · target con `SiroRelieve` vivo incluye el relieve
- [x] Suite completa pasa
- Notas: dos desvíos del plan, ambos por evidencia de los tests. (1) El detector de "boolean sin efecto" no puede ser el conteo de vértices: restar media pieza de un cubo deja los mismos 8 vértices y marcaba falso no-op (rompía el test de Restar existente). Se usa `_mesh_fingerprint` = (verts, caras, suma de coordenadas). (2) Si *alguna* pieza está abierta no se borra **ninguna** (no solo la que no cambió): con EXACT una lámina abierta sí altera la malla, así que el fingerprint no la protegía — que es exactamente el caso del relieve que hacía desaparecer piezas.

### Fase 2 — Relieve sólido (`operators/depthmap_relief.py`, plan §2)
- [x] `base_thickness` (default 1.0 mm) + Solidify aplicado en `apply_relief`
- [x] Test nuevo: tras `apply_relief`, malla toda manifold (cerrada) y sin modificadores
- [x] Suite completa pasa
- Notas: Solidify con `offset = -1.0` (crece hacia abajo, la cara con relieve no se mueve). Relieve aplicado: 0 aristas no-manifold sobre la malla de 607×607.

### Fase 3 — Simplificar que reduce (`operators/simplify.py`, plan §3)
- [x] `use_collapse_triangulate` + reuso de helpers de Fase 1 + WARNING si no redujo
- [x] Test nuevo: malla con ngons (post-boolean EXACT subdividido) reduce caras
- [x] Suite completa pasa
- Notas: dos desvíos del plan. (1) `use_collapse_triangulate` queda **condicional** (`any(len(p.vertices) > 4 ...)`): en malla de quads destruiría topología limpia sin ganar nada, y ahí Collapse ya funciona bien. (2) La métrica pasa de caras a **triángulos** (`_tri_count`): Decimate opera sobre triángulos, y con triangulado 150 quads = 300 tris → ratio 0.5 = 150 tris, o sea "150 caras → 150 caras", que fue exactamente el falso "no redujo nada" que rompió el test existente. Resultado: quads 300→150 tris, ngons 348→174 tris.

### Fase 4 — Reparar real + feedback (`operators/repair.py`, plan §4)
- [x] `_mesh_stats` (agujeros = loops de borde, aristas no-manifold) + paso de caras interiores + segunda pasada si sigue no-manifold + `_make_single_user`
- [x] Reporte "Agujeros: A → B · aristas no-manifold: X → Y — imprimible ✓/✗"
- [x] Tests: cubo con pared interior → 0 no-manifold · cubo con 2 caras borradas → stats reportan 2 agujeros → 0
- [x] Suite completa pasa
- Notas: el caso de "cara interior flotante" se implementó como **pared interior** (dos cubos pegados unidos con `join` + `remove_doubles`), que es el residuo real de un boolean y sí lo detecta `select_interior_faces` — una cara suelta flotando tiene aristas de 1 sola cara, no la ve como interior. Resultado: 4 aristas no-manifold → 0, ancho intacto. El test de agujeros usa tapa y base (`abs(normal.z) > 0.9`): las dos primeras caras del cubo son adyacentes y su borde forma **un solo** contorno, no dos.

### Fase 5 — Espejo in-place (`operators/mirror.py`, plan §6)
- [x] Reflexión `T(c) @ Scale(-1, eje) @ T(-c)` sobre la malla + normales corregidas; sin objeto nuevo
- [x] Test de espejo REESCRITO: mismos vértices, malla reflejada, volumen positivo
- [x] Suite completa pasa
- Notas: para corregir el winding se usa `bmesh.ops.reverse_faces` en vez de `recalc_face_normals`: recalc solo acomoda normales hacia afuera, no revierte el orden de vértices que la reflexión invierte. El test verifica volumen con signo (`bm.calc_volume(signed=True) > 0`), que es lo que delata una pieza dada vuelta.

### Fase 6 — Ghost preview inmortal (`operators/ghost_preview.py` + `cut.py`, plan §7)
- [x] Canales `SCALE_X/Y/Z` en `_add_transform_dep`
- [x] `_plane_component` resuelve cutter por nombre constante y target por modificador `SiroGhostPreview` (sin nombres en la expresión)
- [x] `SIRO_OT_cut.execute` con fallback de target por modificador
- [x] Tests: escalar la pieza cambia el conteo de caras fantasma (evaluadas) · renombrar la pieza no lo deja en 0 · `siro.cut` corta la pieza renombrada
- [x] Suite completa pasa · `test_clip_plane.py` sigue pasando
- Notas: **la causa C8 estaba mal diagnosticada y agregar los canales SCALE no alcanzó.** Verificado headless: con los 9 canales puestos, mover/escalar la pieza seguía sin actualizar el preview (llegaba con un paso de retraso o nunca). El problema real es que el driver vive en un modificador **de la pieza** y dependía de la transform **de esa misma pieza**: el depsgraph no puede ordenar un objeto contra sí mismo y descarta la relación. Solución: el node group pasa a comparar en **espacio mundo** (`Self Object` → `Object Info` → `Transform Point`), así la transform de la pieza la resuelve el depsgraph y el driver depende solo del plano. `_plane_component` devuelve co/normal en mundo y `_make_driver` ya no registra dependencia del target. `_build_node_group` detecta el grupo viejo (sin nodo `Self Object`) y lo reconstruye, para archivos guardados con la versión anterior. Comprobación: plano centrado → 256/512 caras fantasma exactas; reacciona a mover, escalar y rotar la pieza; el renombre no lo afecta.

### Fase 7 — Añadir a 30 mm + UI (`ui/panels.py`, plan §5 y §8)
- [x] Tamaños ~30 mm en los 6 botones de Añadir (valores del plan §5)
- [x] UI: íconos en cabeceras (`draw_header`), reorden Añadir→Transformar→Corte→Malla→Espejo/Acople→Relieve, ícono en todo botón, `scale_y = 1.5` unificado, `use_property_split` en Transformar, hints en `box()`
- [x] Check headless: registro de todas las clases + tamaños reales + íconos válidos
- [x] Suite completa pasa
- Notas: las primitivas pasaron a una tabla `PRIMITIVAS` en `panels.py` en vez de props sueltas en `draw()`, para que el test pueda ejecutar exactamente los mismos valores que usan los botones y medir la pieza resultante (todas entre 28 y 33 mm; el toro Ø32). El reorden de secciones va en `__init__.py`: Blender dibuja los subpaneles en orden de registro, no de definición. Verificado aparte que los 26 íconos usados en `panels.py` existen en el enum de Blender 5.1.2.

### Fase 8 — Cierre
- [x] Flujo completo headless: relieve desde imagen → aplicar → fusionar con cubo → resultado manifold y con el relieve incluido
- [x] `blender -b -P test_tools.py` → `OK tools` · `blender -b -P test_clip_plane.py` OK
- [x] Revisión final del diff completo contra este plan (nada fuera de alcance)
- [x] Commit en el repo SiroBuilder con mensaje descriptivo (sin `.directory`); NO pushear sin que Leo lo pida
- Notas: flujo verificado (relieve 20×20×7 mm cerrado → fusión con cubo de 30 mm → 0 aristas no-manifold, 143.511 verts, relieve consumido). Diff acotado a los 9 archivos del plan + `test_tools.py`. **Pendiente para Leo:** el addon instalado en `~/.config/blender/5.1/extensions/user_default/sirobuilder/` es una copia aparte y quedó desactualizada — hay que reinstalarlo (o hacerlo symlink al repo) para que los arreglos lleguen a su Blender.
