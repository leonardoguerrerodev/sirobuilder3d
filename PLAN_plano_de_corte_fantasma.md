# SiroBuilder — Plan: plano de corte con fantasma "estilo 3D Builder"

Estado al 2026-10-12: **Fase 0 y Fase 1 hechas y probadas en headless (Blender 5.2.0 LTS). El problema original —no ver el fantasma en tu viewport— sigue sin resolver ni explicar.** Siguiente paso: medir en tu sesión real con `diagnostico_viewport.py`.

Basado en la bitácora (v0.25.1), el README de retoma, el análisis del `.exe` y la lectura de `ghost_preview.py` y `cut.py`. Código en `main`: v0.26.0 (commit `2469e25`, sobre `702c029`).

## 1. Objetivo

Al poner el plano de corte verde, la pieza se ve sombreada y se **ve dónde va a dividir**: un lado se queda sólido y el otro aparece como fantasma. Hoy el fantasma **no se ve** en tu Blender 5.2.

Lo que NO nos da el análisis del `.exe`: ese documento solo identifica el binario, explica que no se puede portar (UWP/DirectX) y lista las herramientas. **No dice nada de cómo 3D Builder dibuja el plano ni el fantasma.** El preview se diseña mirando tus capturas, no copiando su técnica.

## 2. Cómo se genera el fantasma

**Hasta la v0.25.1 (con drivers):**
1. `add_cut_plane` crea el objeto `SiroCutter` (plano verde translúcido) y le pone a la pieza un modificador de Geometry Nodes (`SiroGhostPreview`).
2. El modificador toma el centro de cada cara, lo pasa a espacio mundo y calcula `dot(pos − Plane Co, Plane No) < 0`. Las caras que dan verdadero reciben el slot de material "fantasma" (blanco, alfa 0,12).
3. `Plane Co` y `Plane No` llegaban por 6 drivers que llamaban a una función Python (`_plane_component`) en `bpy.app.driver_namespace`, repuesta por un handler `load_post`.

**Desde la v0.26.0 (sin drivers):**
- `SiroCutter` entra al modificador como input de tipo **Objeto**; el node group lee su transform con *Object Info* y calcula punto y normal en espacio mundo (`co = M·(0,0,0)`, `no = normalizar(M·(0,0,1) − M·(0,0,0))`, igual que `siro.cut`).
- Eliminados: los 6 drivers, la función en `driver_namespace` y el handler `load_post`. Los drivers de archivos viejos se borran por ruta al añadir un plano nuevo.
- El plano lleva una **flecha de normal** (un cono hacia +Z, 22 vértices en total) que marca el lado que se conserva.
- Alfa del fantasma 0,25 en materiales **nuevos** (si el archivo ya tiene `SiroGhostFantasma`, conserva su valor).
- El objeto lleva `show_transparent = True` para que el modo Solid respete el alfa.

Limitaciones que siguen vigentes, aunque funcione perfecto:
- Se pinta **por cara entera**: la frontera entre sólido y fantasma es escalonada (sigue la malla), no una línea limpia.
- **No hay tapa** (sección rellena) ni **línea de contorno**.
- Si alguien borra `SiroCutter` a mano, el modificador queda con el input vacío (Object Info devuelve la identidad: plano en el origen del mundo). No está protegido.

## 3. Por qué no lo ves — hipótesis y qué se midió

| # | Hipótesis | Estado | Evidencia |
|---|---|---|---|
| 1 | Drivers sin ejecutar con *Auto Run Python Scripts* desactivado | **DESCARTADA** | Código viejo (`702c029`) con `--factory-startup --disable-autoexec`: el fantasma coincide con el oráculo en todos los casos, incluso tras guardar y reabrir. Una explicación probable —no verificada aquí— es que Blender permite los drivers que solo llaman a funciones registradas en `driver_namespace`. |
| 2 | Drivers inválidos por la ruta nueva de 5.2 | **DESCARTADA** | Con auto-ejecución ON: 6/6 drivers válidos, inputs que siguen al plano, mismo resultado tras reabrir. |
| 3 | Solid con Color ≠ Material | **Pendiente** | Headless no dibuja. Lo mide `diagnostico_viewport.py` (sección F). |
| 4 | Fantasma casi invisible por diseño (blanco al 12 % sobre fondo claro) | **Pendiente** | Lo mide `diagnostico_viewport.py` (secciones D y F). |
| 5 | El plano nace en el **origen** de la pieza, no en su centro | **La más fuerte ahora** | `cut.py` crea el plano en `target.matrix_world.translation`. Si el origen de tu pieza está en la base o fuera del centro, el plano nace en el borde y todo queda de un solo lado (0 % o 100 % fantasma). No se ha medido en tu pieza real. |

Nunca hemos visto el fantasma en tu viewport con tu pieza real. Los tests headless usan una esfera de 4608 caras centrada en el origen, donde la hipótesis 5 no puede aparecer.

## 4. Tres maneras de generar el fantasma

| | A. Material por cara (actual) | B. Shader por píxel | C. Geometría real |
|---|---|---|---|
| Idea | GN asigna slot fantasma a las caras del lado descartado | Un material con `Texture Coordinate → Object` apuntando al `SiroCutter`: `z<0` en espacio del plano → alfa baja | GN con *Mesh Boolean* contra un semiespacio: separa sólido y fantasma de verdad |
| Frontera | Escalonada (por cara) | **Línea limpia por píxel** | Exacta |
| Tapa de sección | No | No (haría falta truco extra) | Sí, sale sola |
| Funciona en Solid | Sí | **No** (Solid no evalúa shaders; solo Material Preview / EEVEE) | Sí |
| Drivers / Python | No (desde v0.26.0) | No | No |
| Costo en mallas pesadas | Bajo | Bajo | **Alto** (booleano en cada movimiento; tu pieza de 250k caras no daría) |

