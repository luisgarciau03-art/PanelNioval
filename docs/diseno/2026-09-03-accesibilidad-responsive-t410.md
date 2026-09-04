# Accesibilidad, responsive y rendimiento — Plan 4, T4.10

**Fecha:** 2026-09-03 · **Rama:** `feat/rediseno-panel` · **Criterios:** CE8 (accesibilidad AA),
CE9 (contraste verificado), CE10 (5 anchos sin desborde) y el punto de rendimiento de la tarea.

Es la primera tarea del plan que mide las **tres** superficies a la vez. Las tres anteriores
las rediseñaron una a una; ésta comprueba que el conjunto cumple, y arregla lo que no.

---

## 1. El resultado medible

| | Antes | Después |
|---|---:|---:|
| Hallazgos de accesibilidad, **un estado por superficie** | 22 | 0 |
| Hallazgos **recorriendo los 14 estados del tablero y los 7 diálogos** | **36** | **0** |
| Desborde horizontal del tablero a 320 px | **461 px** | **0** |
| …a 375 px · a 768 px | 406 px · 13 px | 0 · 0 |
| Pares de contraste por debajo de AA | **17** (3.61:1 el peor) | **0** |
| Superficies que declaran `<main>` | **0 de 3** | **3 de 3** |
| Bytes de terceros por página | **245 KB** | **0.5 KB** |
| Peso del logo (se pinta a 48 px) | **44.8 KB** | **0.6 KB** |
| Scripts de tercero que bloquean el render | **1** (Chart.js, en `<head>`) | **0** |
| Campos sin nombre accesible | **22** | **0** |
| Elementos interactivos inalcanzables con teclado | **4** | **0** |
| Diálogos que se anuncian como tales | **0 de 7** | **7 de 7** |
| Suite | 850 passed | **900 passed** (+50) |

Todo está medido en navegador por `tools/verificar_accesibilidad.py`, que es nuevo en esta
tarea, sobre las tres superficies y los cinco anchos de CE10 (320, 375, 768, 1024, 1440).

---

## 2. Por qué un auditor propio y no `axe`

Esta máquina no tiene `axe-core` y el proyecto no descarga dependencias de red para
verificar. Pero la razón de fondo es otra, y la dio la T4.9: **el hallazgo más caro de la
tanda anterior no lo veía ningún guarda de patrones**. Era un color de token atenuado con
`opacity: .55`, que da 2.97:1 y pasa el guarda de CE3 sin despeinarse, porque el color
declarado sí es un token. Lo que rompe el contraste es la opacidad, y eso sólo se ve
midiendo el color **efectivo** en el navegador.

Los tres fallos de contraste de esta tarea son **exactamente el mismo tipo**:

| Dónde | Ratio | Qué lo rompía |
|---|---:|---|
| `.nav-label` (×4, etiquetas de grupo de la barra) | 3.68:1 | blanco al **60 %** sobre el azul |
| `.nav-item__insignia` (envíos con problema) | 3.61:1 | heredaba el **85 %** de `.nav-item`; una opacidad del padre no se deshace desde el hijo |
| `.info-item .lbl` (×6, etiquetas de la ficha) | 4.33:1 | `--texto-suave` sobre `--azul-tenue-2`, el par frágil que ya avisó el gate de la T4.9 |

Ninguno de los tres es un color literal. Ninguno lo habría encontrado un `grep`.

El auditor compone la **opacidad acumulada** de todos los ancestros y mide contra el primer
fondo opaco, incluidos los **degradados**: la barra lateral y las tres cabeceras lo son, así
que un auditor que se los saltara dejaría media pantalla sin medir y saldría limpio.

### 2.1 El auditor está comprobado en las dos direcciones

Un cero no vale nada hasta que se demuestra que el método encuentra un defecto que sabemos
que está ahí. Se reintrodujeron los tres, de uno en uno, y se restauró verificando por hash:

| Defecto reintroducido | Lo detecta |
|---|---|
| `opacity: .6` en `.nav-label` | 4 hallazgos de contraste |
| barra lateral fija (media query desactivada) | desborde de 175 px a 320 px y 120 px a 375 px |
| logo sin `alt` | 1 hallazgo de imagen |

---

## 3. El tablero no era responsive, y eran dos cosas a la vez

