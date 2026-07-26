# Auditoría de SiroBuilder — 2026-07-25

> ## ⚠️ Revertido el 2026-07-26
>
> **Los arreglos de este informe ya NO están en el código.** A pedido de Leo se
> devolvió el addon a v0.14.0, que es exactamente el estado que se auditó (lo
> que este informe describe abajo como "estado auditado").
>
> El trabajo no se perdió: está en `git stash@{0}` y en
> `AUDITORIA_2026-07-25_arreglos.patch` (1614 líneas). Los hallazgos de abajo
> siguen siendo válidos como diagnóstico; lo que caducó son las líneas
> "**Arreglado**", que describen un código que hoy no está aplicado.
>
> Contexto completo, backups y el estado del bug del gizmo: `ESTADO_2026-07-26.md`.

Estado auditado: working tree con v0.14.0 sin commitear (22 operadores, 3081 líneas de
addon, 1053 de test). Blender 5.1.2, addon instalado por symlink al repo, todo medido
headless. Las dos suites parten en verde: `OK tools`, `OK clip_plane`.

> ## Estado: arreglados, v0.15.0
>
> Los 12 hallazgos se atacaron en la misma sesión. Cada uno lleva abajo su línea
> **Arreglado** con el número nuevo medido. Dos cosas cambiaron respecto a lo que
> decía este informe cuando se escribió, y quedan corregidas en su lugar:
>
> 1. **Los hallazgos 1 y 2 no comparten causa** (este informe decía que sí).
>    Comparten el disparador —geometría del corte coincidiendo con geometría
>    existente— pero `cut` fallaba en `bisect_plane` + `triangle_fill` y
>    `shape_cut` en el solver del boolean. Fueron dos arreglos distintos.
> 2. **El hallazgo 5 no era un defecto.** Ver su entrada: la medición lo dio
>    vuelta, y de paso destapó uno nuevo y peor, el **13**, al final — que
>    también quedó arreglado, junto con un hermano (13b) que el propio arreglo
>    del hallazgo 1 había introducido.

Regla que se siguió: un hallazgo entra acá **solo con su número medido**. Lo que no se
pudo medir está en su propia sección, aparte. Y lo que se sospechó y resultó falso
también está listado, para que nadie lo vuelva a perseguir.

---

## Veredicto

El addon está sano en lo estructural —no hay código muerto, las propiedades de escena se
registran y se dan de baja parejas, los booleans y el relleno hacen lo que prometen—
pero **tiene un patrón de falla repetido y grave: cuando la geometría del corte coincide
exactamente con geometría que ya existe en la pieza, el resultado es basura y nadie
avisa**. Pasa en el corte con plano y en el corte por forma, justo en sus posiciones por
defecto y justo sobre las piezas más comunes en joyería (esferas, toros, cualquier cosa
simétrica).

El segundo eje débil es el respeto por lo que es del usuario: dos herramientas le pisan
configuración o color sin restaurarlo.

Es el mismo patrón que tenía el relieve: **no explota, el test pasa, y la pieza queda
inservible**.

---

## Hallazgos, por gravedad

### 🔴 1. Cortar con el plano en su posición por defecto rompe las piezas simétricas

`operators/cut.py` · `_cut_mesh` / `_group_cut_loops`

`add_cut_plane` deja el plano en el centro del bounding box. En una esfera eso es
exactamente el ecuador, donde ya hay un anillo de vértices; en un toro, igual. Cuando el
plano de corte cae sobre vértices que ya existen, el tapado (`triangle_fill`) construye
caras **encima** de las que ya estaban:

| pieza | plano | aristas de borde | no-manifold | caras degeneradas |
|---|---|---|---|---|
| esfera | z=0.0 (el default) | **32** | **32** | **32** |
| esfera | z=+0.5 | 0 | 0 | 0 |
| esfera | z=+2.0 / −3.7 / +4.9 | 0 | 0 | 0 |
| toro | z=0.0 (el default) | **48** | **48** | — |

Las 32 aristas con más de dos caras confirman la causa: el tapado duplicó superficie.
La pieza queda abierta y no fusionable, y el operador termina en `FINISHED` sin una
palabra.

Reproducir: crear una esfera, `siro.add_cut_plane`, `siro.cut(side='FRONT')` y contar
`e.is_boundary` — 32. Repetir subiendo el plano 0,5 mm antes de cortar — 0.

