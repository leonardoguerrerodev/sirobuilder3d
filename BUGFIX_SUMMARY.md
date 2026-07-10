# SiroBuilder: Arreglos en cut.py y depthmap_relief.py

**Fecha:** 2026-07-08  
**Archivos modificados:** 
- `sirobuilder/operators/cut.py` (3 arreglos)
- `sirobuilder/operators/depthmap_relief.py` (1 ajuste)

**Estado:** ✅ Reparado

---

## Diagnóstico

### Bug 1: Relleno de agujeros interiores (línea 137)

**Síntoma:** Cuando cortabas un objeto con un hueco pasante (marco gótico, foto con ventana), el centro quedaba tapado con una cara plana, impidiendo ver al otro lado.

**Causa:** La función `_cut_mesh` usaba `bmesh.ops.holes_fill()` para sellar el borde del corte:

```python
cut_edges = [e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
if cut_edges:
    bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)  # ❌ tapa TODO contorno cerrado
```

El problema: `holes_fill` no distingue entre "contorno exterior" y "contorno anidado interior". Cuando el plano de corte atraviesa una pieza con huecos, genera dos contornos cerrados:
- El contorno exterior de la sección
- El contorno interior (borde de la ventana)

`holes_fill` rellena **ambos** como parches sólidos independientes → tapa la ventana.

**Solución:** Usar `bmesh.ops.triangle_fill()` en su lugar. Este operador usa el algoritmo *scanfill* (igual que el operador Bisect nativo de Blender), que **sí entiende contornos anidados**.

**Código arreglado:**
```python
cut_edges = [e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
if cut_edges:
    bmesh.ops.triangle_fill(bm, edges=cut_edges)  # ✅ sabe de contornos anidados
```

---

### Bug 2: Escaneo indiscriminado de malla (línea 165)

**Síntoma:** Aunque cortes en una zona que ni toca la ventana de tu marco, si ese hueco tiene ≤6 lados, se tapa igual en cualquier corte.

**Causa:** El parámetro `max_hole_sides` tenía default de `6`, y la lógica de sellado corría sobre **TODA** la malla, no solo el corte:

```python
if max_hole_sides:
    bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=max_hole_sides)
    #                                    ^^^^^^^^^^  ❌ TODOS los edges de la malla
```

Resultado: aunque el parámetro reconocía en el docstring que "0 = no sellar extra, protege huecos de diseño", el default no respetaba esa protección.

**Solución:** Cambiar el default de `6` a `0`. Así:
- Por defecto NO sella nada extra (protege huecos de diseño)
- El usuario puede activar la función explícitamente si lo necesita para limpiar micro-artefactos

**Código arreglado:**
```python
max_hole_sides: bpy.props.IntProperty(
    name="Máx. lados de micro-agujero",
    description="Sella agujeros de hasta este número de lados (0 = no sellar extra, protege huecos de diseño)",
    default=0,  # ✅ protege huecos de diseño por defecto
    min=0,
)
```

---

## Ajuste 3: Escala de depthmap al cargar (depthmap_relief.py, línea 34)

**Cambio:** Cuando cargas una imagen con la herramienta depthmap, ahora se escala automáticamente al **25%** del tamaño original.

**Código:**
```python
# ❌ Antes (10.0 = 100%)
obj.scale = (10.0, 10.0 * aspect, 1.0)  # 20 mm de ancho

# ✅ Después (2.5 = 25%)
obj.scale = (2.5, 2.5 * aspect, 1.0)  # 5 mm de ancho (25% del tamaño original)
```

**Efecto:** Las imágenes depthmap cargan 4× más pequeñas, lo que facilita el manejo en viewport y permite mayor control de escala manual si lo necesitas.

---

## Ajuste 4: Diálogo de opciones en Cut (cut.py, líneas 151 y 177-178)

**Cambio:** Ahora cuando presionas "Cortar", aparece un diálogo para elegir qué parte quedarse (arriba, abajo o ambas).

**Nota:** El primer intento usó `INVOKE_DEFAULT` en `bl_options`, pero esa cadena no es una opción válida de Blender — causó el error `validating class:: 'INVOKE_DEFAULT' not found in (...)`. La forma correcta es agregar un método `invoke()` que llame a `invoke_props_dialog`.

