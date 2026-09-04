# Rediseño del importador — Plan 4, T4.9

**Fecha:** 2026-09-02 · **Rama:** `feat/rediseno-panel` · **Registro del ADR:** «narrativo» —
es una operación larga que gasta dinero, así que la pantalla cuenta el avance de la corrida.

Es la superficie donde convergen los cuatro planes: los contadores del Plan 3, el medidor de
gasto del Plan 2, el catálogo nacional del Plan 1 y el sistema de diseño de las T4.4–T4.6.
Esta tarea no rehace nada de eso. Le da forma.

---

## 1. El resultado medible

Todo lo de esta tabla está medido en navegador, con el mismo protocolo antes y después:
misma máquina, mismo Chromium, catálogo completo de 606 municipios, una pasada de
calentamiento y 7 repeticiones. El «antes» se sirvió copiando el respaldo de
`docs/auditoria/respaldos/2026-09-02/t49-antes/` sobre los archivos vivos, y restaurando
después (verificado por hash, no por confianza). Ese respaldo **no está versionado** —
`.gitignore` cubre `docs/auditoria/respaldos/` a propósito—, así que quien quiera repetir la
medición parte de `git show 7067fb5:static/js/importador.js`, que es el mismo contenido.

| | Antes | Después |
|---|---:|---:|
| Coste de **una pulsación** del buscador (peor caso) | **713.5 ms** | **3.1 ms** |
| Coste de una pulsación (mediana, filtro `a` → 525 chips) | 18.0 ms | 1.6 ms |
| Chips alcanzables con teclado | **0 de 606** | 606, con **1** parada de tabulación |
| Agrupación por macro-región en la lista | 0 grupos | 8 grupos con conteo en vivo |
| Tamaño del número principal frente a los secundarios | 38.4 px / 28.8 px (**1.33×**) | 56 px / 28 px (**2.0×**) |
| Chips que se salían de su caja a 320 px | **50 de 607** | **0** |
| Diálogos del navegador que bloquean la página | 4 `alert()` + 1 `confirm()` | **0** |
| Estados terminales distinguibles a simple vista | 1 de 4 (sólo cambiaba el emoji) | 4 de 4 |
| CLS del importador (320 / 768 / 1440 px) | 0.0030 / 0.0193 / 0.0096 | 0.0000 / 0.0145 / 0.0048 |

Las 713.5 ms no son una anomalía inventada para lucir la mejora: son el peor caso de siete
repeticiones sobre el filtro que más chips deja visibles (525 de 607). La mediana de ese
mismo caso era de 18.0 ms, o sea que **ya se salía del presupuesto de un fotograma (16.7 ms)
en la mitad de las pulsaciones**, y de vez en cuando se iba a casi tres cuartos de segundo.

---

## 2. Lo que estaba roto

### 2.1 Filtrar reconstruía los 606 chips

`filtrarCiudades()` llamaba a `renderChips()`, que rehacía el `innerHTML` entero de la lista.
Cada tecla del buscador destruía 606 nodos y volvía a generar y parsear ~50 KB de marcado.

Ahora los chips se construyen **una vez** y el filtro sólo escribe `hidden` —y sólo en los
que cambian, porque asignarlo a los 606 invalida el estilo de todos aunque el valor sea el
mismo—. El texto buscable se pasa a minúsculas al construir, no en cada tecla.

El arnés no lo comprueba por el reloj, que es ruidoso, sino por identidad de nodo: guarda
una referencia al primer chip y verifica que **sigue siendo el mismo objeto** después de
filtrar. Si alguien vuelve a reconstruir, el reloj podría disimularlo en una máquina rápida;
la referencia, no.

### 2.2 Ni un chip era alcanzable con teclado

Eran 606 `<span>` con un listener de clic delegado: sin `role`, sin `tabindex` y sin un solo
manejador de teclado. Para un operador que no use ratón, el catálogo nacional entero —el
trabajo completo del Plan 1— era invisible.

Ahora es un `listbox` de verdad: un `role="group"` por macro-región, `role="option"` por
ciudad, `aria-selected`, y **tabindex móvil**, que es lo que evita el otro extremo —606
paradas de tabulación serían peor que ninguna, porque habría que atravesarlas todas para
llegar al botón Buscar—. Flechas, `Home` y `End` recorren **sólo lo visible**: saltan lo que
el filtro ocultó. Al filtrar, la parada de tabulación se recoloca sola; si no, se quedaría
en un chip oculto y el teclado no entraría a la lista.

### 2.3 Los cuatro finales se veían iguales

`done`, `cancelado`, `presupuesto_agotado` y `error` compartían caja, fondo y color de
título. Lo único que cambiaba era el emoji, y eso sólo desde la T4.5.