**✅ Arreglado.** `_cut_mesh` tapa ahora **las aristas de borde que caen en el plano de
corte** —lo que quedó realmente abierto— en vez de `geom_cut` a ciegas; en un corte
normal las dos listas coinciden, así que ahí no cambia nada. Más un
`dissolve_degenerate` para las caras de área cero que deja el anillo colapsado. Medido
después: esfera por el ecuador y toro por el medio, `borde=0 nomanif=0 degen=0` y el
volumen exactamente la mitad (1055,2 de 2110,4 · 845,8 de 1691,6). Test nuevo en
`test_clip_plane.py` con **esfera y toro**, no con un cubo.

### 🔴 2. El corte por forma centrado sobre una esfera destruye la pieza

`operators/shape_cut.py` · `apply_shape_cut`

Mismo patrón, otra herramienta. Con la forma centrada, el eje del corte pasa por los
polos de la esfera —vértices existentes— y la pieza desaparece:

| forma | modo | volumen | islas | verts | no-manifold |
|---|---|---|---|---|---|
| centrada (pasa por los polos) | Recortar/Interior | 2110 → **0.0** | 6 | **12** | 6 |
| centrada | Recortar/Exterior | 2110 → 2110 | 1 | 557 | **6** |
| desplazada (esquiva el polo) | Recortar/Interior | 2110 → 285.5 | 1 | 107 | 0 |
| desplazada | Recortar/Exterior | 2110 → 1825.0 | 1 | 495 | 0 |

El caso "Exterior centrada" es el más traicionero: el volumen queda intacto, la pieza
*parece* bien, y sin embargo se llevó 6 aristas no-manifold que van a arruinar el
siguiente Fusionar.

El cortador en sí está sano (cerrado, volumen positivo) — el problema es el boolean
contra geometría coincidente, no la forma dibujada.

Reproducir: `shape_cut.apply_shape_cut(ctx, esfera, rayos, action='TRIM', keep='IN')` con
rayos verticales sobre el cuadro `(±4, ±4)` centrado, y después sobre `(1..6, 1..6)`.

**✅ Arreglado, y borrando código.** La causa era el solver `FLOAT` —no la misma que el
hallazgo 1, como decía este informe—. Medido: `MANIFOLD` es **más rápido** que FLOAT
(8,06 s contra 9,87 s sobre dos millones de caras; 0,01 s contra 0,01 s en una esfera) y
correcto donde FLOAT destruye la pieza, así que FLOAT no tenía ninguna razón de existir.
Ahora el solver se elige solo con el criterio que ya usaba `boolean_ops.py` (cerrada →
MANIFOLD, abierta → EXACT) y **se borraron** la propiedad del operador, la prop de escena
`siro_solver` y el selector "Calidad" del panel. Medido después: esfera centrada,
Interior 928,5 + Exterior 1182,0 = 2110,4, la esfera entera, ambas con `nomanif=0`.

### 🔴 3. "Alinear a la base" deja flotando cualquier pieza rotada

`operators/align_base.py:19`

Usa `obj.bound_box`, que es la **caja local** del objeto. Al rotarla, las esquinas de esa
caja caen más abajo que la malla real, así que la pieza se apoya sobre una caja
imaginaria:

| pieza | Z mínimo real tras alinear | debería ser |
|---|---|---|
| toro rotado (0.7, 0.3, 0) | **4.2968 mm** | 0.0 |
| cubo sin rotar | 0.0 | 0.0 |

4,3 mm de aire bajo una pieza que se manda a fundir. El test actual solo prueba la pieza
sin rotar, por eso nunca lo vio.

**✅ Arreglado.** Una línea: el mínimo se mide sobre los vértices reales. Medido después:
toro rotado, esfera rotada y pieza de escala no uniforme rotada, todas en `z = 0.0`; el
cubo sin rotar y el caso con modificador en vivo, sin cambio. Test nuevo con la pieza
**rotada**. `z_range` y `_encuadre` de `extrude_down.py` usan el mismo `bound_box` pero
ahí **no** rompe (el encuadre queda de más, nunca de menos): no se tocaron.

### 🔴 4. Fusionar con una pieza abierta avisa "conservadas" después de haber empeorado la pieza

