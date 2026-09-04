# Sistema de diseño del panel NIOVAL

**Estado:** vigente desde el Plan 4 (2026-08-31 → 2026-09-03) · **Dirección:**
`docs/adr/2026-08-31-direccion-visual-panel.md`

Este documento existe para que los cambios futuros no erosionen el sistema. No es una guía de
estilo aspiracional: cada regla de aquí salió de un fallo concreto, medido, y casi todas
tienen un test o un arnés que las sostiene. Cuando una regla parezca arbitraria, busca el
«por qué» — está escrito.

---

## 1. Cómo usarlo

Las tres superficies (`/`, `/formulario`, `/importador`) cargan **las mismas cuatro hojas**,
en este orden, y luego la suya:

```
tokens.css  →  base.css  →  componentes.css  →  <superficie>.css
```

El orden importa: `componentes.css` usa los tokens, y la hoja de cada superficie ajusta los
componentes. Los scripts van al final del `<body>`:

```
[vendor/chart.umd.min.js]  →  dialogo.js  →  estados.js  →  <superficie>.js
```

**Antes de escribir CSS nuevo, mira si el componente ya existe.** El importador mantuvo su
propio `.stat-box` durante tres tareas mientras `.stat` —escrito *para* esa pantalla— no lo
usaba nadie.

---

## 2. La dirección, en una frase

**Editorial / Swiss disciplinado: un solo sistema, tres registros.** Los tokens, la escala y
la paleta son únicos; lo que cambia por superficie es la calibración.

| Superficie | Registro | Qué significa en la práctica |
|---|---|---|
| `/formulario` | **Denso y quieto** | Sin animación de entrada. Es decisión, no descuido: se usa hora tras hora y la velocidad de captura manda sobre la estética |
| `/` | **Jerárquico** | Contraste de escala fuerte: lo que se mira primero domina, el resto se retira |
| `/importador` | **Narrativo** | El movimiento cuenta el avance de una corrida que dura minutos y gasta dinero |

---

## 3. Tokens — `static/css/tokens.css`

**Es el único archivo donde puede aparecer un color literal.** Lo comprueba
`tests/test_plan4_tokens.py`, y el resto del proyecto está a cero.

### 3.1 La regla de los pares

Cada color semántico tiene **dos** valores y la diferencia no es cosmética:

| | Para qué | Ejemplo |
|---|---|---|
| `--exito` | Texto y bordes de control. Pasa AA en los dos sentidos | `#008930`, 4.54:1 |
| `--exito-vivo` | **Sólo decoración**: puntos, franjas, rellenos sin texto encima | `#00CC47`, 2.16:1 |

Igual con `--aviso`/`--aviso-vivo` y `--error`/`--error-vivo`. Poner texto sobre un `-vivo`
es el error más fácil de cometer y el más difícil de ver.

### 3.2 Dos trampas de contraste que ya han mordido tres veces

**1. La opacidad rompe el contraste sin tocar el color.** Un token perfectamente válido con
`opacity: .55` da 2.97:1 y **ningún guarda de patrones lo ve**, porque el color declarado sí
es un token. Pasó en el importador (T4.9, CRITICAL), y otras tres veces en el tablero (T4.10:
`.nav-label` al 60 %, la insignia que heredaba el 85 % de su botón, el conteo de pestaña al
75 %).

> Para atenuar texto se usa un token más claro que ya esté medido, **nunca `opacity`**. La
> opacidad se reserva a elementos no textuales.

**2. Un par que pasa sobre blanco puede no pasar sobre un tinte.** `--texto-suave` da 4.76:1
sobre blanco y **4.33:1** sobre `--azul-tenue-2`. `--exito` da 4.54:1 sobre blanco y
**4.13:1** sobre ese mismo tinte — y `tr:nth-child(even) td` pinta la mitad de las filas de
todas las tablas con él.

> Sobre fondos con tinte se usa `--gris-600` en vez de `--texto-suave`, y `--exito-fuerte` en
> vez de `--exito`.

### 3.3 El anillo de foco es de dos tonos, y no es un capricho

Un solo color no sirve: `--azul` da 7.57:1 sobre blanco pero **1.43:1** sobre la barra
lateral azul y 2.36:1 sobre la consola — o sea invisible justo donde más se navega con
teclado. Con dos anillos concéntricos (`--foco-oscuro` fuera, `--foco-claro` dentro) basta
con que uno pase 3:1 en cada fondo, y este par pasa en los ocho fondos del sistema.

### 3.4 Tipografía

Pila de sistema, **sin fuente web**: es un panel interno de jornada completa y los bytes se
gastan mejor no gastándolos donde manda la velocidad de captura. Lo que sí es decisión:

