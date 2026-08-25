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
- ✅ **v0.16.0 — Generador de anillos por talla (sección "Anillo por talla").** Se elige **talla** (chilena 1–36, ∅ interior copiado de la calculadora del dashboard: `!Dashboard/src/components/PreciosCalculadora.tsx`), **perfil** de banda (plano / media caña / confort / biselado) y **top** de sello (rectángulo redondeado / óvalo / hexágono / sin top). El anillo queda **vivo**: los parámetros viven en el objeto (`Object.siro_ring`) y cambiar cualquiera reconstruye la malla en el mismo datablock, conservando posición, materiales y selección, hasta apretar **Aplicar a malla**.

  **Todo sale de un solo barrido, sin un boolean.** El anillo se barre alrededor de un ángulo con el eje del dedo en Y; cada paso aporta una sección cerrada y las secciones se puentean cíclicamente. El sello **no es un sólido aparte que se fusione después**: todas las formas de sello son convexas y simétricas respecto del plano medio, con el eje largo a lo largo del barrido, así que se expresan como un semiancho `w(θ)` más un recorte plano — en el sector del sello el vértice más externo de cada sección se fija en `r = z_placa / cos(θ)`, con lo que todos caen en el mismo plano y **la cara superior sale plana por construcción**, no por un corte posterior. Eso no es solo elegancia: un boolean necesita `bpy.ops`, que no se puede correr desde un callback `update=` de una propiedad, y sin él el reconstruir-en-vivo es bmesh puro y seguro.

  **El hombro es la tangente** desde el borde del sello al cilindro de la banda: una recta en el plano del anillo que aterriza sin costura. La primera versión interpolaba el radio con un smoothstep y la silueta salía **con un bulto y un pellizco** — medido: x subía a 8,97 mm a 45°, bajaba a 8,91 a 55° y volvía a subir. Sobre una recta eso no puede pasar, y encima es menos código; `hombro` pasó a repartir solo el ancho a lo largo de esa recta.

  **Dos detalles de precisión que se vieron midiendo, no mirando:** en el borde exacto del sello `x` se pasaba del largo por **un ulp** y `semiancho_top` devolvía 0, así que la sección del borde perdía su cara plana y el sello salía **13,48 mm en vez de 14**; y las muestras por sección pasaron a ser **impares**, para que siempre haya un vértice en el eje — la cresta de la media caña y la punta del óvalo, que con conteo par no existían. Con las dos cosas, los 12 combos de perfil × top dan ∅ interior 17,200 mm, sello de 14,00 × 9,00 mm, planitud 0, 0 aristas abiertas y volumen positivo.

  El test fija el bulto además de las medidas, y se comprobó que **falla** al reponer el smoothstep: era el patrón repetido de este addon que un test verde tapara un defecto a simple vista.
- ✅ **v0.17.0 — El sello gira, la banda se refuerza arriba y el hombro sigue la forma.** Tres pedidos de Leo sobre la v0.16.0, con la referencia `sr_circle_set.webp`.

  **El sello pasa de "un semiancho" a un contorno completo.** Era el límite que había que levantar primero: `semiancho_top()` devolvía un solo valor, así que toda forma quedaba obligada a ser simétrica respecto del plano medio del anillo y el hexágono no se podía girar 30° sin dejar de serlo. Ahora `contorno_top()` devuelve el polígono cerrado ya rotado y cada sección del barrido consulta por scanline el **tramo de Y** que ocupa. Dos bordes independientes en vez de uno: eso da **giro libre en grados**, formas asimétricas (**corazón** y **escudo**, nuevas) y — gratis — hombros que se adaptan a cada borde por separado.

  **Lo que ese modelo no puede representar se avisa, no se disimula.** Una sección ocupa un intervalo continuo de Y, así que la huella del sello tiene que ser un solo tramo por posición. El corazón cumple con la muesca mirando al frente; girado 90° la muesca queda a lo largo del aro, la huella se parte en dos y **se rellenaría sola**. Se detecta contando cruces del scanline y el panel lo dice en rojo.

  **`Refuerzo`: la banda deja de ser un cilindro.** `Grosor` no cambió de significado —sigue siendo el fondo del aro, que es la medida estructural— y el refuerzo suma material arriba desvaneciéndose con un coseno. Eso rompió la tangente del hombro, que apuntaba a un círculo; ahora el punto de tangencia se busca con un punto fijo de media docena de vueltas, así el hombro sigue aterrizando sin costura sobre la banda reforzada.

  **Los tres cambios de hombro:** el ancho se cierra con una **Hermite cúbica cuyo tangente inicial es la pendiente real del contorno** en el borde del sello, así que el óvalo se cierra redondo y el rectángulo se mantiene y dobla en la esquina — sale de la forma elegida, no de una curva genérica igual para todas; `Masa` sostiene la huella del sello antes de cerrarse (el bloque macizo de los sellos clásicos); y `Cintura` curva el hombro hacia adentro con un bombo que vale 0 en los dos extremos, así ni el borde del sello ni el punto de tangencia se mueven.

  **El máximo de `Cintura` está medido, no elegido:** hasta 0,60 la silueta no retrocede ni una micra, en 0,70 son 0,002 mm y en 0,80 ya son 0,072 — un pellizco visible. Quedó en **0,65**, y el test lee ese tope de la propiedad para seguir probando el extremo real si alguien lo mueve.

  **Dos bugs de borde, los dos del mismo tipo que el ulp de la v0.16.0.** El ángulo exacto del borde del sello se **salteaba** cuando había un paso del barrido cerca — pero ese vecino puede caer del lado de afuera, y entonces la sección del borde no existe: el hexágono girado 30° perdía la punta y salía 0,7 mm corto. Ahora se **reemplaza** el paso vecino. Y una cara plana angosta podía caer entre dos muestras de la sección, así que el muestreo garantiza los bordes de la cara plana. Con las dos cosas, las 5 formas dan huella exacta contra el bbox de su contorno.

  Además: la curva del corazón no está centrada (va de −17 a +5), así que se encaja en su bbox en vez de dividirse por el máximo absoluto; antes salía descentrada y con 6 mm de alto en vez de los 9 pedidos. 24 combinaciones de forma × perfil: 0 aristas abiertas, volumen positivo, ∅ 17,200 mm, sello 14,00 × 9,00, planitud 0. Reconstrucción en vivo a 512 segmentos: **35 ms**.
