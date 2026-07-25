# SiroBuilder

Addon de Blender (formato Extensions) que envuelve herramientas nativas en un panel de botones grandes, estilo 3D Builder / Nomad Sculpt, para el flujo de joyería (escala mm, fundición en plata).

Plan completo: `!cerebronardo/Obsedium/sin_clasificar_plan_addon_3dbuilder_blender.md`

## Instalar

```bash
cd sirobuilder && zip -r ../sirobuilder.zip . && cd ..
```

Blender → Preferences → Get Extensions → ⌄ → *Install from Disk* → `sirobuilder.zip`.

El panel aparece en el N-panel del viewport, pestaña **SiroBuilder**.

## Tests

```bash
blender -b -P test_clip_plane.py
blender -b -P test_tools.py
```

## Estado

- ✅ `clip_plane` — plano de corte naranja translúcido, posicionarlo con G/R, "Cortar": recalcula normales, corta, tapa y sella. "Conservar": arriba (normal) / abajo / **ambas partes** (divide en dos objetos sellados).
- ✅ Reparar malla — sueltos + degenerados + soldado + **caras interiores** + agujeros + normales, con segunda pasada si sigue no-manifold; reporta `Agujeros: A → B · aristas no-manifold: X → Y — imprimible ✓/✗`.
- ✅ Simplificar — Decimate Collapse con preset 50%, triangulando solo si hay ngons; reporta triángulos antes/después.
- ✅ `depthmap_relief` — plano + Texture + Displace desde imagen; sliders "Suavizado", "Resolución" y "Profundidad (mm)"; "Aplicar relieve" lo baja a malla real **y sólida** (Solidify, "Grosor de base" 1 mm por defecto) para que se pueda fusionar con la pieza.
- ✅ Fase 2: espejo X/Y/Z (refleja la pieza en su lugar, sin duplicarla), Modo Acople (snap cara a cara con alineación de rotación), panel Transformar (posición/rotación/dimensiones en mm), corte de forma libre (Knife Project: dibujar contorno → conservar interior/exterior; sin test headless — requiere viewport).
- ✅ Fase 3: primitivas rápidas (botones a los operadores nativos), alinear a la base (Z mín = 0 en las seleccionadas), overlay de dimensiones en viewport (toggle; sin test headless — requiere viewport). Defaults del relieve calcados de `depth_maps.blend`, incluida la densidad de malla (nivel 9 ≈ 513×513 ≈ el plano de 607×607 del .blend).
- ✅ UX estilo 3D Builder (portado de Siro3D): preview en vivo del slicer (lado conservado sólido, descartado en rejilla wireframe, vía booleano FLOAT no destructivo), corte libre guiado en 2 pasos ("Dibujar contorno" a mano alzada sobre la pieza → "Recortar con contorno"), botón "Cancelar corte", Modo Cámara (arrastre izquierdo orbita, derecho pan, clic sigue seleccionando — keymap toggle), Marcar selección (seleccionado #a84a42, resto gris #a0a6ae, colores de Siro3D).
- ✅ v0.6.0: corte libre real (silueta dibujada → prisma → boolean EXACT: sellado y manifold como el corte con plano, con interior/exterior/**ambas**; ahora con test headless), Agrupar/Desagrupar (custom prop + handler de selección: el grupo se selecciona y transforma como uno, sin fusionar mallas), toolbar reorganizada en secciones retráctiles (sub-paneles nativos: cabecera fija con modos + Agrupar, secciones Añadir/Corte/Malla/Espejo y Acople/Transformar/Relieve).
- ✅ v0.7.0: Fusionar y Restar (booleans de 3D Builder) — las piezas seleccionadas se unen a / se restan de la pieza activa.
- ✅ **v0.8.0 — pasada de pulido de todas las tools** (plan y verificación en `PLAN_FIXES_2026-07-24.md`):
  - **Fusionar/Restar** hornea los modificadores pendientes y desliga las mallas multi-usuario antes de operar, usa el solver `MANIFOLD` cuando todas las piezas están cerradas, y ya no borra piezas cuando el boolean no las usó o cuando alguna malla está abierta (era la causa del "de 3 piezas queda 1").
  - **Relieve** sale sólido al aplicarlo, así se puede fusionar con la pieza.
  - **Simplificar** reduce también las mallas con ngons que dejan los booleans.
  - **Reparar** borra caras interiores e informa agujeros y aristas no-manifold antes/después.
  - **Espejo** refleja la pieza en su lugar en vez de duplicarla.
  - **Ghost preview** del corte: el node group compara en espacio mundo (`Self Object`), así el driver deja de depender del objeto que lo lleva — esa dependencia circular era lo que congelaba el preview al mover o escalar la pieza. Tampoco se rompe al renombrarla.
  - **Añadir** crea piezas de ~30 mm en vez de los 2 mm de Blender, y la UI va con íconos en cada sección, secciones en orden de flujo, altura de botón unificada y avisos en caja.
- 🧪 **v0.9.0 — pestaña `SiroLab` (en prueba, fuera del toolbar principal): corte por forma estilo Nomad Sculpt.** Un solo gesto sobre el viewport con 5 modos — **Lazo, Línea (cuchillo), Rectángulo, Elipse y Polígono** — aplicado como **Recortar (Trim)** o **Partir (Split)**. Reemplaza al corte libre de dos pasos, que fallaba de raíz: tomaba la dirección de vista al *aplicar* y desde la región equivocada, así que cortaba desde arriba sin importar cómo estuvieras mirando (90° de error, medido en el Blender de Leo). El nuevo modal captura la región `WINDOW` y la vista **al dibujar**, y construye el cortador con rayos reales, así que sale correcto tanto en ortográfica (prisma) como en perspectiva (tronco de pirámide). Vive en su propia pestaña a propósito: cuando esté probado se muda a la sección **Corte** del toolbar principal y el panel se borra.
- ⬜ Fase 4 (nice to have): vaciar/cascarón (FDM), texto 3D de un clic.