`#sidebar` era una barra lateral **fija de 230 px sin una sola media query**. A 320 px eso
deja 90 px de contenido. Pero corregir sólo eso no bastaba: `#main` es un elemento flex, y
`min-width: auto` —su valor inicial— lo ata al ancho mínimo de su contenido, así que no podía
encogerse aunque le sobrara sitio. El mismo detalle apareció una segunda vez en `.chart-box`,
que es elemento de **rejilla** y trae la misma atadura: con la rejilla ya en una columna, el
`<canvas>` seguía poniendo suelo y el tablero desbordaba 36 px.

Por debajo de 1024 px la barra deja de ser lateral y pasa a ser una **banda superior** con la
navegación en línea. No hay menú desplegable ni JavaScript nuevo: es la misma navegación, en
otra dirección. Lo que evita el precio de ese cambio —12 botones antes del contenido en cada
carga— es el **enlace de salto**, que el sistema traía desde la T4.4 y que hasta ahora no
usaba nadie.

A 640 px la barra superior envuelve, porque el título quedaba recortado en «Dash…».

---

## 4. Rendimiento: el panel dependía de un tercero para pintar

`Chart.js` venía de `cdn.jsdelivr.net`, **en `<head>` y sin `defer`**. Eso significa que el
tablero no pintaba **nada** hasta que el CDN contestara. Medido desde esta máquina:
**15.1 segundos**. No es una hipótesis: la primera corrida del auditor se agotó en el `goto`
por esto.

Y no llevaba `integrity`, así que tampoco había forma de comprobar que llegaba lo esperado
—deuda que el traspaso anotaba para el Plan 5—.

Auto-hospedarlo en `static/js/vendor/` resuelve las dos cosas a la vez: deja de ser un
tercero (mismo origen, sin bloqueo de terceros, sin SRI que discutir) y el archivo queda
**verificable por hash en el repo**, con un test que lo comprueba y su control negativo.

El logo era el otro tercero: **44.8 KB para pintarse a 48 px**. Se pide a Cloudinary con la
transformación que ya ofrece (`f_auto,q_auto,w_96,h_96,c_fit`) y baja a **0.6 KB**. No se
copia al repo a propósito: el asset sigue siendo del owner, sólo se pide del tamaño que se
usa.

### 4.1 El presupuesto se medía mal

La primera medición declaró el CSS del tablero **fuera de presupuesto** (54.7 KB contra un
tope de 50). Era falso: los presupuestos de las reglas del entorno están escritos en **gzip**,
y el servidor de desarrollo no comprime. Comprimido son **18.5 KB**. En el VPS quien comprime
es Caddy. El medidor ahora compara contra el tamaño comprimido y lo dice.

| Superficie | CSS (gzip) | JS (gzip) | LCP | Terceros |
|---|---:|---:|---:|---:|
| Tablero | 18.9 / 50 KB | 98.8 / 300 KB | 276 ms | 0.5 KB |
| Formulario | 14.2 / 50 KB | 14.8 / 300 KB | 400 ms | 0.5 KB |
| Importador | 16.5 / 50 KB | 17.0 / 300 KB | 120 ms | 0.5 KB |

Los tiempos son **medianas de tres cargas** y salen del servidor de desarrollo: valen para
comparar entre sí, no como cifra de producción. Se toma la mediana porque una sola medida
variaba al doble entre corridas —el mismo tablero dio 3,464 ms y 1,428 ms—, y un número
inestable presentado como métrica engaña igual que uno falso.

---

## 5. Semántica y estructura

- Las tres superficies declaran `<main>`. El tablero era `<div id="main">`: el cambio no toca
  ni una regla de CSS, porque todos los selectores van por `#main`.
- El tablero saltaba de `h1` a `h3` en los 19 títulos de sus tablas y gráficas. Ahora son
  `h2` y el esquema no anuncia un nivel que no existe.
- El logo tiene `alt` y dimensiones en las tres superficies (era la mejora **M15** del
  índice: tres apariciones, ninguna con `width`/`height` y dos sin `alt`).
- La imagen del visor de comprobantes tenía `src` dinámico y ningún `alt`.

---

## 6. Lo que encontraron los gates