- ✅ **v0.18.0 — El hombro y el sello dejan de tener un escalón.** Leo mostró la v0.17.0 con un top circular: las bandas de los costados quedaban **cortadas**, con una aleta con filo justo antes del sello, contra la continuidad del render de referencia `circle-v1-side.png`.

  **No era resolución ni un ajuste de perilla: la superficie tenía un salto de un milímetro.** Adentro del sector del sello, el material que flanqueaba la placa caía hasta `r_banda(a)` —el **aro pelado**— mientras el hombro de al lado ya estaba sobre la recta tangente: 11,264 mm contra 12,251 mm en el borde exacto del sello. Sólo se dispara en las formas cuya huella se **angosta antes del borde** (óvalo, círculo, punta del hexágono, corazón, escudo); el rectángulo llega al borde con la huella entera y por eso ese caso siempre se vio bien y los tests pasaban.

  **La placa y el aro dejaron de turnarse.** Antes cada sección era placa **o** hombro **o** banda según el ángulo, y las dos primeras chocaban en el borde. Ahora cada sección es siempre el **cuerpo** —una media caña barrida con su radio y su semiancho— con la **placa** puesta encima donde la huella la tapa: `r = max(cuerpo, placa)`. En el borde del sello las dos ramas del radio del cuerpo coinciden **por construcción** (la recta tangente se trazó justo por ese punto), así que el escalón no se disimula: no existe. La cara del sello sigue saliendo plana sola. **Borró más de lo que agregó:** se fueron `redondez`, `plano`, `hombrito`, `r_caida` y todo el bloque de pendientes `m0`/`m1` con sus topes.

  **El ancho pasó a ser una envolvente.** El `max(huella, ancho de banda)` dejaba un codo: el semiancho del óvalo bajaba 0,21 mm por grado y se cortaba en seco al cruzar el ancho de la banda — en planta, un vértice donde tenía que haber una curva. Ahora es una Hermite anclada en el contorno del sello que aterriza en la banda con pendiente 0. `Masa` conserva su papel pero se mide **desde el tope del anillo** y tiene **piso**: la envolvente no puede empezar a cerrar antes de que la placa termine, o el borde del sello se queda sin apoyo.

  **Los dientes de sierra alrededor del sello eran topología, no geometría.** `_muestras_y` repartía las muestras **proporcionalmente al largo de cada tramo**, así que el índice del vértice del borde del sello cambiaba de una sección a la siguiente y el puenteado cíclico lo unía con un vértice interior de la vecina. El cupo por tramo pasó a ser fijo; donde un tramo mide cero las muestras caen encima y las suelda un `remove_doubles`.

  **Y el ulp mordió por tercera vez.** `d = ((th + π) % 2π) − π` le comía un ulp a `th`, y el borde del sello —que se mete como paso **exacto** del barrido desde la v0.17.0— caía del lado de afuera: el escudo girado 90° perdía la sección del borde entera y dejaba 1,5 mm de escalón. Se saca el `%` y se compara con holgura.

  El test nuevo mide la **cornisa** —el canto del anillo en la sección del borde contra su vecina de afuera, sólo del lado donde la placa no llega hasta el canto— y el **quiebre de pendiente del semiancho**. Con la v0.17.0 repuesta dan 3,232 mm y 1,517 mm/° contra topes de 0,35; con la v0.18.0, 0,113 mm y 0,12 mm/°. Los 25 casos de forma × perilla × giro siguen cerrados, con ∅ 17,200 mm, sello exacto y planitud 0. Reconstrucción en vivo: **17 ms** en Detalle Medio, **57 ms** en Alto.

- ✅ **v0.19.0 — El sello deja de ser una placa y pasa a ser el plano que corta el cuerpo.** Leo mostró la v0.18.0 con un óvalo de 16×12 y una referencia CAD (`2.png`): la cabeza salía como un bloque con aletas planas a los costados, el agujero deformado, y el perfil **Plano** aplanaba todo y borraba el contorno del sello.

  **El modelo estaba al revés.** Hasta acá el sello era una placa que se ponía ENCIMA del cuerpo (`max(cuerpo, placa)`). En un sello de verdad —y en la referencia— el sello es el **plano que corta el cuerpo**, y su contorno es la intersección: por eso el borde no tiene ni cornisa ni escalón, el cuerpo cruza el plano con un ángulo y no con un salto. Ahora es `min(lomo, r_placa)`, y la media caña del lomo se dimensiona al revés de lo obvio: se levanta lo justo para que el cruce caiga **exacto** en la huella pedida, así el sello sigue midiendo lo que dice la perilla.

  **La sección pasó de dos tramos a cuatro: flanco, lomo, flanco y agujero.** La cabeza es mucho más ancha que el aro, y ese desnivel se resuelve con las caras laterales inclinadas —un cuarto de elipse tangente al lomo— en vez de un bloque de lado a lado. Las aletas planas de los costados eran justamente ese bloque muriendo de golpe contra la banda; el agujero deformado, el mismo bloque visto desde adentro.

  **En planta el anillo ABRAZA la forma.** El ancho es `max(huella, ancho de banda)` con un **máximo suave quíntico**: tan ancho como el sello donde el sello es ancho y como la banda donde no. El `max` a secas dejaba un vértice, y sostener el ancho máximo del sello hasta el borde dejaba un ladrillo alrededor del óvalo. `Masa` conserva su papel —sostener el ancho del sello más allá de su contorno— pero ahora es lo único que engorda la cabeza.

  **`Perfil` describe la BANDA, no la cabeza.** Con `Plano` el perfil se aplicaba también arriba, la cara del sello quedaba al ras del cuerpo y el contorno desaparecía. La cabeza es siempre una media caña y `Perfil` entra recién hacia la banda.

  **Tres bugs de borde en el camino:** el chaflán se medía desde el eje de la sección y se comía la cara del sello en las formas asimétricas (corazón biselado: 8,61 mm en vez de 9); `recalc_face_normals` elegía el lado de adentro y dejaba volumen negativo (en un cerrado manifold el signo del volumen no es una heurística, así que manda él); y pasado el borde del sello la huella desaparecía de golpe, lo que en el rectángulo era una cornisa de 2,7 mm — ahora se achica.

  Las 24 combinaciones de forma × perfil siguen cerradas, con ∅ 17,200 mm, sello exacto y planitud 0. Tests nuevos: el hombro no quiebra fuera del sello (**0,03 mm/°** contra 0,60 de la v0.17.0) y la cabeza abraza la forma (**0,0 mm** de exceso contra 0,95 de la v0.18.0); adentro del sello no se mide, porque ahí un vértice es la forma pedida —la esquina del rectángulo, la punta del óvalo— y no un defecto. Reconstrucción en vivo: **21 ms** en Detalle Medio.