`operators/boolean_ops.py:113-157`

Con el target abierto, el operador decide bien no borrar los operandos… pero **ya aplicó
el boolean sobre el target**:

| | antes | después |
|---|---|---|
| aristas de borde | 4 | 4 |
| no-manifold | **0** | **12** |

El mensaje dice *"piezas conservadas, pasa Reparar malla primero"*, que se lee como "no
hice nada". Hizo: dejó la pieza peor de lo que estaba.

**✅ Arreglado.** Con alguna malla abierta se cancela **antes** de tocar nada, con el
patrón que ya usaba `extrude_down`, y el mensaje dice que no se hizo el boolean y por
qué. Medido después: el target queda idéntico (mismos vértices, mismo no-manifold) y el
operando se conserva. Los booleans normales siguen dando 1500 en Fusionar y 500 en
Restar. Test nuevo.

---

### 🟡 5. El relleno hacia abajo deja caras degeneradas

`operators/extrude_down.py` · `_sombra`

La malla sale cerrada, pero llena de caras de área ~0 donde la grilla toca el borde de la
silueta, y escalan con la resolución:

| resolución | caras | degeneradas |
|---|---|---|
| 128 | 25 095 | 1 002 |
| 256 | — | 1 831 |
| 512 | 373 330 | 3 454 |

(esfera; el toro da 967 a resolución 256).

**❌ No era un defecto. La medición dio vuelta este hallazgo y no se arregló nada.**

Lo que este informe daba por supuesto —"degrada los booleans siguientes y la impresión"—
resultó falso al medirlo, y el arreglo propuesto era peor que el problema:

- **La sombra no las produce.** Sale con 0 degeneradas y área mínima 4,31e-3. Las caras de
  área **exactamente** cero las crea el boolean de unión, no el muestreo.
- **Un boolean posterior funciona perfecto** sobre la pieza con sus 1831 degeneradas:
  restarle un cubo da 3428,1 → 3212,1 (exacto), cerrada y con `nomanif=0`.
- **Los cuatro remedios rompen la malla.** Entra con 0 aristas no-manifold y sale con:
  `dissolve_degenerate` 1e-6 → **59**; 1e-4 → **4252**; `remove_doubles` 1e-5 → **3112**;
  los dos juntos → **3349**.

Son caras de área cero integradas en una malla cerrada y manifold: sacarlas la abre. Se
descartó el arreglo. Al medir esto apareció el hallazgo **13**, abajo.

### 🟡 6. Modo Acople te pisa la configuración de snap

`operators/snap_dock.py:20-22`

Al apagarse escribe valores fijos en vez de restaurar lo que había:

| | antes | tras encender y apagar |
|---|---|---|
| `use_snap` | True | **False** |
| `snap_elements` | {'VERTEX'} | **{'INCREMENT'}** |

Si trabajás con snap a vértices, el Modo Acople te lo borra. **Y el test consagra el
comportamiento**: `assert not ts.use_snap` (test_tools.py:281) fija justamente que apagar
el modo deje el snap apagado.

**✅ Arreglado.** Los tres valores se guardan al encender —en la escena, que es donde vive
`tool_settings` y por lo tanto sobrevive lo mismo que lo que se pisó— y se devuelven al
apagar. Medido: `(True, {'VERTEX'}, False)` → encendido `(True, {'FACE'}, True)` →
apagado `(True, {'VERTEX'}, False)`. El test que fijaba el comportamiento equivocado
ahora comprueba la restauración.

### 🟡 7. Marcar selección borra los colores de objeto que hayas puesto

`operators/select_mark.py:35-37`

`disable()` no restaura: pone **todos** los objetos mesh en blanco.

| | valor |
|---|---|
| color puesto por vos | (0.1, 0.9, 0.3) |
| con el modo encendido | (0.659, 0.29, 0.259) — esperado |
| **tras apagarlo** | **(1.0, 1.0, 1.0)** — se perdió |

**✅ Arreglado.** El color de cada objeto se anota al encender y se devuelve al apagar; el
que nació después del encendido cae en blanco, como antes. Medido: (0.1, 0.9, 0.3) →
teñido (0.659, 0.29, 0.259) → apagado **(0.1, 0.9, 0.3)**. Test nuevo.