Detener a mano no es un fallo: es una decisión del operador. Quedarse sin presupuesto
tampoco: es el tope del Plan 2 haciendo exactamente su trabajo. Pero ninguno de los dos
completó, así que tampoco se visten de verde. Cuatro bandas, cuatro títulos, cuatro fondos
distintos —comprobado por test, no a ojo— y `role="alert"` reservado al único que de verdad
interrumpe.

### 2.4 Cuatro `alert()` y un `confirm()`

Bloquean la página, roban el foco y al aceptarlos no dejan rastro de lo que dijeron. Es la
misma clase que la T4.8 cerró en el formulario.

- Ciudad vacía → mensaje junto al campo, `aria-invalid`, `role="alert"` y el foco de vuelta
  donde hay que escribir.
- Fallo al iniciar → estado de error del sistema **con reintento**.
- «¿Detener la búsqueda?» → confirmación **en la página**, con el estado de la corrida
  delante, que es justo lo que hay que poder leer para decidir.

### 2.5 El registro se reescribía entero en cada sondeo

`logEl.innerHTML = ...` cada tres segundos: parpadeo, animación de entrada reiniciada en
todas las líneas, y `scrollTop = scrollHeight` incondicional, que arrastraba al final a quien
estuviera leyendo más arriba.

Ahora se añaden **sólo las líneas nuevas**. El backend manda las diez últimas, así que la
ventana se desplaza: se busca cuánto del bloque anterior sigue al principio del nuevo y se
añade el resto. Y el scroll sólo sigue al final si el operador ya estaba al final.

---

## 3. Lo que la tarea pedía, punto por punto

| Lo que pide el plan | Cómo quedó |
|---|---|
| 1. Jerarquía de los cuatro contadores | `nuevos_en_sheet` ocupa la fila entera con `--texto-3xl` (56 px); los otros tres, 28 px en una rejilla de tres. Usa `.stat--principal`, el componente que la T4.4 escribió **para esta pantalla** y que nadie había usado todavía |
| 2. Agrupación, contador por grupo y buscador instantáneo | 8 grupos por macro-región con cabecera adherida y conteo que pasa a «12 de 87» al filtrar; el grupo sin coincidencias se retira entero, cabecera incluida. El `<select>` de regiones se conserva: es nativo, accesible y compacto, y sustituirlo por nueve chips habría gastado dos filas de una tarjeta que ya aprieta a 320 px |
| 3. La consola dentro del sistema | Adopta `.consola` de `componentes.css`: pila monoespaciada **declarada** (antes decía `monospace` a secas, a merced del navegador), encabezado propio y `tabindex="0"`, porque una caja con scroll tiene que poder recorrerse con teclado |
| 4. Etiqueta de fase junto al progreso | `#prog-fase` es una insignia al lado del porcentaje, y cambia de tono según el estado. La línea de abajo dice ciudad y categoría, que antes se perdían porque el mismo hueco servía para la fase y para los mensajes de error |
| 5. Cancelación y tope como estados de primera clase | §2.3 |

**El orden de los grupos sale del orden de llegada, no del alfabeto.** El catálogo llega
ordenado por prioridad (Plan 1), así que la región que contiene la ciudad número 1 del país
va primera, y dentro de cada grupo se conserva el mismo orden. Agrupar por nombre habría
destruido el ranking que el Plan 1 construyó; agrupar por orden de llegada lo **indexa**.
Hay un test que lo fija, porque es la clase de decisión que se deshace sin querer.

---

## 4. Lo que encontraron los gates

Tres revisiones en paralelo. **`code-reviewer`: APPROVE** (0 CRITICAL, 0 HIGH, 1 MEDIUM,
2 LOW). **`security-reviewer`: 0 CRITICAL, 0 HIGH**, 1 observación LOW. **`a11y-architect`:
1 CRITICAL, 2 HIGH, 7 MEDIUM, 2 LOW** — y el CRITICAL no lo vio ninguno de los otros dos,
que es la razón por la que los dos gates van siempre juntos.

### 4.1 CRITICAL — el contraste roto por una opacidad, que ningún guarda mide

```css
.chip-ciudad .pct--crudo { opacity: .55; }   /* --texto sobre blanco -> 2.97:1 */
```

Es el badge que ven **la mayoría de las 606 ciudades** (el conteo crudo de ferreterías, que
se muestra cuando el porcentaje de interés es 0). Y el detalle que lo hace interesante: el
color declarado **sí es un token**, así que el guarda de CE3 lo da por bueno; lo que rompe el
contraste es la opacidad, que ningún test de tokens mide. Corregido usando `--texto-suave`,
que ya está medido a 4.76:1, y con test propio.