- ✅ **v0.20.0 — `Marco`: la cinta que bordea el sello y baja por los hombros.** Leo marcó en rojo, sobre su propia captura, la parte que faltaba: un borde continuo que rodea la cara del sello y sigue por los dos hombros, con perillas propias.

  **`Marco` (mm)** es el bisel de esa cinta. Va **por afuera** de la huella, así que `Largo × Ancho del top` siguen siendo la cara del sello: subir el marco engorda el anillo, no achica el sello. Se apaga hacia la banda, donde vuelve a mandar `Perfil`. En 0 el sello va a canto vivo.

  **La cinta va pegada al CANTO de la sección, no al borde del sello.** Bajo el sello los dos coinciden —la sección es la huella más el marco— pero pasado el borde el sello ya no existe, y anclarla ahí la dejaba corriendo por el **medio** del hombro, con una muesca en V donde se topaba con la del sello. Esa muesca era exactamente lo que Leo venía marcando.

  **La malla sale con sombreado suave y las aristas vivas marcadas.** No es cosmético: el anillo es una superficie barrida y en sombreado plano se ve como una escalera de facetas. Tres pasadas se fueron persiguiendo "escalones" que en la geometría no existían — medidos, eran facetas del viewport. Las aristas de verdad (la cara del sello, los dos bordes del marco, el canto del aro) se marcan y siguen saliendo vivas.

  Además: el muestreo del flanco pasó a ser **por ángulo** y no por altura (en una cabeza fina y ancha todo el recorrido en Y caía en el último tramo y el costado salía en escalones de verdad), y el marco entró al presupuesto de grosor junto con el bulto y el chaflán. Las 24 combinaciones siguen cerradas, con ∅ 17,200 mm, sello exacto y planitud 0. Reconstrucción en vivo: **24 ms** en Detalle Medio.

- ✅ **v0.21.0 — Forma `Círculo`, `Pared` y `Afinado`.** Leo mostró un círculo de 14 mm sobre una banda de 5: *"la circunferencia del anillo no cubre los bordes del círculo"*, contra la foto de un anillo real donde la pared baja a plomo bajo el contorno.

  **`Pared` (0–1)** es lo que faltaba, y era lo mismo que venía reportando desde tres pasadas atrás con otras palabras. La sección de la cabeza es un trapecio: ancha arriba, del ancho de la banda contra el agujero. Con un sello mucho más ancho que el aro ese trapecio es un **cono**, y el sello queda flotando sin que el aro llegue a cubrir su borde. `Pared` dice cuánto de esa pared baja **a plomo**: en 0 es el cono de antes, en 1 el aro baja recto bajo el contorno de la forma. Default 0,5.

  **`Afinado` (0–0,7)** adelgaza la banda hacia el fondo del aro y la deja entera arriba —el mismo criterio que `Refuerzo` con `Grosor`—, así `Ancho` sigue significando el ancho bajo el sello, que es la medida que se mira.

  **`Círculo`** es una forma propia con un solo **Diámetro**: `Ancho del top` deja de mostrarse. Óvalo con largo = ancho hacía lo mismo, pero obligaba a mantener dos números iguales a mano.

  Los tres tienen test: la pared cubre el 0,45 del contorno con `Pared` en 0 y el 0,98 en 1; el afinado deja el ancho de arriba clavado en `Ancho` y el del fondo en `Ancho × (1 − Afinado)`. Las 24 combinaciones de forma × perfil pasan a ser 24 con el círculo adentro, todas cerradas, con ∅ 17,200 mm y sello exacto.