### 🟡 8. Espejo refleja sobre el eje local, pero el botón muestra los ejes globales

`operators/mirror.py:31`

Medido sobre una C rotada 45° en Z:

| hipótesis | coincide |
|---|---|
| reflejo sobre el eje X **global** (el del gizmo) | **No** |
| reflejo sobre el eje X **local** de la pieza | **Sí** |

Las letras X/Y/Z de los botones se pintan con los colores de eje **del tema**, para que
concuerden con el gizmo del viewport — y el gizmo muestra ejes globales. Con la pieza
sin rotar da igual; con la pieza rotada, el botón promete un plano y usa otro.

**✅ Arreglado — Leo eligió el eje global**, el que promete el color del botón. La
reflexión se arma en mundo y se lleva al espacio local de la malla. Medido después: la C
rotada 45° coincide con el reflejo **global** y ya no con el local; sin rotar no cambia
nada (mismo volumen 6560,0 y mismo bounding box). Test nuevo con la pieza **rotada**.

### 🟡 9. Simplificar deforma la pieza sin avisar cuando la malla es de pocas caras

`operators/simplify.py:45`

La pérdida de forma depende de la densidad, y el aviso solo mira si bajó el conteo de
triángulos:

| malla | triángulos | volumen | pérdida de forma | qué reportó |
|---|---|---|---|---|
| cubo | 12 → 6 | 1000 → 370 | **63 %** | `Info: Triángulos: 12 → 6` |
| C de 12 caras | 28 → 14 | 6560 → 3538 | **46 %** | `Info: Triángulos: 28 → 14` |
| cubo subsurf 1 | 48 → 24 | 252 → 211 | 16 % | Info |
| cubo subsurf 2 | 192 → 96 | 306 → 295 | 3,7 % | Info |
| cubo subsurf 3 | 768 → 384 | 322 → 320 | 0,7 % | Info |
| cubo subsurf 4 | 3072 → 1536 | 326 → 326 | **0,1 %** | Info |
| esfera / toro | 512 / 576 caras | — | < 0,6 % | Info |

En mallas densas —el caso normal de una pieza importada— se porta bien. El problema es
solo abajo de unos ~200 triángulos, donde el Decimate no tiene margen y devuelve otra
cosa con cara de éxito.

**✅ Arreglado.** Compara el volumen antes y después y avisa con `WARNING` si se fue más
del 5 %, diciendo cuánto cambió y qué hacer. **Sin topes por conteo de caras**: el aviso
va sobre la deformación real. Medido después: el cubo de 12 triángulos dispara
*"Triángulos: 12 → 6, pero la pieza cambió 63% de volumen…"*, y los de 192 y 3072
triángulos siguen en `INFO`, sin ruido.

---

### ⚪ 10. "Plano de corte" es el único panel de acción sin aviso de estado vacío

`ui/panels.py:170-185`

Transformar, Corte por forma, Extrudir, Malla y Relieve avisan con `_sin_pieza`. Plano de
corte no: sin pieza activa el botón queda gris y el panel parece roto — el mismo síntoma
que costó una sesión con el corte por forma.

**✅ Arreglado.** Mismo patrón que `SIRO_PT_extrude`: avisa si no hay pieza activa **ni**
plano puesto (con el plano en escena la sección sigue funcionando aunque no haya
selección).

### ⚪ 11. La clave de grupo queda colgada tras fusionar

`operators/group.py`

Al fusionar dos piezas agrupadas, el resultado conserva `siro_group = 1`: queda
"agrupado" con una pieza que ya no existe. Inofensivo hoy, pero es estado fantasma.

**✅ Arreglado.** Tras el boolean, si no queda ninguna otra pieza con ese grupo, la clave
se borra del resultado.

### ⚪ 12. El README afirma algo que no es exacto

`README.md`, entrada v0.13.0: *"**todos** los botones de acción pasan por `_boton`"*. No
lo hacen `siro.cut` (`panels.py:179`), `siro.group`, `siro.ungroup` ni los toggles. En
los toggles da igual (no tienen propiedades) y en `siro.cut` es defendible —abre un
diálogo donde ves los valores—, pero la frase del README es falsa tal como está escrita.

**✅ Arreglado.** El README dice ahora qué queda fuera y por qué. El código no se tocó: el
comportamiento estaba bien, lo que mentía era la frase.

