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

  La lógica del gesto vive en `StrokeState`, **fuera** del operador modal, para que el ciclo de eventos se pueda testear headless con eventos simulados: el primer intento se cancelaba solo con el `RELEASE` del clic que lo lanzaba desde el panel, y ese bug pasó justamente porque esa lógica no era alcanzable por ningún test. La herramienta queda armada tras cortar, para encadenar varios cortes como en Nomad; se sale con `Esc`.

  ⚠️ **Falta la prueba a mano de los 5 modos** antes de graduarla al toolbar principal.
- 🧪 **v0.11.0 — `SiroLab`: Extrudir hacia abajo (3D Builder).** Se pone el **plano de altura** (el mismo plano verde del corte, pero horizontal, bloqueado en rotación y **limitado al alto de la pieza** con una restricción `LIMIT_LOCATION`; nace arriba del todo), se lo mueve con G o escribiendo la altura en mm, y "Extrudir hacia abajo" **no corta nada**: barre hacia abajo todo el volumen que queda bajo el plano hasta el fondo (`Fondo`, 0 mm = la placa) y lo **une** a la pieza. Una esfera queda como domo sobre un cilindro; una "C" queda con el hueco entre los brazos relleno, porque hay pieza por encima. Es lo que deja una pieza con base plana lista para fundición.

  **La primera versión hacía lo contrario** —cortaba la pieza en el plano y reemplazaba lo de abajo por la sección extruida— y el test de la esfera no lo detectó, porque con una esfera partida por su ecuador las dos interpretaciones dan exactamente el mismo sólido. El caso que las distingue, y que ahora fija la suite, es la "C": la muesca tiene que quedar **rellena**.

  En la misma pasada: el corte por forma empuja un **paso de deshacer por corte** (`ed.undo_push`). Sin eso, los cortes hechos dentro del modal quedaban fuera del stack y el Ctrl+Z se comía el paso anterior. Y se arregló por qué "no funcionaba": las 5 formas eran un **selector** con pinta de botón (se clickeaban y no pasaba nada) y el panel no avisaba cuando faltaba pieza activa. Ahora cada forma **arranca** la herramienta y Recortar/Partir es el modo.
- 🧪 **v0.11.1 — lo que salió de usar el relleno en una pieza real** (un cráneo importado de 400 000 triángulos):
  - **Los botones de la toolbar ya no heredan las propiedades de la última corrida.** Blender las recuerda, incluido lo que se toque en el panel de rehacer (F9): Leo bajó el ratio de Simplificar a 1 para probar y desde ahí el botón quedó inservible —"no se pudo reducir"— sin ninguna pista de por qué. `_boton()` en `panels.py` las resetea a su default, y se usa en todos los botones con propiedades (Simplificar, Reparar, Fusionar/Restar, corte libre, Espejo). Simplificar nunca estuvo roto: hacía exactamente lo que le pedían.
  - **Rellenar exige malla cerrada.** Una malla abierta no tiene "adentro", así que el boolean de unión no puede dar un resultado correcto; ahora lo dice —con la cuenta de aristas abiertas— en vez de devolver basura. Reusa `_open_edge_count` de Fusionar/Restar.
  - **El techo de caras ahora es medido y el mensaje manda al lugar correcto.** El boolean exacto crece bastante peor que lineal: 10 240 caras hacia arriba tardan 6,6 s y 40 960 tardan 55 s (esferas de densidad creciente, medido). *(En v0.12.0 el techo desaparece del todo.)*
- 🧪 **v0.12.0 — el relleno pasa a la sombra proyectada, el método de 3D Builder.** Leo señaló que 3D Builder hace esto sin mirar el conteo de polígonos, y que el plano *"captura un punto de vista ortográfico y toma solo lo visible"*. Tenía razón: el planteo estaba mal.

  Ahora la altura visible sale de una **grilla con un Shrinkwrap en modo `PROJECT` hacia abajo**: cada vértice cae sobre la superficie más alta de su columna y los que no tocan nada recortan la silueta. Es proyección ortográfica pura, resuelta por Blender en C — **0,2 s contra una malla de 245 000 caras**. Después se recorta a la altura del plano, se extruye hasta el fondo y se une a la pieza.

  Lo importante es *por qué* el método anterior no escalaba, y no era lo que parecía: un boolean `EXACT` contra un target de 245 000 caras y un operando simple tarda **1,8 s**, así que el tamaño de la pieza nunca fue el problema. Lo caro era que la sombra del barrido cara a cara **se auto-intersecaba** en cuanto había voladizos. La sombra proyectada es de **un solo valor por columna**, así que no se auto-interseca — y eso además habilita el solver **`MANIFOLD`**, que con la sombra vieja daba mal (dejaba la "C" sin rellenar) y ahora da volúmenes idénticos al exacto:

  | caso | barrido cara a cara | sombra proyectada + `MANIFOLD` |
  |---|---|---|
  | esfera / "C" / toro | 0,03–0,3 s | 0,6–0,7 s |
  | **245 000 caras** | **~8 min (rechazada por techo)** | **2,2 s** |

  Se van, por innecesarios: el **techo de caras**, el margen de 1 mm bajo la base y el corte de fondo propio, y el `use_self` del boolean — los tres existían solo para esquivar la auto-intersección y la coincidencia coplanar del solver exacto. El precio es que la silueta queda muestreada: selector **Detalle** con 128 / **256 (default)** / 512, que en una pieza de 30 mm son pasos de 0,23 / 0,12 / 0,06 mm.

  - **`Reparar malla` ahora deshace pellizcos.** El cráneo de Leo tenía 0 agujeros, 1 isla y 0 caras degeneradas, pero **una arista compartida por 4 caras** —la superficie tocándose consigo misma—, que la pasada no cubría; y el mensaje aconsejaba subir la distancia de soldado, que contra un pellizco no hace nada. Se agrega una etapa `select_non_manifold` + borrar por **vértice**, y el `fill_holes` que ya venía cierra el hueco. Dos detalles medidos: el operador necesita modo vértice, y devuelve vértices sueltos —2, sin ninguna cara completa—, así que un `delete(type='FACE')` no borraba absolutamente nada. Borrar por vértice se llevó 7 caras de 174 138. El reporte además **nombra el defecto** que queda en vez de dar el consejo genérico.
  - **Verificado contra el cráneo real** (exportado de la sesión de Leo, sin tocarla): Reparar 1,6 s → 0 no-manifold; rellenar 1,6 s → fondo plano exacto, 0 aristas abiertas, y el resultado queda **más liviano** que la entrada (123 887 caras contra 174 131) porque `MANIFOLD` fusiona lo coplanar.