- ✅ **v0.22.0 — `Cabeza`: qué es la superficie que rodea al sello.** Leo mostró un hexágono girado 90° sobre una banda de 8 mm y fue bajando `Largo` de 12 a 1 mm: *"queda en una forma curva al llegar a 1 mm, siendo que debería ser una superficie plana"*.

  **La cara del sello estaba bien; el problema era lo que la rodeaba.** Medido, a `Largo` 1 mm los vértices que caen exactamente en el plano del sello forman una superficie de **8,00 × 1,00 mm**, plana a 1e-6: las perillas se respetaban. Lo que se veía curvo era la cabeza — la sección del tope caía de 13,850 a 12,111 mm, un **domo de 1,74 mm** sobre los 8 mm de la banda, con la cara de 1 mm perdida adentro como un filo.

  **Y el domo crecía con perillas que no tenían por qué curvarlo:** `Alto` 0,5 / 1,5 / 4 daba 1,40 / 1,74 / 2,50 mm. La causa era una sola línea: `cana = min(grosor * 0.55, …)` con `grosor = r_ext - r_int`, y bajo la placa `r_ext` **es el plano del sello**, así que ese grosor era la cabeza entera —banda + refuerzo + alto, 4,3 mm— y no los 1,8 mm de la banda. Una perilla que sube el sello no puede curvar lo que tiene al lado. Ahora la media caña se dimensiona por el grosor de la **banda**; en la banda pura los dos valores coinciden, así que ahí no cambió nada. Con `Alto` 0,5 y 4 el domo mide lo mismo: 0,713 mm.

  Con eso arreglado, qué es la cara de arriba por **fuera** de la huella pasa a ser una decisión, no un accidente, y Leo pidió las tres elegibles. La perilla nueva **`Cabeza`** las ofrece, y monta sobre `mezcla` —que ya valía 1 en la banda y 0 en la cara del sello— así que el empalme con el hombro sale continuo sin maquinaria nueva:

  - **`Plana`** (default) — el bulto se desvanece con `mezcla`: la cara de arriba es **un solo plano**, y al achicar el sello el top nunca se curva. La meseta mide 0,000 mm de caída con `Largo` 12, 7,6 y 1.
  - **`Abombada`** — la media caña de siempre, ya sin inflarse con `Alto`. Conserva la medida del sello (8,00 × 1,00) porque el marco va por afuera de la huella.
  - **`Relieve`** — el sello se para **sobre** el lomo de la banda: el cuerpo es la banda y la placa se suma encima donde la huella la tapa, con el marco bordeándola y una **pared vertical** de 0,95 mm en todo el contorno. Es la doctrina `max(cuerpo, placa)` que el docstring del módulo venía describiendo desde la v0.17.0. `Masa` y `Cintura` no tienen hombro que mover en este modo.

  Dos detalles que costaron una pasada cada uno. El marco del relieve entró primero **hacia adentro** de la huella, y 0,6 mm de marco se comían entera la cara de un sello de 1 mm; va por afuera, como en los otros dos modos. Y la pared del relieve necesita dos muestras pegadas al borde de la huella o el salto se reparte sobre el primer tramo libre —casi un milímetro— y sale como chaflán: van en **todas** las secciones, porque el puenteado cíclico exige el mismo conteo de vértices en todas (sin sello caen sobre el centro y las suelda el `remove_doubles` del final).

  Tests nuevos sobre el caso reportado: los tres modos cerrados y con volumen positivo, `Plana` con menos de 0,03 mm de caída en la meseta (había 1,74), `Abombada` con el domo clavado ante `Alto` y bajo 0,9 mm, y `Relieve` con pared de verdad. `Refuerzo` y `Grosor` **sí** mueven el domo y así queda asentado: son el grosor de la banda. Las 6 formas × 3 modos × 4 perfiles a `Largo` 1 mm — 72 combinaciones — salen cerradas y con volumen positivo.

- ✅ **v0.23.0 — Peso en plata, en vivo.** Leo preguntó cuánto volumen tiene la pieza para calcular los gramos de plata. **El número ya estaba calculado y se tiraba**: `construir()` computa el volumen con signo para decidir si da vuelta las normales —en un cerrado manifold el signo no es una heurística— y después lo descartaba. Ahora lo devuelve, `_reconstruir` lo guarda y el panel muestra `mm³ · g en plata 950` bajo `Detalle`, así que el peso se mira **mientras se mueven las perillas** y no después de exportar, que es cuando sirve para cotizar.

  Dos detalles que sin test habrían salido mal. `calc_volume` mide la malla **local**: con el objeto escalado el peso real no es ése, así que se multiplica por el determinante de la matriz de mundo (el factor de escala al cubo). Y el control del test no es otra corrida del mismo código sino **geometría con fórmula**: una banda `Plano` sin top ni refuerzo es un tubo, y el addon da 945,5 mm³ contra 945,5 teóricos — 0,00 % de error. El caso del escalado se prueba aparte: al doble de tamaño tiene que pesar ocho veces.

  **La densidad es la de la ley 950** (95 % plata fina, 5 % cobre), que es con la que se trabaja acá. Lo que fija el peso no es el peso atómico sino la densidad de la **aleación**, y sale de la regla de volúmenes aditivos sobre los dos metales —plata fina 10,49 y cobre 8,96 g/cm³—: `1/ρ = 0,95/10,49 + 0,05/8,96` → **10,4012 g/cm³**. La misma cuenta devuelve 10,357 para la 925, que es el 10,36 de tabla: ésa es la comprobación de que está bien planteada y no es un número copiado de algún lado.

  **El peso depende de `Detalle`**, y no es un bug: la malla es un poliedro **inscrito** en la superficie barrida, así que siempre queda corta. El mismo anillo da 13,61 g en Bajo, 13,87 en Medio y 14,03 en Alto. Para cotizar, Alto. Y es el peso de la **pieza**: la fundición pide además bebedero, botón y mermas, que no salen de la geometría.

