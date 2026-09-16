# Rediseño del tablero — Plan 4, T4.7

**Fecha:** 2026-09-01 · **Rama:** `feat/rediseno-panel` · **Criterios:** CE3 (cero
colores literales fuera de tokens), CE8 (todo interactivo alcanzable por teclado), CE11
(jerarquía real), sin regresión de CE4/CE6/CE7/CE12.

---

## 1. Los cinco puntos de la tarea

### 1.1 Jerarquía: las ocho tarjetas dejan de pesar igual

El ADR lo dejó escrito como la señal de que el rediseño no se había aplicado: *«si al
terminar el dashboard las 8 tarjetas siguen pesando igual, la dirección no se aplicó»*.
Pesaban igual: mismo tamaño de cifra, mismo alto, mismo peso visual. Ocho cosas igual de
importantes es lo mismo que ninguna importante.

Ahora son dos filas. Arriba, los tres números que contestan «cómo va la operación», con
**Aprobados** como cifra dominante a `--texto-3xl`. Abajo, el desglose por resultado, que
se consulta pero no se vigila.

`SUPUESTO: que Aprobados es lo que el owner mira primero.` Se deduce de la operación
—llamar para conseguir clientes—, pero no lo ha dicho nadie. Cambiarlo es mover una
tarjeta de un grupo al otro.

### 1.2 Las tablas son el trabajo

- **Encabezado fijo** (`position:sticky`) dentro de un área desplazable: con 50 filas por
  página, a media tabla ya no se sabía qué columna se estaba mirando.
- **Orden en un `<button>`** con `aria-sort` en el `<th>`, alcanzable con Tab y operable
  con Enter. Antes era un `onclick` sobre el `<th>`, que no recibe foco.
- **Paginación** que dice «Página N de M», con `aria-current` y `aria-label` por botón.

### 1.3 Las gráficas, dentro del sistema

Colores de `tokens.css`, ejes y leyendas con el gris que sí pasa AA (Chart.js usa por
defecto uno que no llega), y **color semántico por etiqueta**.

Esto último no era cosmético. La gráfica de resultados usaba una paleta **posicional**
sobre `Object.keys(res)` —el orden en que la hoja devuelve las claves—, así que bastaba
con que Google las reordenara para pintar APROBADO de rojo y NEGADO de verde. Ahora el
color sale de la etiqueta.

### 1.4 Navegación alcanzable

Los 12 `div class="nav-item" onclick="showSection(…)"` pasan a `<button data-seccion>`
dentro de un `<nav aria-label>`, con listener delegado y `aria-current="page"` en la
activa. Un `div` no entra en el orden de tabulación, no responde a Enter ni a Espacio y
no se anuncia como control: **toda la navegación del panel estaba fuera del alcance de
quien no usa ratón** (SC 2.1.1).

Los dos accesos de Herramientas pasan a `<a rel="noopener">` —son enlaces de verdad— con
aviso de que abren pestaña nueva.

De paso, `showSection` deja de leer `event.currentTarget`: dependía de que se la llamara
siempre desde un manejador de evento, y adivinaba el botón activo comparando trozos del
título con el texto del menú.

### 1.5 La insignia de caché dice la verdad

Decía «Actualizado 10:17» con la hora del **navegador**, o sea cuando llegó la respuesta.
Pero el panel sirve de una caché de 5 minutos: con la caché caliente el dato podía tener
4 minutos y la insignia afirmaba que era de ahora mismo.

`app.py` expone ahora `edad_de_cache()` y la insignia dice la edad real, más una
explicación de de dónde sale el dato y de que «Actualizar» fuerza una lectura nueva.

---

## 2. CE3 llega a cero

Los 31 colores literales que quedaban vivían todos en `dashboard.js` y eran **dos paletas
de datos**: las series de Chart.js y el color de fila del operador en Seguimiento. Una
gráfica necesita una cadena de color y no puede consumir `var()` — esa era la excusa con
la que se quedaron.