---

## 🔴 13. Hallazgo NUEVO — "Reparar malla" rompe las piezas rellenadas

`operators/repair.py` · `_pasada`

**No estaba en la auditoría** (nunca se corrió `repair` sobre una pieza salida del
relleno). Apareció al medir el hallazgo 5, y es más grave que varios de los doce:

| pieza | degeneradas | aristas no-manifold |
|---|---|---|
| esfera rellenada (sana) | 1831 | **0** |
| la misma, tras Reparar malla | 0 | **3342** |

Reparar malla convierte una pieza **cerrada y correcta** en una con 3342 aristas
no-manifold. Es especialmente serio porque es la herramienta a la que el addon manda al
usuario cuando algo está abierto.

Etapas aisladas, cada una sobre la pieza sana:

| etapa de `_pasada` | degeneradas | no-manifold |
|---|---|---|
| `delete_loose` | 1831 → 1831 | 0 → 0 |
| **`dissolve_degenerate`** | 1831 → 0 | 0 → **4252** |
| **`remove_doubles`** | 1831 → 0 | 0 → **9676** |
| `select_interior_faces` + delete | 1831 → 1831 | 0 → 0 |

Las dos culpables son las mismas operaciones que el hallazgo 5 probó que no sirven para
esto: sobre caras de área cero integradas en una malla cerrada, abren la superficie. El
daño son **agujeros, no pellizcos**: `dissolve_degenerate` borra 7588 caras y deja 4183
aristas de borde; el `fill_holes` posterior alcanza a tapar algunas y quedan 3064.

**✅ Arreglado, en dos capas** (`operators/repair.py`):

1. **Una malla ya cerrada no se toca.** Si llega con `no_manifold == 0` no hay nada que
   reparar: informa "imprimible ✓" y sale. Medido: la esfera rellenada sana pasa de
   quedar con 3064 aristas de borde tras 23,5 s, a salir intacta en **0,2 s**.
2. **Reparar no puede devolver la pieza peor de lo que llegó.** Se guarda la malla antes
   de las pasadas —gratis, Blender lo hace por copy-on-write: 0,000 s medido sobre
   373 000 caras— y si el recuento de aristas no-manifold sube, se restaura y se avisa.
   Verificado sobre una pieza rellenada **con** un defecto real: reparar habría dejado
   3205 aristas no-manifold, se deshizo el cambio y la pieza quedó como estaba.

La capa 2 tiene un precio honesto: una pieza rellenada **con** un agujero real no se
puede reparar hoy — se prefiere devolverla como llegó antes que destrozarla, y el mensaje
lo dice. Repararlas de verdad pide una pasada que no use soldado ni disolución, y eso es
trabajo aparte.

### 13b. El hermano que apareció al arreglar el hallazgo 1

El arreglo del hallazgo 1 había agregado un `dissolve_degenerate` **sobre toda la malla**
en `cut.py`, que es exactamente el patrón que rompe a `repair`. Cortar una pieza
rellenada la abría: **21 aristas de borde y 60 no-manifold**. Aislado cambiando una sola
variable (con la línea: 21/60; sin ella: 0/0).

**✅ Arreglado**: la limpieza se acota a las aristas **del plano de corte** —las que el
propio corte colapsa—, nunca a toda la malla. Verificado que las dos cosas se sostienen a
la vez: esfera y toro por su centro siguen en `degen=0`, y la pieza rellenada cortada da
`borde=0 nomanif=0`. Con su test.

## Sospechas por lectura, descartadas con medición

Ninguna de estas es un problema. Van anotadas para que no se vuelvan a perseguir:

- **`align_base` ignoraría los modificadores en vivo** → falso: con un Solidify activo el
  Z mínimo evaluado da 0.0. `bound_box` sí refleja el objeto evaluado.
- **El handler `_sync_selection` se duplica y sobrevive al `unregister()`** → falso. En
  entorno limpio (`--factory-startup`, addon instalado desactivado): un register deja 1,
  dos registers dejan 1, unregister deja 0. Lo que vi era artefacto de tener dos
  instancias del módulo cargadas a la vez.