- ✅ **v0.24.0 — El contorno del sello recto, el marco parejo y el peso de cualquier pieza.** Leo mostró un hexágono en vista superior y delineó en rojo cómo tenían que quedar sus lados: **rectos**.

  **La cara seguía el hexágono exacto casi entera, y se inflaba cerca de las puntas.** Medido con sus parámetros —talla 20, banda 8, `Largo` 12, `Ancho del top` 8—, el borde daba 6,109 donde la huella dice 6,000, con el desvío máximo de **+0,194 mm** a 0,6 mm de la punta: el sello salía de **12,219 mm en vez de 12** y la punta quedaba roma. La causa: las cuatro llamadas a `_maximo_suave(…, w_b, w_b)` pasaban **`w_b` como radio de filete**. `w_b` es el semiancho de la banda ENTERO, así que la mezcla entre "ancho del sello" y "ancho de la banda" estaba activa en todo el recorrido en vez de en una franja, y el smooth-max sobrepasa hasta `0,1875·k` — con k = 4 mm, hasta 0,75.

  **No era del hexágono.** Le pegaba a toda forma cuya huella quedara a menos de `w_b` del ancho del aro: un **óvalo 12×8 sobre esa misma banda salía de 9,5 mm de ancho en vez de 8**. Los tests no lo veían porque corren con los defaults (banda 4, sello 9), donde la huella está lejos del ancho del aro y el max sale exacto. Ahora el radio es una constante propia, `SUAVIZADO_PLANTA = 0,25 mm`, elegida para que el sobrepaso máximo (0,047 mm) quede bajo los 0,05 con que los tests miden el sello. Resultado: desvío de la recta **0,001 mm**, sello de **8,000 × 12,000**, y las seis formas midiendo el bbox de su propio contorno.

  **`Marco`, el mismo defecto un paso más allá.** Se desvanecía con `mezcla`, que ya vale 0,34 en el borde del sello: el bisel medía 0,600 mm en el centro y **0,395 en la punta**, un 34 % más angosto, y como `mezcla` no es lineal en θ también curvaba el contorno. El desvanecido sigue existiendo —sin él el bisel de la banda muere bajo el sello y deja una muesca en V— pero pasa a ocurrir en el **hombro**, entre `lim` y `a_t`, que es donde tiene que morir. Medido: 0,600 parejo en todas las secciones del sello.

  **Y el botón `Peso`** en la sección Malla, porque la línea del panel del anillo desaparece justo cuando la pieza está terminada: al aplicarla a malla, después de los cortes y los booleans. Mide cualquier selección y devuelve `mm³ · cm³ · g en plata 950`. Sobre una malla **abierta no inventa un número** —el volumen de una malla abierta no significa nada—: avisa y manda a Reparar malla. Tiene test de que da lo mismo que la línea del panel.

  144 combinaciones (6 formas × 3 `Cabeza` × 4 perfiles × 2 tamaños de sello) cerradas y con volumen positivo.

- ✅ **v0.25.0 — `Redondeo` para toda forma con esquinas, no solo el rectángulo.** Era la única perilla condicionada por forma: hexágono, escudo y corazón tienen esquinas y no había cómo suavizarlas. El código propio del rectángulo se reemplazó por un filete genérico que reconoce esquinas vivas (ángulo interior bajo 150°) en cualquier contorno cerrado y les arma un arco tangente.

  **En el rectángulo, el hexágono y el canto del escudo el radio es exacto**, porque ahí las dos aristas de la esquina son rectas: medido por cuerda, `Redondeo 1,2` da 1,200 mm en las tres. En la **punta y la muesca del corazón** las aristas son curvas de una paramétrica, no rectas de un polígono —y encima una cúspide de 6° pediría recortar 19 veces el radio por lado—, así que quedó **afuera a propósito**: la perilla no aparece con el corazón seleccionado y `contorno_top()` lo confirma con un test (mismo contorno con `Redondeo` 0 o 2).

  **Redondear una punta la acorta**, y eso hubiera sido un bug nuevo del mismo tipo que el de la v0.24.0: un hexágono de 12 mm con 1,2 mm de filete media 11,38 antes de corregirlo, porque el filete se resta del contorno crudo. Ahora el molde se agranda y se vuelve a redondear hasta que el contorno YA filetado mida lo que piden `Largo` y `Ancho del top` —converge en un par de vueltas—, así que el hexágono sigue midiendo 12 × 8 con cualquier radio.

  **Un radio grande no puede comerse la forma.** Dos frenos: el recorte no pasa de la mitad del tramo hacia la esquina vecina (si no, dos filetes se pisan y el contorno se cruza a sí mismo), y no pasa de la mitad del semieje menor de la forma. Con `Redondeo 5` sobre un sello de 6 mm de semiancho, el radio que realmente entra es 2 mm, no 5 — medido, y con test de que ninguna de las tres formas con esquinas sale abierta o con volumen negativo a ese extremo.

  216 combinaciones (6 formas × 3 `Cabeza` × 4 perfiles × 3 radios de `Redondeo`) cerradas y con volumen positivo.

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
  - **Pasada de UX:** "Escena en mm" solo aparece si la escena no está en mm (era un setup de una vez ocupando un botón permanente en la zona más valiosa); Malla y Relieve avisan cuando falta pieza activa, igual que los demás; el escalón del relleno deja de ser una caja y pasa a texto; Reparar deja de compartir ícono con la cabecera; y los botones de acción pasan por `_boton`, así no heredan propiedades de la corrida anterior. (Quedan fuera los toggles, que no tienen propiedades que heredar, y `Cortar`, que abre un diálogo donde los valores están a la vista.)
