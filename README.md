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
- ✅ Reparar malla — sueltos + degenerados + soldado + agujeros + normales, reporta aristas no-manifold antes/después.
- ✅ Simplificar — Decimate Collapse con preset 50%, reporta caras antes/después.
- ✅ `depthmap_relief` — plano + Texture + Displace desde imagen; sliders "Suavizado", "Resolución" y "Profundidad (mm)"; "Aplicar relieve" lo baja a malla real.
- ✅ Fase 2: espejo X/Y/Z (Mirror aplicado en un paso), Modo Acople (snap cara a cara con alineación de rotación), panel Transformar (posición/rotación/dimensiones en mm), corte de forma libre (Knife Project: dibujar contorno → conservar interior/exterior; sin test headless — requiere viewport).
- ⬜ Fase 3: primitivas rápidas, alinear a la base, overlay de dimensiones.
- ⬜ Al terminar la implementación: pasada de pulido de todas las tools.