### 4.2 HIGH — un diálogo modal que no era modal

La confirmación de «Detener» se anunciaba con `role="alertdialog"`. Ese rol es, por
definición, modal: exige `aria-modal`, trampa de foco y el resto de la página inerte. No
había ninguna de las tres **a propósito** —el ADR descarta el bloqueo del `confirm()`—, así
que el rol le decía al lector de pantalla algo que era falso. Ahora es `role="group"` con
`aria-labelledby` y `aria-describedby`: lo que de verdad es, un aviso en línea.

### 4.3 HIGH — el foco caía a `<body>` al confirmar

La rama «Seguir buscando» devolvía el foco; la rama «Sí, detener» no. `cerrarConfirmacionDetener()`
destruye el botón que en ese momento tenía el foco. Ahora se lleva al registro de la corrida,
que es donde va a aparecer la respuesta («Cancelación pedida; terminando el paso en curso…»).

De paso, el foco por defecto pasó del botón destructivo al seguro: el operador viene de
pulsar un botón, y un Enter reflejo cancelaba la corrida sin haber leído la pregunta.

### 4.4 MEDIUM — lo que se anunciaba de más y lo que no se anunciaba

- **El resumen de chips interrumpía una vez por letra tecleada.** `filtrarCiudades` corre en
  el `oninput` del buscador, así que la región viva se disparaba con cada pulsación, encima
  del eco de la propia tecla. Ahora el texto visible se actualiza al instante y el anuncio va
  por una región aparte, con 600 ms de retardo.
- **El registro no se anunciaba nunca.** `role="region"` es un *landmark*, no implica región
  viva: las líneas que llegan cada 3–10 s no llegaban a un lector de pantalla. Pasa a
  `role="log"`, cuya cadencia sí es baja.
- **Los dos avisos del catálogo** —contactos sin clasificar y «no pude leer el catálogo»—
  se saltan `Estados.*` y no llevaban rol: `status` el informativo, `alert` el que bloquea la
  elección por chip.
- **El estado de cada categoría vivía solo en el color de fondo.** Ahora también en texto
  (`.solo-lectores`) y en `aria-current="step"`.
- **Dos pares de contraste al filo**: `--texto-suave` sobre `--superficie-2` da 4.55:1, que
  pasa AA por dos centésimas. Es el mismo caso que `componentes.css` ya documenta para
  `.estado--vacio`; se sustituye por `--gris-600` en los dos sitios nuevos.
- **El borde del chip destacado** usaba `--exito-vivo` contra `--exito-tinte`: 2.1:1, por
  debajo del 3:1 de WCAG 1.4.11. Aquí el borde de color **sustituye** al del control, así que
  no aplica la excepción de «franja decorativa» que sí vale para `.stat--exito`.
- **El foco se perdía al reintentar** la carga del catálogo: `renderChips` destruye el botón
  «Reintentar» que lo tenía. Mismo patrón que 4.3, mismo arreglo.

### 4.5 MEDIUM de `code-reviewer` y las dos LOW

El MEDIUM señalaba que el chip elegido conserva `aria-selected` aunque el filtro lo oculte.
Revisándolo, el estado sí era veraz mientras el campo mantuviera esa ciudad —el operador la
eligió y sigue ahí—; **lo que no era veraz** es lo que pasaba al escribir otra ciudad a mano:
el chip anterior seguía marcado afirmando algo ya falso. Eso es lo que se arregló: la marca
sigue al campo.

Las dos LOW se aplicaron tal cual: el medidor de gasto ya no hereda los números de la corrida
anterior, y «Deteniendo…» ya no parpadea (el worker mira la bandera *entre* pasos, así que el
siguiente sondeo seguía reportando la fase real de Places).

La LOW de seguridad —`pedirDetener` arma HTML a mano y hoy no interpola nada externo— queda
anotada **en el propio código**, que es donde la va a leer quien añada mañana un mensaje
dinámico.

### 4.6 Y un fallo que no encontró ningún gate: un byte NUL en el fuente

Buscando otra cosa, `grep` dijo `Binary file static/js/importador.js matches`. El separador
que usa el registro para comparar ventanas se había escrito como **byte NUL crudo** en vez
del escape ` `. Funcionaba —y ese era el problema—: `grep` trata como binario cualquier
archivo con bytes raros y **suprime las coincidencias sin avisar de forma evidente**, que es
exactamente el fallo de barrido que el CLAUDE.md del entorno documenta. Un secreto en ese
archivo habría sido invisible para `tools/barrer_secretos.py`.