- 🧪 **v0.14.0 — ahora el addon también *produce* depthmaps, no solo los consume.** Hasta acá el relieve exigía traer el gris ya hecho desde GIMP. Se suman dos caminos, sin IA y sin dependencias nuevas (numpy ya viene con Blender):

  - **Relieve desde pieza 3D** — profundidad **real**, sin render, sin cámara y sin pase Mist: reusa el mismo Shrinkwrap `PROJECT` con el que el relleno imita la vista ortográfica de 3D Builder (0,06 s contra 8 000 caras, medido). Sale a tamaño real y con la Profundidad ya puesta en los mm que mide la pieza — una esfera de radio 15 da 15,00 mm, y eso lo fija el test.
  - **Preparar depthmap** — para imágenes a color, donde **no hay profundidad que recuperar** y hay que fabricarla: silueta + domo por distancia al borde + luminancia como detalle, con sliders Domo / Contraste / Tolerancia / Invertir. El distance transform va en numpy puro (pila de erosiones alternando vecindad 4 y 8, porque Blender no trae scipy): 0,55 s a 768² en el peor caso, y por eso es un botón y no un `update` de slider.

  **Lo que se midió y cambió el diseño:** la idea de quitar el fondo automáticamente **no sobrevivió a la medición**. Sobre un render de fondo degradado con sombra proyectada, el degradado del propio fondo varía *más* que la diferencia entre fondo y pieza (fondo hasta 0,235 de distancia RGB; partes de la pieza en 0,180–0,198), así que **no existe umbral que los separe** — y no lo arreglan ni una cuadrática ajustada al marco ni el matiz; las tres se probaron y las tres devuelven un bloque en vez de una silueta. Conclusión: **el camino bueno es el alpha** (un render con *Film → Transparent* lo trae gratis, y es exacto). El color de esquina queda como respaldo para fondos planos de verdad, y el operador **avisa con un WARNING cuando tuvo que adivinar**, en vez de dar el resultado por bueno.

  **Y de paso, `Aplicar relieve` dejó de destrozar la pieza.** Cerraba la lámina con un Solidify, que desplaza cada vértice a lo largo de su normal: sobre un heightfield con paredes verticales —y con la escala no uniforme del relieve, que en local empina las pendientes 2,5×— la base se arrastraba **2,5 mm de costado en una pieza de 5 mm**, el grosor caía de 1 mm a **0,03 mm** y la malla quedaba auto-intersecada (volumen con signo negativo: ni orientable, y Fusionar habría dado basura). La cara con el relieve nunca se movía, así que el test viejo —que solo miraba que quedara cerrada y con altura— la daba por buena. Ahora la base se aplana a mano sobre la topología que arma el Solidify: mismo XY que la cara de arriba, Z constante. Base plana, que además es la que apoya para fundición, y el "Grosor de base" pasa a ser el material bajo el punto más bajo del relieve. Medido tras el arreglo: arrastre 0,0 mm, grosor exacto y volumen positivo en los tres casos.

  El depthmap generado va en **float y Non-Color**: los valores que escribimos son la altura que desplaza la malla, y leerlos de vuelta como sRGB les metería una gamma que nadie pidió. Preparar dos veces no compone efectos —siempre parte del original, que queda anotado en `siro_source`— y el test lo fija.
- 🧪 **v0.15.0 — los 12 hallazgos de la auditoría** (informe completo en `AUDITORIA_2026-07-25.md`). El patrón que la auditoría destapó: **cuando la geometría del corte coincide con geometría que ya existe en la pieza, el resultado era basura y nadie avisaba** — y justo en la posición por defecto del plano, sobre las piezas más comunes en joyería.

  - **Cortar una esfera por el ecuador o un toro por el medio dejaba la pieza rota**: 32 aristas de borde, 32 no-manifold y 32 caras de área cero (48 y 48 en el toro). Cuando el plano cae sobre vértices que ya existen, `bisect_plane` devuelve en `geom_cut` aristas que **ya tienen dos caras**, y el agujero real de la malla es otro: tapar `geom_cut` a ciegas creaba caras encima de las que ya estaban *y* dejaba el agujero sin tapar. Ahora se tapa lo que quedó **abierto sobre el plano**, que en un corte normal es exactamente lo mismo.
  - **El corte por forma centrado sobre una esfera la borraba** (volumen 2110 → 0, 12 vértices). El culpable era el solver `FLOAT`, y resultó que **no tenía ninguna razón de existir**: medido, `MANIFOLD` es *más rápido* —8,06 s contra 9,87 s sobre dos millones de caras— y correcto donde FLOAT destruye. Así que el solver se elige solo con el mismo criterio que Fusionar/Restar (cerrada → MANIFOLD, abierta → EXACT) y **el selector "Calidad" desaparece**: una perilla menos y ninguna elección que el usuario pueda errar.
  - **"Alinear a la base" dejaba flotando 4,30 mm** cualquier pieza rotada: medía sobre `bound_box`, que es la caja **local** y al rotarla cae más abajo que la malla. Ahora mide los vértices reales.
  - **Fusionar con una pieza abierta** aplicaba el boolean igual —dejando el target con 12 aristas no-manifold donde no había ninguna— y después avisaba "piezas conservadas", que se lee como "no hice nada". Ahora valida y cancela **antes** de tocar la pieza, como ya hacía el relleno.
  - **Modo Acople y Marcar selección devuelven lo que era tuyo.** Los dos apagaban escribiendo valores fijos: el primero te dejaba el snap apagado y en `INCREMENT` aunque estuvieras trabajando con snap a vértices; el segundo pintaba de blanco **todos** los objetos de la escena. Ahora guardan y restauran. El test del acople, que fijaba el comportamiento equivocado, también se corrigió.
  - **El espejo pasa al eje de MUNDO**, que es el que muestra el gizmo y del que los botones toman su color. Antes reflejaba sobre el eje local: con la pieza sin rotar da igual, con la pieza rotada el botón prometía un plano y usaba otro.
  - **Simplificar avisa por deformación, no por conteo.** Bajar el número de triángulos no es haber salido bien: con 12 triángulos el Decimate se llevaba el 63 % del volumen y reportaba `Info: Triángulos: 12 → 6`. El aviso va sobre la variable que importa —cuánto cambió la pieza— y no sobre un tope de caras: la pérdida depende de la densidad (63 % a 12 tris, 3,7 % a 192, 0,1 % a 3072), no del tamaño.
  - Y tres chicos: el panel **Plano de corte** avisa cuando no hay pieza activa, como el resto; la clave de grupo deja de quedar colgada tras fusionar; y el README dice lo que el código hace sobre `_boton`.

  **Un hallazgo que la medición dio vuelta.** Las caras degeneradas que deja el relleno (1002 a resolución 128, 3454 a 512) parecían basura a limpiar. No lo son: un boolean posterior sobre esa pieza sale **perfecto** (cerrada, volumen exacto), y los cuatro remedios probados —`dissolve_degenerate` a dos distancias, `remove_doubles`, y ambos juntos— la **rompen**, dejando entre 59 y 4252 aristas no-manifold donde no había ninguna. Se descartó el arreglo.