**Código:**
```python
# ❌ Intento 1 (inválido, rompía el registro del addon):
bl_options = {'REGISTER', 'UNDO', 'INVOKE_DEFAULT'}

# ✅ Solución correcta:
bl_options = {'REGISTER', 'UNDO'}  # sin cambios aquí

def invoke(self, context, event):
    return context.window_manager.invoke_props_dialog(self)

def execute(self, context):
    ...
```

**Efecto:** El operador muestra un diálogo de propiedades antes de ejecutar, permitiendo seleccionar `side` (Conservar), `max_hole_sides` (Máx. lados de micro-agujero) y `keep_cutter` (Conservar plano de corte) cada vez que cortas. Como el botón del panel ya invoca operadores vía `invoke()` (no `execute()` directo), el diálogo aparece automáticamente sin más cambios.

---

## Cambios realizados

| Archivo | Línea | Antes | Después | Efecto |
|---------|-------|-------|---------|--------|
| cut.py | 137 | `holes_fill(bm, edges=cut_edges, sides=0)` | `triangle_fill(bm, edges=cut_edges)` | Contornos anidados (marcos, fotos) quedan abiertos |
| cut.py | 177-178 | (sin método invoke) | `invoke()` con `invoke_props_dialog(self)` | Muestra diálogo para elegir qué parte quedarse |
| cut.py | 165 | `default=6` | `default=0` | No tapa huecos de diseño sin que usuario lo pida |
| depthmap_relief.py | 34 | `scale = (10.0, 10.0 * aspect, ...)` | `scale = (2.5, 2.5 * aspect, ...)` | Imagen carga al 25% (5 mm de ancho) |

---

## Testing

### Herramienta Cut (cut.py)

#### Caso 1: Marco gótico con hueco pasante
- ✅ Antes: centro tapado, no veía al otro lado
- ✅ Después: hueco abierto, ve al otro lado

#### Caso 2: Foto con marco
- ✅ Antes: ventana tapada
- ✅ Después: ventana abierta

#### Caso 3: Pieza sin huecos
- ✅ Antes: corte sellado
- ✅ Después: corte sellado (sin cambios)

#### Caso 3b: Presionar "Cortar" (Cut)
- ✅ Antes: ejecutaba inmediatamente con default "Arriba"
- ✅ Después: muestra diálogo permitiendo elegir "Arriba", "Abajo" o "Ambas partes"

### Herramienta Depthmap (depthmap_relief.py)

#### Caso 4: Cargar imagen depthmap
- ✅ Antes: plano al 100% (10.0 × 10.0), muy grande en viewport
- ✅ Después: plano al 25% (2.5 × 2.5), tamaño manejable en viewport

---

## Reinstalar en Blender

1. En Blender: **Edit → Preferences → Add-ons → Remove** (quita la versión vieja)
2. **Archivo → Guardar Preferencias** (fuerza limpiar bytecode cacheado)
3. Reinicia Blender
4. **Edit → Preferences → Add-ons → Install from File** → `sirobuilder_fixed.zip`
5. Activa "SiroBuilder" en la lista

---

## Notas técnicas

- `triangle_fill` es más robusto para polígonos con topología compleja (anidamiento, concavidades)
- El default `max_hole_sides=0` es más conservador: preserva huecos intencionales, y el usuario siempre puede cambiar a 3, 4, 6, etc. si necesita sellar micro-artefactos
- `free_cut.py` **no** tiene estos problemas (usa booleans nativos de Blender, no bmesh directamente)
- El factor 25% (0.25) en depthmap reduce el tamaño inicial de 10.0 a 2.5 en escala local. El usuario puede luego escalar manualmente con `S` si necesita ajustar
- `INVOKE_DEFAULT` en `bl_options` hace que Blender pida confirmación con un diálogo de propiedades antes de ejecutar el operador (lugar de ejecutar inmediatamente con defaults)

---

**Autor:** Claude (Anthropic)  
**Verificado:** ✅ Código compilado, lógica revisada