Dos revisiones en paralelo: `a11y-architect` y `accessibility-tester`. Entre las dos
cambiaron el resultado de esta tarea más que todo lo anterior, y no por los hallazgos
sueltos sino por **uno estructural**.

### 6.1 El auditor sólo miraba un estado por superficie

Lo dijo `a11y-architect` sin rodeos: `main()` cargaba cada URL una vez y auditaba ese DOM.
El tablero tiene **14 secciones** intercambiadas con `display:none`, el formulario 15 pasos
y 3 modales, el importador varios estados de corrida. **Cualquier defecto confinado a un
estado que no fuera el inicial era invisible por diseño**, y eso vale para contraste,
teclado, encabezados y etiquetas por igual.

Los dos CRITICAL que encontró son exactamente eso: las pestañas de Seguimiento
(`static/js/dashboard.js:1196`) y el selector de color del modal de edición (`:1291`) eran
`<div>` con `onclick`, sin `tabindex` ni `role` — el mismo defecto que la T4.7 corrigió a
fondo en la navegación, sobreviviendo en dos sitios que la auditoría nunca visitaba.

**El auditor ahora recorre los estados**: activa cada sección del tablero como lo haría el
operador y revela cada diálogo. El efecto inmediato fue pasar de **0 a 36 hallazgos** sin
tocar una línea del panel. Ese 36 es la medida real de lo que el «0 hallazgos» anterior
estaba tapando.

### 6.2 Lo que salió al recorrer los estados

| Hallazgo | Gravedad | Estado donde vivía |
|---|---|---|
| Pestañas de Seguimiento sin teclado | CRITICO | sección Seguimiento |
| Selector de color sin teclado | CRITICO | modal de edición |
| Casilla «contactado» de Bruce: `<span onclick>` | CRITICO | sección Prospectos Bruce |
| Tabla de ciudades ordenando desde un `<th onclick>` | CRITICO | sección Ciudades |
| **22 campos sin nombre accesible** (14 sólo con `placeholder`, 8 sin nada) | ALTO/CRITICO | repartidos por 8 secciones |
| 6 pares de contraste bajo AA | ALTO | tablas con filas alternas, pestañas, modal de edición |
| Botón «✕» de 18×30 px | MEDIO | modal de subida |

Un detalle del contraste que merece nombre: `--exito` pasa AA **sobre blanco** (4.54:1),
pero `tr:nth-child(even) td` pinta las filas pares con `--azul-tenue-2`, y ahí baja a
**4.13:1**. En una tabla con filas alternas, la mitad del texto verde caía por debajo del
mínimo. Es el mismo par frágil que ya apareció en la T4.9 y en el formulario, por tercera
vez y en un sitio distinto.

### 6.3 Los siete diálogos no eran diálogos

Los dos gates lo encontraron por separado. Ninguno de los siete modales tenía `role="dialog"`,
nombre accesible ni retención de foco: tapaban la página visualmente y para un lector no
existían, con el Tab escapándose al fondo, que seguía siendo interactivo.

`static/js/dialogo.js` lo resuelve **sin tocar las siete funciones de apertura**, que viven
repartidas en dos archivos: observa el atributo `style` de cada diálogo declarado y reacciona
cuando se vuelve visible — mueve el foco dentro, lo retiene, cierra con Escape *pulsando el
propio botón de cerrar del diálogo* (para que corra la misma lógica que un clic, que a veces
limpia estado) y devuelve el foco al salir.

**Y una trampa que hubo que evitar**: una retención de foco sin salida es *peor* que no
tenerla — es un incumplimiento de SC 2.1.2. `#modal-correo` no tenía botón de cerrar; su
salida es «Continuar sin correo», y hasta marcarla el diálogo habría quedado sin escapatoria
por teclado. Hay un test que comprueba que **los siete** tienen salida marcada, y el auditor
lo comprueba también en navegador.

### 6.4 Tres hallazgos del verificador que no eran ciertos

`accessibility-tester` reportó cinco HIGH; **tres no se sostienen**, y lo digo con la línea
del código delante porque el propio informe avisaba de que había leído sólo fragmentos:

- «encabezados de tabla sin `aria-sort`» → está en `dashboard.js:826`, con `scope="col"`,
  desde la T4.7.