- 🧪 **v0.15.1 — `Reparar malla` dejó de romper las piezas rellenadas.** Apareció midiendo lo anterior: una esfera rellenada **sana** salía de Reparar con 3064 aristas de borde, tras 23,5 s de trabajo. El daño son agujeros, no pellizcos — `dissolve_degenerate` borraba 7588 caras y abría 4183 aristas, y el `fill_holes` posterior solo tapaba parte.

  Dos capas: **una malla ya cerrada no se toca** (si llega sin aristas no-manifold no hay nada que reparar: informa y sale, 0,2 s en vez de 23,5 s), y **reparar no puede devolver la pieza peor de lo que llegó** — se guarda la malla antes, gratis por copy-on-write (0,000 s sobre 373 000 caras), y si el no-manifold sube se restaura y se avisa. El precio, dicho de frente: una pieza rellenada **con** un agujero real hoy no se puede reparar; se la devuelve como llegó en vez de destrozarla.

  **Y un hermano introducido por el arreglo del corte:** ese arreglo había puesto un `dissolve_degenerate` sobre **toda la malla**, que es justo el patrón que rompe a Reparar — cortar una pieza rellenada la abría (21 aristas de borde, 60 no-manifold). Ahora la limpieza toca solo las aristas **del plano de corte**, las que el propio corte colapsa.

  La lección, ya tres veces seguidas: **`dissolve_degenerate` y `remove_doubles` sobre una malla que ya está cerrada no cosen, borran.** Sirven para reparar lo roto, no para limpiar lo sano.
- 🧪 **v0.15.2 — el fantasma del corte moría al abrir cualquier archivo.** Leo reportó que el plano de corte no le mostraba el ghost. Medido en su sesión con una pieza real: **0 caras fantasma de 250 185**, con el addon perfectamente habilitado y todo el sistema bien montado (modificador puesto, materiales `[None, SiroGhostFantasma]`, `show_transparent` en True).

  La causa: **Blender vacía `bpy.app.driver_namespace` cada vez que carga un `.blend`**, y la función que alimenta los drivers del fantasma se inyectaba solo en `register()` — que corre una vez al arrancar y no vuelve a correr al abrir un archivo. Los seis drivers quedaban `is_valid: False`, los sockets del modificador en cero, y con la normal del plano en `(0,0,0)` el producto punto da 0 — que no es `< 0`, así que ninguna cara se marca. El docstring del módulo anticipaba el caso "abrir un .blend con el addon deshabilitado"; el real es peor, pasa con el addon habilitado y con solo abrir un archivo.

  El arreglo es un handler `load_post` que repone la función, y tiene que ser **`@persistent`** o se borraría a sí mismo en la primera carga. Verificado en el ciclo real —guardar, abrir, medir—: 6/6 drivers válidos y el fantasma de vuelta al 50 %. Con su test, que comprueba el comportamiento (que la función se reponga tras cargar) y no solo que el handler esté puesto.

  **Ojo con un detalle que no es del addon:** los gizmos de mover/rotar/escalar se guardan **por screen dentro del .blend**. En el archivo de Leo estaban apagados en los 10 screens, así que ningún eje respondía — y no era el addon (no toca los gizmos en ninguna de sus 3081 líneas). Se activan desde la flechita junto al ícono de gizmo, arriba a la derecha del viewport, y hay que **guardar el archivo** para que queden.
- 🧪 **v0.15.3 — "Cancelar corte" dejaba la escena sin selección y el gizmo dejaba de mover.** Leo reportó que veía los ejes sobre la pieza, los arrastraba y no pasaba nada; con `G` sí se movía, y los campos del panel Transform también. Su pista fue la que resolvió el caso: *"los candaditos los bloqueé y luego los desbloqueé y por algún motivo se desbuguea"*, y andaba **hasta que hacía algo**.

  El plano de corte nace **activo y como único objeto seleccionado** (`add_cut_plane`), y `cancel_cut` lo borraba sin devolverle el foco a nadie: la escena quedaba con `activo=None` y sin selección. En Blender el gizmo se **dibuja** tomando como referencia el objeto activo, pero `transform.translate` opera sobre los **seleccionados** — así que los ejes aparecen y arrastrarlos no hace nada. `G` seguía andando porque al invocarlo el usuario vuelve a seleccionar, y tocar un candado forzaba el refresco que lo "desbugueaba".

  Medido, cambiando una sola variable: tras `cancel_cut`, `activo=None seleccionados=[]`; tras `siro.cut` o `extrude_down` —sus dos hermanos, que **sí** restauran—, `activo=Cube seleccionados=['Cube']`. `cancel_cut` era el único de los tres sin restaurar: el patrón correcto ya estaba en el addon. Ahora resuelve la pieza objetivo *antes* de borrar el plano (con el mismo criterio que `siro.cut`: la clave `siro_target` y, si no, quién lleva puesto el fantasma) y le devuelve el foco.

  **Se barrieron todos los hermanos**, porque el patrón del bug es *borrar un objeto que era el activo sin restaurar el foco*: `boolean` (borra los operandos), `bake_depthmap` (borra la grilla de muestreo), `shape_cut` (borra el cortador), `extrude_down` (grilla y sombra), `add_cut_plane` (el plano anterior), más `repair`, `simplify`, `mirror`, `align_base`, `group`/`ungroup`. Los quince quedan con activo válido y seleccionado. Con test para los dos caminos de cancelar (plano de corte y plano de altura).

  **Lo que NO era**, aunque lo parecía: Wayland. Se llegó a desactivar *Continuous Grab* persiguiendo esa hipótesis y hubo que revertirlo. Los keymaps estaban intactos (`keymaps modificados por el usuario: ninguno`), los umbrales de arrastre en su default, y el objeto se movía perfecto por código.