Lo que no sé: cuál usa 3D Builder. La frontera limpia y la tapa que se ven en sus capturas sugieren B o C, pero es una inferencia, no un dato.

## 5. Plan por fases

Cada fase termina con una prueba antes de pasar a la siguiente. Regla heredada de la bitácora: **medir antes de tocar, y romper el test a propósito para comprobar que falla.**

### Fase 0 — Diagnóstico (sin tocar el addon) — HECHA
- Corrido en Blender 5.2.0 LTS, auto-ejecución ON y OFF. Resultado: hipótesis 1 y 2 descartadas (ver §3).
- Ojo con una confusión de archivos: tu `diagnostico_fantasma.py` del repo es una copia exacta de `test_ghost_fase1.py` (179 líneas, idénticos). El diagnóstico original solo se corrió con auto-ejecución ON.

### Fase 1 — Que el fantasma no dependa de Python — HECHA (v0.26.0), probada solo en headless
- Implementada como se describe en §2. Commit `2469e25`.
- Prueba: `tests/test_ghost_fase1.py` (`blender -b --factory-startup --disable-autoexec --python tests/test_ghost_fase1.py`).
  - Contra el código nuevo: `TODO OK` — 0 drivers, flecha de 22 vértices, fantasma = oráculo en Python puro (plano en el origen, z=±0,5, girado 90°, normal invertida, pieza desplazada, tras guardar y reabrir), controles de 0 % y 100 %, limpieza sin residuos.
  - Contra el código viejo: **falla** en "6 drivers" y "flecha", como debe. El test prueba algo.
- El oráculo compara **por cara, no por área**: en una esfera UV, z=±0,5 da 67 % / 33 %, no 75 % / 25 %.
- **Lo que esta fase NO resolvió:** el problema de no ver el fantasma. Es una mejora de robustez (quita la dependencia de Python, agrega la flecha), no la causa.
- Pendiente: commitear la corrección del caso 0 contra 0 en `tests/test_ghost_fase1.py` (cambio local; con el test sin corregir aparece una falla falsa a "pieza desplazada +1 en Z").
- No visto todavía en un viewport 5.2 real.

### Fase 1b — Medir en la sesión real (EN CURSO)
- Tú: abre tu `.blend` con la pieza real, pulsa "Añadir plano de corte" sin mover nada, y corre `diagnostico_viewport.py` desde el Text Editor (Alt+P). Resultado en `~/diag_viewport.txt`. Opcional: una captura del viewport, y repetirlo con el plano movido al medio de la pieza.
- Mide: si el plano atraviesa la caja de la pieza (y a qué fracción), caras fantasma en la pieza real y tiempo de reevaluación, pila de modificadores y slots, shading de cada viewport (Solid/Material Preview, Color, X-Ray), alfa del material y fondo del tema. Solo lee: no cambia la escena. Probado únicamente contra un `bpy` simulado.
- Según el resultado:
  - **Plano en el borde (hip. 5):** el plano nace en el centro de la caja de la pieza, no en su origen. Cambio chico en `add_cut_plane`; se prueba con el mismo oráculo, con una pieza de origen descentrado.
  - **Shading o alfa (hip. 3 y 4):** ajustar el material y avisar en el panel.
  - **Todo bien y aun así no se ve:** captura del viewport y buscar algo propio del dibujo.
- Visibilidad, para decidir después: tinte, wireframe u ocultar el lado descartado. Hoy es blanco translúcido.

### Fase 2 — Línea de contorno de la sección
- Overlay GPU (ya existe infraestructura en `overlay.py`) que dibuja donde el plano toca la malla.
- Cálculo con numpy (intersección arista-plano); recalcular solo cuando el plano se mueve. Medir contra tu pieza de 250k caras antes de comprometerse. `diagnostico_viewport.py` ya reporta cuánto tarda la reevaluación del modificador sobre tu pieza.

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

- **El fantasma nunca se ha visto en tu viewport 5.2 con tu pieza real.** Los tests son headless; en `blender -b` no se dibuja nada, y la esfera de prueba no reproduce una pieza con el origen descentrado.
- **Rendimiento**: contorno y tapa sobre 250k caras pueden arrastrar el viewport; hay que medir y, si hace falta, limitar por tamaño.
- **Solid vs. Material Preview**: la variante por píxel no existe en Solid.
- **Plano borrado a mano**: el modificador queda con el input vacío y dibuja un plano falso en el origen del mundo.
- **Respaldo**: el repo ya tiene remoto en GitHub. Cada corrida de `correr_todo.sh` deja un respaldo fechado.

## 7. Decisiones

Resueltas:
1. ¿Parto por la Fase 0? — Hecha.
2. ¿Fase 1 elimina los drivers? — Hecha (v0.26.0), aunque los drivers no eran la causa.
3. Fantasma del lado descartado: se dejó blanco translúcido por ahora.

Abiertas:
4. ¿Quieres que el addon cambie el shading del viewport (Fase 4) o lo dejamos a tu elección? Se decide después de ver `diag_viewport.txt`.
5. ¿Contorno + tapa en la misma entrega, o contorno primero?
6. Si la hipótesis 5 se confirma: ¿el plano nace en el centro de la caja de la pieza? Propuesta mía; falta tu visto bueno y ver si el centro de caja es lo que esperas con piezas agrupadas.
7. ¿Commiteas la corrección del test (caso 0 contra 0)? Es la única recomendación de commit pendiente.
