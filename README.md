# SiroBuilder

Addon de Blender (formato Extensions) que envuelve herramientas nativas en un panel de botones grandes, estilo 3D Builder / Nomad Sculpt, para el flujo de joyería (escala mm, fundición en plata).

Plan completo: `!cerebronardo/Obsedium/sin_clasificar_plan_addon_3dbuilder_blender.md`

## Instalar

```bash
cd sirobuilder && zip -r ../sirobuilder.zip . && cd ..
```

Blender → Preferences → Get Extensions → ⌄ → *Install from Disk* → `sirobuilder.zip`.

El panel aparece en el N-panel del viewport, pestaña **SiroBuilder**.

## Test

```bash
blender -b -P test_clip_plane.py
```

## Estado

- ✅ `clip_plane` — añadir plano de corte, posicionarlo con G/R, "Cortar": recalcula normales, corta, conserva el lado de la normal, tapa el corte y sella micro-agujeros.
- ⬜ Reparar malla, Simplificar, `depthmap_relief` (resto del MVP, Fase 1).
