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

- ✅ `clip_plane` — plano de corte naranja translúcido, posicionarlo con G/R, "Cortar": recalcula normales, corta, conserva el lado de la normal, tapa el corte y sella micro-agujeros.
- ✅ Reparar malla — sueltos + degenerados + soldado + agujeros + normales, reporta aristas no-manifold antes/después.
- ✅ Simplificar — Decimate Collapse con preset 50%, reporta caras antes/después.
- ✅ `depthmap_relief` — "Nuevo relieve desde imagen" arma plano + Texture + Displace; sliders "Suavizado" (Filter Size) y "Resolución"; "Aplicar relieve" lo baja a malla real. **MVP (Fase 1) completo.**
- ⬜ Fase 2: espejo rápido, modo acople, transformar en mm, slider "Profundidad", corte de forma libre.
- ⬜ Al terminar la implementación: pasada de pulido de todas las tools.