- **`bake_depthmap` fallaría con escala no uniforme u origen descentrado** → falso: el
  relieve sale plano porque esas piezas son cubos y un cubo visto desde arriba no tiene
  profundidad. Con esfera da 7,99 mm sobre radio 8, y con la pieza rotada 7,93 mm.
- **Propiedades de escena huérfanas** → falso: 9 registradas, 0 tras `unregister()`.
- **`prep_depthmap` con una imagen sin silueta** → correcto: cancela con
  *"La silueta quedó vacía: baja la Tolerancia de fondo"*.
- **`group`/`ungroup` no hacen nada** → falso; mi primera prueba miraba `parent` y el
  addon no usa parenting sino una clave custom más un handler. Medido bien: la clave se
  pone en ambas piezas, el handler está registrado, y al seleccionar una se selecciona la
  otra.
- **`shape_cut` sobre un toro deja la malla vacía** → falso: mi cuadro de prueba caía
  entero dentro del agujero del toro, así que no había nada que recortar.
- **Código muerto** → no hay. Ni una función, ni una constante sin usar en las 3081
  líneas.

---

## Qué fija realmente cada test

| operador | qué está cubierto | qué queda afuera |
|---|---|---|
| `cut` | corte de un **cubo** por z=0.5, manifold, lado correcto | **plano sobre geometría existente** (hallazgo 1) |
| `shape_cut` | el cortador (ortográfica, perspectiva, lazo cóncavo, vacío); recorte de un **cubo** | **esfera / forma centrada** (hallazgo 2) |
| `extrude_down` | rotada, plano fuera de pieza, malla abierta, escalón, caso pesado, volumen ±5 % | **caras degeneradas** (hallazgo 5) |
| `boolean` | multiusuario, 3 piezas, pieza abierta conservada, relieve vivo | **que el target no se degrade** (hallazgo 4) |
| `repair` | agujeros, pared interior, pellizcos del cráneo | — (bien cubierto) |
| `simplify` | que baje el conteo de triángulos, ngons | **pérdida de forma** (hallazgo 9) |
| `mirror` | refleja en su lugar, no duplica, volumen > 0 | **sobre qué eje, con la pieza rotada** (hallazgo 8) |
| `align_base` | Z mínimo = 0 **sin rotar** | **con rotación** (hallazgo 3) |
| `apply_relief` | cerrada, altura, base plana, grosor, volumen positivo | — (endurecido hoy) |
| `prep_depthmap` / `bake_depthmap` | alpha, invertir, Non-Color, no compone, 15 mm reales | — |
| `snap_dock` | el toggle enciende y apaga | **fija el comportamiento equivocado** (hallazgo 6) |
| `group` / `ungroup` | clave compartida, selección sincronizada, borrado | clave colgada tras fusionar (11) |
| `select_mark` | **nada** | todo (hallazgo 7) |
| `cam_mode` | **nada** | todo |
| `scene_mm` | **nada** | todo |
| `toggle_dims` | **nada** | todo |

El patrón: **casi todos los tests de corte usan un cubo**, y el cubo es la única pieza
que no dispara el bug de geometría coincidente.

---

## Qué borrar

Nada. Se buscó función por función y constante por constante con los usos verificados por
grep: no hay código muerto, no hay abstracciones con una sola implementación de más, y la
duplicación entre `cut.py`, `shape_cut.py` y `extrude_down.py` es la que ya está factorizada
en `boolean_ops.py`. La pasada de v0.13.0 —donde se borró `free_cut.py` entero— dejó el
repo limpio en este eje.

---

## Lo que necesita tu ojo en Blender abierto

1. **Marcar selección al cerrar Blender o desactivar el addon:** `unregister()` llama a
   `select_mark.disable()` sin contexto, así que el `shading.color_type` del viewport
   queda en `'OBJECT'` y no vuelve a `'MATERIAL'`. Headless no tiene viewport para
   confirmarlo — mirá si al desactivar el addon con el modo encendido te queda la escena
   en blanco.
2. **Hallazgo 8 (espejo):** decidí vos si querés espejo sobre el eje global o sobre el eje
   propio de la pieza. La medición dice cuál hace hoy; cuál querés es tuyo.
3. **Los avisos de los hallazgos 1, 2 y 4** conviene verlos en el panel real: son mensajes
   que hoy no existen o que dicen lo contrario de lo que pasó.