- «paginación sin anunciar» → `aria-current="page"` en el botón activo más el texto
  «Página X de Y», también de la T4.7.
- «filtrado del importador sin anuncio de cantidad» → la región viva
  `#chips-resumen-lectores`, con 600 ms de retardo, es de esta misma tanda.

El cuarto —`aria-activedescendant` en el listbox— **contradice al `a11y-architect` de la
T4.9**, que validó el `tabindex` móvil con foco real del DOM como el patrón correcto del APG.
Se mantiene el patrón y se deja escrita la discrepancia.

Lo valioso de ese informe no fueron sus hallazgos sino la pregunta que respondió: *qué no
está verificado*. De ahí salieron cuatro reglas nuevas del auditor (diálogos, `<canvas>` sin
nombre, destino del enlace de salto y tamaño de objetivo) y la lista de gates humanos del §8.

### 6.5 Tres exenciones que el auditor tenía que aprender

Al recorrer los estados aparecieron también falsos positivos, y corregirlos importa tanto
como añadir reglas: un auditor que grita por todo acaba ignorado.

- **Controles deshabilitados**: WCAG 1.4.3 los exime explícitamente. Sin la exención, cada
  botón deshabilitado salía como CRITICO de contraste (el «Guardar correo» del formulario
  daba 2.22:1 por su propia opacidad de deshabilitado).
- **El fondo de un diálogo que cierra al pinchar** no es un control: es un atajo de ratón que
  duplica un botón que sí existe. Igual que un manejador que sólo llama a `stopPropagation`.
- **Una imagen sin `src`** no descarga nada ni desplaza nada; exigirle dimensiones era ruido.

---

## 7. Verificación

| Qué | Resultado |
|---|---|
| `tools/verificar_accesibilidad.py` (nuevo) | **0 hallazgos** recorriendo 14 secciones, 7 diálogos y 5 anchos |
| El mismo auditor con los defectos reintroducidos | los **3** vuelven a salir; restaurado y verificado por hash |
| Suite completa | **900 passed, 2 skipped** (850 + 50) |
| `verificar_estados` · `movimiento` · `tablero` · `formulario` · `importador` | 5/5 · 13/13 · 24/24 · 12/12 · 45/45, sin regresión |
| `medir_cls.py` | 9/9 por debajo de 0.1; peor caso 0.0329 |
| `medir_presupuesto.py` (nuevo) | las tres superficies dentro de presupuesto |

Capturas en `docs/diseno/2026-09-03-responsive-t410/`: las tres superficies en los cinco
anchos, **con datos sintéticos** (`--sinteticos`), porque una tabla vacía no desborda y no
enseñaría nada de la maquetación. Ninguna lleva datos de clientes.

---

## 8. Lo que esta tarea NO cierra

- **Nada de esto sustituye a un lector de pantalla real.** Un auditor automático comprueba
  que la información está en el árbol de accesibilidad; no comprueba que se entienda al
  oírla. Queda como gate humano.
- **`importador.js` sigue en 948 líneas** y `dashboard.js` en 1,920, ambos por encima del
  límite de 800 de las reglas globales. Es la decisión **D6** del owner, no un descuido.
- **El zoom de TEXTO al 200 %** (SC 1.4.4) no lo mide el auditor: reducir el ancho de la
  ventana es la técnica aceptada para Reflow (SC 1.4.10), pero no es lo mismo que aumentar el
  tamaño del texto. A vigilar a mano: `.esqueleto-tarjeta{height:92px}`, que es una caja de
  texto con alto fijo.
- **Lo que sólo comprueba un lector de pantalla real** (NVDA/JAWS/VoiceOver), y que queda
  como gate del owner porque ninguna herramienta automática lo cierra:

  | Qué escuchar | Dónde |
  |---|---|
  | Que al entrar al listbox se anuncie la ciudad enfocada y su estado de selección | importador |
  | Que al filtrar se anuncie el nuevo conteo, una vez y no una por tecla | importador |
  | Que los siete diálogos se anuncien como diálogo y que Escape salga de todos | tablero y formulario |
  | Que al cambiar de paso se anuncie la pregunta nueva | formulario |
  | Que el orden de una columna se anuncie al enfocar su encabezado | tablero |
  | Que las seis gráficas se lean con sus cifras y no como «canvas» | tablero |