- 🧪 **v0.12.1 — resolución del relleno.** Leo confirmó que el relleno queda como esperaba y pidió más resolución. Medido sobre su pieza real (219 151 caras), lo que limita **no es el tiempo sino el peso de la malla que sale**:

  | Detalle | tiempo | caras del resultado |
  |---|---|---|
  | 128 (Rápido) | ~1 s | — |
  | 256 (Normal) | 2,5 s | 143 000 |
  | 512 (Fino) | 5,7 s | 428 000 |
  | **1024 (Máximo, nuevo)** | 17,6 s | 1,5 millones |
  | 2048 | 64,6 s | **5,9 millones** |

  Las cuatro salen cerradas. **2048 no se ofrece**: seis millones de caras dejan la pieza inmanejable para seguir trabajándola, que es lo contrario de lo que busca un addon de preparación.

  Y el selector pasa a decir algo: `128/256/512` no le sirve a nadie, porque el escalón real depende del tamaño de la pieza —la misma resolución sobre un colgante de 4 mm y sobre uno de 40 mm da escalones diez veces distintos—. El panel ahora muestra **`Escalón del borde: X.XXX mm`** calculado sobre la pieza que tiene puesto el plano, y el test fija que ese número es exactamente el que se usa para muestrear.
- 🧪 **v0.13.0 — la toolbar se reorganiza en una sola pestaña.** SiroLab cumplió su función y desaparece: sus dos herramientas ya están probadas y pasan al toolbar. Además se va el panel contenedor que repetía el nombre de la pestaña — en un N-panel angosto cada nivel de anidamiento cuesta ancho.

  Orden nuevo, siguiendo el flujo de trabajo: **Acciones → Añadir → Transformar → Plano de corte → Corte por forma → Extrudir hacia abajo → Malla → Espejo y Acople → Relieve desde imagen**. "Alinear a la base" sube de Transformar a Acciones, junto a Agrupar/Desagrupar, porque se usa en cualquier momento y no solo al mover la pieza.

  - **Se jubila el corte libre de dos pasos.** El corte por forma hace lo mismo en un gesto y mejor: toma la vista al dibujar (el viejo cortaba a 90° de lo que veías) y trae 5 formas. Se van `SIRO_OT_draw_contour` y `SIRO_OT_free_cut`, y con ellos `free_cut.py` entero: de todo el módulo solo sobrevivían dos helpers, que se mudaron a donde pertenecen (`_apply_bool` a `boolean_ops.py`, el Douglas-Peucker a `shape_cut.py`, su único usuario).
  - **Letras X/Y/Z en el color de su eje**, en Transformar y en los botones de Espejo. Con un límite que conviene tener anotado: **Blender no deja colorear el texto de una etiqueta desde Python** — `UILayout.label()` solo acepta `text/icon/icon_value` y lo único que tiñe es `alert`, que además es rojo y nada más. La salida es `ui/iconos.py`: tres iconos de 32×32 con las letras dibujadas píxel a píxel y teñidas con los colores de eje **del tema del usuario**, así concuerdan con el gizmo del viewport y siguen su tema. Ojo al testear: sin interfaz, `icon_id` **siempre vale 0** porque Blender no asigna IDs de icono en background, así que la suite comprueba los píxeles y los colores, no el id.
  - **Pasada de UX:** "Escena en mm" solo aparece si la escena no está en mm (era un setup de una vez ocupando un botón permanente en la zona más valiosa); Malla y Relieve avisan cuando falta pieza activa, igual que los demás; el escalón del relleno deja de ser una caja y pasa a texto; Reparar deja de compartir ícono con la cabecera; y **todos** los botones de acción pasan por `_boton`, así ninguno hereda propiedades de la corrida anterior.
- ⬜ Fase 4 (nice to have): vaciar/cascarón (FDM), texto 3D de un clic.
