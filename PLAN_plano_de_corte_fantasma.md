# SiroBuilder — Plan: plano de corte con fantasma "estilo 3D Builder"

Estado: **solo planificación, no se ha tocado código.** Basado en la bitácora (v0.25.1), el README de retoma y el análisis del `.exe`, más una lectura de `ghost_preview.py` y `cut.py` del addon.

## 1. Objetivo

Al poner el plano de corte verde, la pieza se ve sombreada y se **ve dónde va a dividir**: un lado se queda sólido y el otro aparece como fantasma. Hoy el fantasma **no se ve** en tu Blender 5.2.

Lo que NO nos da el análisis del `.exe`: ese documento solo identifica el binario, explica que no se puede portar (UWP/DirectX) y lista las herramientas. **No dice nada de cómo 3D Builder dibuja el plano ni el fantasma.** El preview se diseña mirando tus capturas, no copiando su técnica.

## 2. Cómo se genera hoy el fantasma (lo que preguntabas)

1. `add_cut_plane` crea el objeto `SiroCutter` (plano verde translúcido) y le pone a la pieza un **modificador de Geometry Nodes** (`SiroGhostPreview`).
2. El modificador toma la posición de **cada cara** (centro), la pasa a espacio mundo y calcula `dot(pos − Plane Co, Plane No) < 0`. Las caras que dan verdadero reciben el **slot de material "fantasma"** (blanco, alfa 0,12). Las demás conservan su material.
3. `Plane Co` y `Plane No` (punto y normal del plano) llegan al modificador mediante **drivers** que llaman a una función Python (`_plane_component`) inyectada en `bpy.app.driver_namespace`. Un handler `load_post` la repone al abrir archivos.
4. El objeto lleva `show_transparent = True` para que el modo Solid respete el alfa.

Limitaciones de este método, aunque funcione perfecto:
- Se pinta **por cara entera**: la frontera entre sólido y fantasma es escalonada (sigue la malla), no una línea limpia.
- **No hay tapa** (sección rellena) ni **línea de contorno**.
- Depende de drivers Python → ver hipótesis 1.

## 3. Por qué no lo ves — hipótesis (sin verificar)

Ordenadas por probabilidad. Cada una se descarta con una comprobación de ~10 segundos.

| # | Hipótesis | Cómo comprobarla |
|---|---|---|
| 1 | **Drivers sin ejecutar.** Los drivers llaman a una función Python propia, no a una expresión simple. Con *Auto Run Python Scripts* desactivado (default de Blender, y las preferencias de 5.2 son nuevas si migraste el 2-oct), Blender los salta. Los inputs del modificador quedan en `(0,0,0)` / `(0,0,1)` y el fantasma cae en `z<0` del mundo, fuera de tu pieza. | Preferences → Save & Load → *Auto Run Python Scripts*. O mira si sale "Auto-run disabled" en la barra superior. O abre el Drivers editor sobre la pieza y busca drivers en rojo / inválidos. |
| 2 | **Drivers inválidos por la ruta nueva de 5.2** (`modifiers[…].properties.inputs.Socket_N.value`). El fix de v0.25.1 pasó los tests *headless*, pero no se ha visto dibujar en un viewport real. | Misma comprobación del Drivers editor. Además, en el panel del modificador revisa si Plane Co / Plane No se mueven al mover el plano. |
| 3 | **Solid con Color ≠ Material.** Si Viewport Shading → Color está en Object / Single / Random / Texture, Blender ignora el alfa y el color del material: los dos lados se ven iguales. | Viewport Shading → Color: Material. |
| 4 | **El fantasma es casi invisible por diseño**: blanco al 12 % sobre fondo claro. | Probar con tema/fondo oscuro; subir alfa a mano en el material `SiroGhostFantasma`. |
| 5 | **El plano nace en el origen de la pieza con normal Z**: el lado fantasma es el `−Z` del plano. Si el plano está justo en el borde de la pieza, todo o nada es fantasma. | Mover el plano a media altura de la pieza y rotarlo. |

Si es la 1 o la 2, el arreglo estructural es el de la Fase 1 (quitar los drivers), no parchar.

## 4. Tres maneras de generar el fantasma

| | A. Material por cara (actual) | B. Shader por píxel | C. Geometría real |
|---|---|---|---|
| Idea | GN asigna slot fantasma a las caras del lado descartado | Un material con `Texture Coordinate → Object` apuntando al `SiroCutter`: `z<0` en espacio del plano → alfa baja | GN con *Mesh Boolean* contra un semiespacio: separa sólido y fantasma de verdad |
| Frontera | Escalonada (por cara) | **Línea limpia por píxel** | Exacta |
| Tapa de sección | No | No (haría falta truco extra) | Sí, sale sola |
| Funciona en Solid | Sí | **No** (Solid no evalúa shaders; solo Material Preview / EEVEE) | Sí |
| Drivers / Python | Sí (hoy) o no (con Object Info, ver Fase 1) | No | No |
| Costo en mallas pesadas | Bajo | Bajo | **Alto** (booleano en cada movimiento; tu pieza de 250k caras no daría) |