- **Cifras tabulares** en todo lo numérico. Sin ellas las columnas bailan al reordenar, que
  es el defecto tipográfico más visible de un panel de datos. Cuesta cero bytes.
- **Pila monoespaciada declarada** (`--fuente-mono`) para la consola. `monospace` a secas la
  deja a merced del navegador.
- **Escala con saltos reales** (`--texto-xs` … `--texto-3xl`). Tres tamaños casi iguales no
  son jerarquía.

---

## 4. Componentes — `static/css/componentes.css`

| Componente | Para qué | Ojo con |
|---|---|---|
| `.btn`, `.btn--secundario`, `.btn--error` | Acciones | Los estados hover/focus/active/disabled ya están; no los redefinas |
| `.tarjeta` | Contenedor de sección | — |
| `.chip`, `.chip__conteo` | Filtro seleccionable con conteo | `aria-pressed` marca el activo |
| `.stat`, `.stat--principal` | Indicador numérico | `--principal` es **uno por pantalla**: el dato que manda (en el importador, `nuevos_en_sheet`) |
| `.insignia--exito/aviso/error/info` | Estado corto | Pares de tinte/texto ya medidos |
| `.campo`, `.campo__control`, `.campo__error` | Formulario | El borde usa `--borde-control` (3:1), que es WCAG 1.4.11 |
| `.tabla` | Datos | Encabezado fijo, `aria-sort` operable con teclado |
| `.progreso`, `.progreso__barra` | Avance | Anima `scaleX`, nunca `width` |
| `.consola` | Registro de corrida | Pila mono declarada; necesita `tabindex="0"` porque tiene scroll |
| `.esqueleto*`, `.estado--vacio/error/parcial` | Estados de carga | §5 |
| `.fila-entra`, `.seccion-entra` | Movimiento | §6 |

---

## 5. Los cuatro estados — `static/js/estados.js`

Antes había **uno**: `.loading` con un spinner que sustituía el contenido, así que el layout
saltaba cuando llegaban los datos. Ahora son cuatro, y el módulo impone tres reglas que no
deja negociar:

1. **El esqueleto no parpadea.** Por debajo de 200 ms no se pinta: una respuesta de 80 ms con
   esqueleto se ve peor que sin él.
2. **Un error siempre trae salida.** `Estados.error` exige `reintentar`; sin eso el operador
   sólo puede recargar la página entera.
3. **Nada celebra sin verificar.** No hay confeti, ni marcas de verificación, ni verde de
   éxito. *Un estado que sólo puede afirmar «no recibí datos» no se viste de éxito.*

Esa tercera regla es del ADR (voto del Crítico) y se aplica también a los finales de una
corrida: en el importador, de cuatro finales posibles **sólo `done` celebra**; detener a mano
y agotar el presupuesto no son fallos —son decisiones, una del operador y otra del tope— pero
tampoco completaron.

**El esqueleto de la primera carga va en la plantilla, no en el JS.** Es lo único que evita
el salto de layout del primer render. Y el aviso para lectores va en un nodo vacío con
`data-aviso-carga` que `estados.js` rellena *después*: un `role="status"` que ya tenía texto
cuando el lector construyó el árbol **no se anuncia** — los lectores anuncian mutaciones.

---

## 6. Movimiento

Dos animaciones en todo el sistema, y las dos existen porque **aclaran** algo:

- `.fila-entra` — las filas llegan de arriba abajo: se ve que es contenido nuevo y en qué orden.
- `.seccion-entra` — la sección nueva entra desde abajo: se ve que el clic hizo algo.

Reglas duras:

- **Sólo `transform`, `opacity` y `color`/`background-color`.** Nada de `transition: all`
  —anima también lo que fuerza layout— ni de animar `width`/`height`/`top`/`left`/`border`.
- **La barra de progreso escala, no se ensancha.** Una corrida son minutos de barra
  moviéndose; animar el ancho recalcula layout en cada cuadro.
- **`will-change` se pone y se retira.** Dejarlo puesto reserva una capa de composición
  permanente para algo que el resto del tiempo no se mueve. Y ojo: una corrida cancelada al
  42 % no pasa ni por 0 ni por 100, así que hay que soltarlo **en todos los caminos
  terminales**.
- **`prefers-reduced-motion` se respeta en los dos sitios.** El CSS no alcanza a Chart.js,
  que dibuja en `<canvas>`: hay que apagarlo desde JavaScript con `matchMedia`.

---

## 7. Accesibilidad: lo que no se negocia