Corregido, y con un guarda que barre `.js`, `.css`, `.html`, `.py` y `.md` de las cinco
carpetas de fuente buscando bytes NUL, más su control negativo.

Al arreglarlo apareció el segundo: un `read_bytes().decode()` seguido de `write_text()`
convirtió los **871** finales de línea del archivo en `


`. Normalizado a CRLF y
verificado byte a byte, no de vista.

---

## 5. Verificación

| Qué | Resultado |
|---|---|
| Suite completa | **850 passed, 1 skipped** (baseline de la rama: 781 + 69 nuevos) |
| `tools/verificar_importador.py` (nuevo) | **45/45 en verde** |
| El mismo arnés contra el código anterior | **34 de 45 en rojo** — comprobado en las dos direcciones |
| `tests/test_plan4_importador.py` contra el código anterior | **59 de 69 en rojo** |
| `verificar_estados` · `verificar_movimiento` · `verificar_tablero` · `verificar_formulario` | 5/5 · 13/13 · 24/24 · 12/12, sin regresión |
| `medir_cls.py` | 9/9 por debajo de 0.1; peor caso 0.0373 (tablero a 768 px, sin tocar) |
| `barrer_secretos.py` sobre el diff | 0 hallazgos — y el barrido se probó **contra un positivo conocido**, que sí detecta |

Capturas en `docs/diseno/2026-09-02-importador-t49/`: reposo a 320/768/1440 px, el filtro
agrupado, la corrida en marcha y los cuatro finales. Se generan con
`tools/capturar_importador.py`, que sirve el catálogo versionado del INEGI y contadores
inventados: **ninguna captura lleva un dato de cliente**.

### 5.1 Dos guardas que hubo que arreglar, no relajar

1. `test_el_css_escala_en_vez_de_ensanchar` buscaba `\.progress-fill\{` **pegado**. Al dejar
   de escribir el CSS minificado, el patrón dejaba de encontrar la regla: el guarda se
   apagaba solo al reformatear el archivo, sin avisar. Ahora tolera el espacio y exige
   `transition: transform`; comprobado con un control negativo que reintroduce
   `transition: width` y lo pone en rojo.
2. `tools/verificar_movimiento.py` mostraba el panel con `caja.style.display = 'block'`. Los
   paneles ahora se ocultan con `hidden`, que `base.css` declara `display:none !important`,
   así que el estilo en línea ya no los muestra. Se cambió por la misma vía que usa el panel
   de verdad, `mostrarPaneles()`.

Y dos guardas nuevos se dispararon con **su propia documentación** —el comentario que explica
por qué se retiró `querySelectorAll` de `elegirChip`, y el que explica dónde no se llama a
`toLowerCase`—. Es la sexta y la séptima vez en esta tanda; están acotados quitando
comentarios antes de afirmar «no queda ninguno».

---

## 6. Lo que esta tarea NO hace

- **No arregla el responsive del panel entero.** Es T4.10. Lo que sí hace es no empeorarlo y
  cerrar el desborde de esta superficie: los 50 chips que se salían de su caja a 320 px eran
  el defecto concreto que el traspaso anotaba como «el importador desborda en horizontal».
  Medido: el *documento* nunca desbordaba —la caja de chips tiene scroll propio—, así que lo
  roto era el contenido dentro de la caja, no la página.
- **No consolida los componentes paralelos de las otras dos superficies.** El importador ya
  usa `.stat` y `.consola` del sistema; `.btn-green` del formulario sigue siendo suyo. T4.10.
- **No trocea `importador.js`, que queda en 948 líneas** (653 de código; el resto son
  comentarios y líneas en blanco). Las reglas globales fijan el límite en 800. No se parte
  aquí por dos razones que conviene dejar escritas: `dashboard.js` quedó en **1,920** tras la
  T4.7 y el plan tampoco lo partió, así que partir sólo este sería incoherente; y la
  redacción de la opción recomendada de **D6** —«ningún archivo *nuevo* supera 800 líneas»—
  se cumple: los tres archivos nuevos de esta tarea miden 592, 473 y 117. Queda como dato
  para esa decisión del owner y como trabajo natural de la T4.10, donde el corte evidente es
  separar el catálogo de ciudades de la corrida.
- **No verifica una corrida real contra la hoja.** El gate de la tarea pide «los números
  cuadran contra la hoja», y la mitad de cliente está verificada: los cuatro contadores
  muestran exactamente lo que sirve `/api/importador/estado`, sin aritmética propia. La otra
  mitad exige credenciales y gasto real de Places, y es el gate del owner que ya está abierto
  («recorrido funcional en navegador sobre datos reales»).