Se resuelve declarándolas en `tokens.css` y leyéndolas con `getComputedStyle`. Las claves
del color de fila (`'yellow'`, `'red'`…) **no** se renombran: están guardadas en el
`localStorage` del operador y cambiarlas le borraría todas las marcas que tenga puestas.

**Resultado: 0 colores literales fuera de `tokens.css` en todo el proyecto** — CSS, JS y
plantillas.

---

## 3. Un fallo grave, preexistente, que encontró el gate

Al comparar el orden de las filas antes y después de ordenar, salían **iguales**. La
causa no era el orden: la tabla tenía **7 encabezados y 8 celdas**.

`editTh` era condicional (`isEditable ? th : ''`) y `editTd` no: emitía siempre un `<td>`.
Toda tabla **no** editable salía con una celda de más, así que **cada valor aparecía una
columna a la derecha de su encabezado**: el teléfono bajo «CIUDAD», la ciudad bajo
«TIENDA», y la primera columna vacía. Ocho de las once tablas del panel.

Confirmado contra los respaldos de la T4.5 y de la T4.7: **es de antes y no lo introdujo
esta tarea**. Corregido, con test de regresión comprobado en las dos direcciones.

Que apareciera aquí no es casualidad: es lo que el gate de la T4.7 pide literalmente
—«las once tablas funcionan»— y no se puede comprobar leyendo código.

---

## 4. Lo que encontraron los dos gates

`code-reviewer`: 1 CRITICAL, 1 MEDIUM. `a11y-architect`: 1 CRITICAL, 2 HIGH, 2 MEDIUM.

### 4.1 CRITICAL — dos `</div>` de más rompían el árbol del documento

**Mío, introducido en esta tarea.** Al reestructurar el esqueleto de las tarjetas en dos
filas, el corte dejó cierres desbalanceados. Consecuencia medida en Chromium:

- **11 de las 12 secciones colgaban de `<body>`** en vez de `#content`;
- las tres gráficas del tablero quedaban fuera de su sección, así que **no se ocultaban
  nunca** al cambiar de pantalla.

Lo peor no es el `</div>`: es que **mi propia verificación en navegador lo dio por
bueno**. Comprobaba la clase `.section.active`, que seguía siendo correcta — la clase
estaba bien y el árbol no. `tools/verificar_tablero.py` mira ahora el anidamiento real y
la visibilidad efectiva (`offsetParent`), y con el `</div>` reintroducido a propósito se
pone en rojo en tres comprobaciones.

### 4.2 CRITICAL — el anillo de foco se recortaba contra el encabezado fijo

El anillo de `base.css` se dibuja hacia **afuera** (`outline-offset:2px` más un
`box-shadow` de 2px). El botón de orden vive en un `<th>` pegado con `sticky` al borde
mismo del contenedor con `overflow`, así que el anillo claro **se recortaba siempre**, ya
en el primer render. El que sobrevivía era el oscuro, que sobre el azul del encabezado da
**2.36:1** — por debajo del 3:1 que WCAG 1.4.11 pide para un indicador de foco.

Corregido con un anillo enteramente `inset`, más `scroll-padding-top` en el contenedor
para que al enfocar una fila desplazada el encabezado opaco no la tape (SC 2.4.11).

### 4.3 HIGH — la explicación de la insignia solo vivía en `title`

`title` no es alcanzable por teclado, no existe en pantalla táctil y los lectores no lo
anuncian de forma fiable. La explicación pasa a un nodo `solo-lectores` dentro de la
propia insignia, siempre presente en el árbol de accesibilidad. El `title` se conserva
porque para quien usa ratón sigue siendo cómodo.

### 4.4 HIGH — el `role="status"` dentro del botón lo contaminaba