- **Todo lo que se comporta como control es un control.** Un `<div onclick>` no entra en el
  orden de tabulación, no responde a Enter ni a Espacio y no se anuncia. El panel tenía 15;
  ahora ninguno. El precio de usar el elemento correcto es reponer lo que el navegador le
  pone de fábrica (`background:none;border:0;padding:0;color:inherit`).
- **Una lista larga usa `tabindex` móvil.** Las 606 ciudades del importador son **una** parada
  de tabulación, no 606: se recorren con flechas. 606 paradas serían peor que ninguna.
- **Un diálogo modal necesita las tres cosas**: `role="dialog"`, nombre accesible y retención
  de foco. Y **una retención de foco sin salida es peor que ninguna** (SC 2.1.2): todo diálogo
  lleva un botón marcado con `data-cerrar`, que es lo que pulsa Escape.
- **No prometas modalidad que no cumples.** `role="alertdialog"` sin `aria-modal`, sin trampa
  de foco y sin el fondo inerte le dice al lector algo que es falso.
- **Objetivos de 24×24 px como mínimo** (SC 2.5.8).
- **El destino de un enlace de salto necesita `tabindex="-1"`.** Sin eso el navegador
  desplaza pero no emite evento de foco: para un lector el salto es un scroll silencioso, y
  es justo el usuario para el que existe el mecanismo.
- **El `placeholder` no es una etiqueta.** Desaparece al escribir y no todos los lectores lo
  anuncian.

---

## 8. Rendimiento

- **Nada de terceros en la ruta crítica.** Chart.js venía de un CDN, en `<head>` y sin
  `defer`: el tablero no pintaba nada hasta que respondiera, y respondió en **15.1 s** el día
  que se midió. Está auto-hospedado en `static/js/vendor/` y verificado por hash.
- **Las imágenes se piden del tamaño que se pintan.** El logo pesaba 44.8 KB para verse a
  48 px; pedido con la transformación de Cloudinary, 0.6 KB.
- **Dimensiones explícitas en toda imagen visible al cargar**, o el hueco se reserva a cero y
  la página salta.
- Presupuesto: **< 300 KB de JS y < 50 KB de CSS, comprimidos**. Ojo con medirlo: el servidor
  de desarrollo no comprime, y comparar el tamaño en claro contra un tope en gzip declara
  fuera de presupuesto algo que no lo está.

---

## 9. Cómo verificar

Ocho herramientas, todas arrancan la app **sin credenciales de Google** —comprobado en la
dirección útil, que el cliente falla— y ninguna llama a APIs de pago.

| Herramienta | Qué comprueba |
|---|---|
| `tools/verificar_accesibilidad.py` | Contraste efectivo, teclado, foco, etiquetas, landmarks, diálogos, objetivos y desborde en 5 anchos — **recorriendo los estados**, no sólo el inicial |
| `tools/verificar_estados.py` | Los cuatro estados de carga |
| `tools/verificar_movimiento.py` | Que el movimiento no toca layout y que la preferencia se respeta |
| `tools/verificar_tablero.py` | El tablero: gráficas, orden, paginación, estructura del DOM |
| `tools/verificar_formulario.py` | La captura completa sólo con teclado, contando pulsaciones |
| `tools/verificar_importador.py` | Los chips, el registro, los cuatro finales |
| `tools/medir_cls.py` | Salto de layout con la red lenta |
| `tools/medir_presupuesto.py` | Bytes por tipo, terceros, bloqueo de render y LCP |

**Y la regla que las gobierna a todas: un cero no vale nada hasta que demuestras que el
método encuentra un defecto que sabes que está ahí.** Cada arnés de esta tanda está
comprobado en las dos direcciones, reintroduciendo el defecto y viéndolo salir.

El corolario que costó más caro: `tools/verificar_accesibilidad.py` daba **0 hallazgos**
mientras auditaba un solo estado por superficie. Al hacerle recorrer las 14 secciones del
tablero y los 7 diálogos aparecieron **36**. Cuando añadas una pantalla o un modal, asegúrate
de que el auditor lo visita.

---

## 10. Lo que el sistema NO cubre

- **Lectores de pantalla reales.** Un auditor comprueba que la información está en el árbol
  de accesibilidad; no que se entienda al oírla. Es gate humano.
- **Zoom de texto al 200 %** (SC 1.4.4). Reducir el ancho de la ventana es la técnica
  aceptada para Reflow, pero no es lo mismo.
- **Fondos de imagen rasterizada.** El medidor de contraste entiende colores y degradados; si
  alguien pone texto sobre un `url(...)`, cae al blanco por defecto y devolvería un «pasa»
  falso.
- **El tamaño de los archivos JS.** `dashboard.js` (1,920 líneas) e `importador.js` (948)
  superan el límite de 800 de las reglas globales. Es la decisión **D6**, abierta.