Lo que no sé: cuál usa 3D Builder. La frontera limpia y la tapa que se ven en sus capturas sugieren B o C, pero es una inferencia, no un dato.

## 5. Plan por fases

Cada fase termina con una prueba antes de pasar a la siguiente. Regla heredada de la bitácora: **medir antes de tocar, y romper el test a propósito para comprobar que falla.**

### Fase 0 — Diagnóstico (sin tocar el addon)
- Tú: las comprobaciones de la sección 3 (sobre todo 1, 2 y 3) y una captura de cómo ves el plano hoy y otra de 3D Builder cortando.
- Yo: reproducir en Blender 5.2.2 headless: crear plano, mover, evaluar y contar caras con slot fantasma, **con y sin** auto-ejecución de scripts. Esto confirma o descarta las hipótesis 1 y 2.
- Necesito el repo actual y los tests (`test_clip_plane.py`, `test_tools.py`, no venían en el zip) y `git status && git diff && git stash list` antes de cualquier cambio.

### Fase 1 — Que el fantasma aparezca siempre (sin drivers)
- El node group recibe el **objeto `SiroCutter` como input** y lee su transform con `Object Info`; calcula punto y normal del plano dentro del propio nodo.
- Se eliminan los drivers, `driver_namespace`, el handler `load_post` y la dependencia de *Auto Run Python Scripts*. Sin Python en el camino, tampoco hay ciclo de dependencias de la §9 de la bitácora (el cutter no depende de la pieza).
- Hay que validar en headless que el depsgraph reevalúa el modificador al mover el plano.
- Visibilidad: color/alfa del fantasma más legible, opción de tinte, wireframe u ocultar el lado descartado, y una **flecha de normal** que indique el lado que se conserva.
- Pruebas: caras fantasma > 0 tras mover el plano, con auto-ejecución desactivada; el test debe fallar si se repone la versión con drivers.

### Fase 2 — Línea de contorno de la sección
- Overlay GPU (ya existe infraestructura en `overlay.py`) que dibuja donde el plano toca la malla.
- Cálculo con numpy (intersección arista-plano); recalcular solo cuando el plano se mueve. Medir contra tu pieza de 250k caras antes de comprometerse.

### Fase 3 — Tapa de la sección (translúcida)
- Triangular el contorno de la Fase 2. Casos con huecos o varios lazos (toro, anillo) pedirán más trabajo; los lazos ya se saben recorrer (`_walk_cut_loops` en `cut.py`).

### Fase 4 — Sombreado "shade" (opcional, preguntar)
- Variante B en Material Preview para frontera por píxel.
- Poner el viewport en Solid / Color: Material mientras la herramienta está activa y **restaurar al salir** (patrón del Modo Acople). La config de shading vive por screen dentro del `.blend`, hay que recorrer `bpy.data.screens`.

### Fase 5 — Backlog (después del corte)
Orden propuesto, de los documentos:
1. **Verificación de fundibilidad** (0,8 / 1,0 / 8 mm). Reusa el overlay de la Fase 2.
2. **Vaciado interior (hollow)**, con el peso en gramos bajando en vivo. Cuidado con `dissolve_degenerate` / `remove_doubles` sobre mallas sanas (§16).
3. **Grabado de texto** en la cara del sello (reusa la proyección de "extrudir hacia abajo").
4. Baratas: separar partes sueltas, suavizar, duplicar, tubo por curva.
5. Para después: relleno curvo del corte.

Descartado: portar el `.exe`, lib3mf (solo si algún día exportas 3MF), color/pintura, biblioteca de piezas, pinceles alpha.

## 6. Riesgos

- **El ghost de la v0.25.1 no se ha visto en un viewport 5.2.** Los tests son headless; en `blender -b` no se dibuja nada.
- **Rendimiento**: contorno y tapa sobre 250k caras pueden arrastrar el viewport; hay que medir y, si hace falta, limitar por tamaño.
- **Solid vs. Material Preview**: la variante por píxel no existe en Solid.
- **Repo sin remoto**: cualquier cambio parte con stash/diff y un respaldo fechado (lección del §30).

## 7. Decisiones abiertas

1. ¿Parto por la Fase 0 (diagnóstico) apenas me pases el repo?
2. ¿Aceptas que la Fase 1 elimine los drivers, o prefieres confirmar primero que ese es el problema?
3. Para el fantasma, ¿qué prefieres en el lado descartado: blanco translúcido, wireframe o tinte de color?
4. ¿Quieres que el addon cambie el shading del viewport (Fase 4) o lo dejamos a tu elección?
5. ¿Contorno + tapa en la misma entrega, o contorno primero?