La insignia de envíos con problema era un `role="status"` con `aria-label` **dentro** del
botón «Envíos Catálogo». Dos efectos: el nombre accesible del botón pasaba a leerse
«Envíos Catálogo 3 envíos con problema» cada vez que se tabula ahí, y —al usarse su
contenido para calcular ese nombre— varios motores dejan de exponerlo como región viva,
que es justo para lo que estaba.

Separadas las dos funciones: la insignia queda decorativa (`aria-hidden`), el nombre
completo va en el `aria-label` del botón, y el anuncio vive en una región propia fuera
del menú.

### 4.5 MEDIUM — la franja de la tarjeta dominante tampoco ganaba

`.card--principal{border-left-width:5px}` tiene la misma especificidad que `.card{…
border-left:4px …}`, declarada después. **Es el mismo defecto de cascada que el
comentario de dos líneas más arriba dice haber corregido para `.value`** — lo corregí
ahí y no lo repliqué aquí. Lo encontró `code-reviewer` midiendo `borderLeftWidth` en un
navegador real.

### 4.6 MEDIUM — no empeorar el reflow

Había subido el mínimo de columna de la fila de KPI de 160 px a 220 px. La barra lateral
sigue siendo `fixed` de 230 px sin media query (responsive es **T4.10**), así que a 400 %
de zoom eso pedía 60 px más de ancho justo en la franja que debe verse primero. Revertido
a 160 px: la jerarquía la da el **tamaño de la cifra**, no el ancho de la columna.

### 4.7 Y uno que vi yo en una captura

La cifra dominante **no dominaba**. `.card .value` se declara más abajo en la hoja y, con
la misma especificidad, ganaba la última. El tamaño renderizado se mide ahora en el
navegador, no se deduce de la regla CSS.

### 4.8 Lo que los gates descartaron

- **`aria-sort` está bien en el `<th>`**, no en el botón: es propiedad del encabezado de
  columna, no del control que lo activa (patrón WAI-ARIA APG). Se añadió `scope="col"`
  explícito por la `<th>` extra de acciones.
- **El aviso de «se abre en una pestaña nueva»** dentro del enlace es el patrón correcto
  (técnica G201).
- **Contraste de la barra lateral**: el texto no activo, con `opacity:.85` sobre el
  degradado azul, da **5.87:1** en el extremo peor. Pasa AA con margen, calculado.
- **El listener delegado** no colisiona con el del orden de tabla ni con el del
  importador (páginas distintas).
- **`getComputedStyle` resuelve `var()` encadenado**: `--dato-aprobado: var(--exito-vivo)`
  devuelve el hex, no la cadena literal. Verificado en Chromium.

---

## 5. Verificación

| Qué | Resultado |
|---|---|
| Suite completa | **740 passed, 1 skipped** (baseline previo 690; +50 de la T4.7) |
| CE3 · colores literales | 31 → **0 en todo el proyecto** |
| Navegador · tablero | **24/24** (`tools/verificar_tablero.py`) |
| Navegador · estados y movimiento | 5/5 y 13/13, sin regresión |
| CE4 · CLS | 9/9 por debajo de 0.1 |
| Las 11 tablas | Orden, filtro y paginación, con ratón **y** con teclado |

Comprobado **en las dos direcciones**: con el `</div>` de más reintroducido sobre una
copia, la verificación se pone en rojo en tres comprobaciones; con la corrección del
`editTd` revertida, el test de alineación de columnas también.

---

## 6. Lo que esta tarea NO hace

- **No hace responsive el panel.** La barra lateral sigue siendo `fixed` de 230 px sin
  media query, y a 320 px deja menos de 90 px de contenido. Es **T4.10**, y esta tarea se
  cuidó de no empeorarlo.
- **No añade texto alternativo a las gráficas.** T4.10.
- **No toca el formulario ni el importador.** T4.8 y T4.9.
- **No pone SRI a Chart.js.** Deuda del Plan 5.

El respaldo previo al cambio está en `docs/auditoria/respaldos/2026-09-01/t47-antes/`
(5 archivos).