- 🧪 **v0.15.4 — las formas que insertaba el panel nacían colapsadas en un punto.** Lo destapó Leo pasando una copia de la **v0.9.0**, donde "insertar forma y mover objetos funcionaban perfecto": comparar contra una versión sana valió más que cualquier hipótesis.

  La regresión entró en v0.13.0, cuando las primitivas pasaron a dibujarse con `_boton`. Ese helper resetea **todas** las propiedades del operador a su default para que ningún botón herede lo de la corrida anterior — pero en los operadores de añadir, `scale` no es un valor: es un **centinela**. Su default `(0,0,0)` significa "sin escala especificada", y escrito literalmente multiplica la geometría por cero. Medido: la misma llamada da `dim=(30, 30, 30)` como en 0.9.0 y `dim=(0, 0, 0)` con `_boton` — 64 vértices, todos en el origen, **invisible**.

  De ahí el síntoma que Leo venía describiendo: insertaba un cilindro, no aparecía nada, y el gizmo quedaba plantado sobre ese objeto de tamaño cero en el origen. Arrastrar los ejes no movía nada visible.

  El arreglo es una lista explícita, `_PROPS_DE_CONTEXTO` = `location`, `rotation`, `scale`, `align`: las que Blender rellena desde el contexto en su `invoke` (cursor 3D, orientación de la vista) y donde el default es un centinela, no un valor. `_boton` sigue reseteando todo lo demás, que es para lo que existe.

  **Y el test tenía el mismo agujero de siempre:** llamaba al operador directo con `**props`, esquivando `_boton` — el camino que el usuario nunca recorre. Ahora pasa por las propiedades reseteadas de verdad, y además fija el centinela: si `scale=(0,0,0)` dejara de colapsar la primitiva en una versión futura de Blender, el test avisa para revisar si la exclusión sigue haciendo falta.
- ⬜ Fase 4 (nice to have): vaciar/cascarón (FDM), texto 3D de un clic.

## Ideas para el futuro

Analizadas contra el ecosistema en agosto de 2026, para no reimplementar lo que ya existe
al lado. **JewelCraft** —que Leo tiene instalado en la pestaña de al lado— cubre gemas,
garras, cutters, biblioteca de componentes, mapas de piedras, reportes JSON/HTML y **peso
en aleaciones**; sus huecos documentados son justamente *talla* y *generación de aro*, que
es donde vive SiroBuilder. **MatrixGold** (el CAD pago del rubro) suma wizards paso a paso,
*smart prongs*, builders de bisel y canal, y **Azure cutters** para vaciar metal del interior
del aro.

> ⚠️ El `Peso` de la v0.23.0 **se pisa con JewelCraft**, que ya calcula peso en aleaciones.
> El nuestro se gana el lugar por estar en el panel del anillo vivo —se actualiza mientras
> se mueven las perillas— y por estar en la ley 950 concreta en vez de una tabla genérica.
> Antes de invertir más ahí, mirar si JewelCraft no lo resuelve.

Ordenadas por (valor × encaje) / esfuerzo:

1. ⬜ **Verificación de fundibilidad — "¿esto se puede hacer?"** Es la mitad que falta de la
   v0.23.0: `Peso` responde *cuánto cuesta*, esto responde *si sale del molde*. Marcar dónde
   la pared baja de **0,8 mm** (mínimo de fundición en plata), avisar si el aro baja de
   **1 mm**, y avisar si la cara del sello queda bajo los **8 mm** que necesita un monograma
   legible. Los tres umbrales salen de las guías de fundición, no de una estimación.

   Dos razones por las que va primero: **no se duplica con nada** —JewelCraft no lo hace, y
   verificado en el Blender de Leo, 5.1 ya no trae el 3D-Print Toolbox (`bpy.ops.mesh` no
   tiene ningún operador de grosor)—; y **SiroBuilder sabe qué es cada parte**, así que puede
   decir *"la pared del sello mide 0,45 mm"* en vez de tirar un heatmap genérico: conoce
   `Grosor`, `Pared` y `Marco` por nombre.

2. ⬜ **Vaciado interior de la cabeza** — el equivalente al Azure cutter de MatrixGold. Ahora
   que el peso se ve en vivo, esto lo baja y se ve bajar: en una cabeza de sello maciza es
   plata que no vuelve. Absorbe el "vaciar/cascarón" de la Fase 4.

3. ⬜ **Grabado de texto / monograma en la cara del sello** — es *para lo que existe* un anillo
   de sello. Hoy hay relieve desde imagen (`depthmap_relief`) pero no texto nativo. El de mayor
   valor de producto y el de mayor esfuerzo: hay que proyectar la tipografía sobre la cara y
   bajarla al plano del sello. Absorbe el "texto 3D de un clic" de la Fase 4. Dejarlo para
   cuando (1) esté cerrado.

Fuentes: [JewelCraft](https://github.com/mrachinskiy/jewelcraft) ·
[review con sus límites](https://www.toolworthy.ai/tool/jewelcraft) ·
[MatrixGold](https://gemvision.com/matrixgold) ·
[Azure cutters y smart prongs](https://aidi.org/matrixgold-jewelry-design-software-update/) ·
[Materialise — diseño para plata](https://www.materialise.com/en/academy/industrial/design-am/silver) ·
[i.materialise — tips de joyería](https://3dprint.com/137896/jewelry-basic-tips-i-materialise/) ·
[Roberts & Co — grabado de sellos](https://www.roberts-and-co.com/blogs/news/the-art-of-engraving-signet-rings)
