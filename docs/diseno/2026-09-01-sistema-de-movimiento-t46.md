# Sistema de movimiento del panel — Plan 4, T4.6

**Fecha:** 2026-09-01 · **Rama:** `feat/rediseno-panel` · **Criterios:** CE6 (solo
propiedades del compositor), CE7 (`prefers-reduced-motion` respetado), sin regresión de
CE4 (CLS < 0.1).

---

## 1. De qué se partía

| Qué había | Dónde | Por qué es un problema |
|---|---|---|
| 9 × `transition: all` | 4 en `dashboard.css`, 1 en `formulario.css`, 2 en `importador.css`, **2 escondidos en atributos `style=`** del marcado | `all` anima también `width`, `padding`, `border-width` y `font-size`. Basta con que alguien añada un `padding` a un `:hover` para que la transición pase a costar recálculo de layout, sin que nadie se entere |
| 7 × `transition: border` | las tres superficies | El mismo problema en pequeño: `border` incluye `border-width` |
| `transition: width .5s` | barra de progreso del importador | Una corrida son **minutos** con la barra recalculando layout cuadro a cuadro |
| Chart.js sin apagar | 6 instanciaciones | Dibuja sobre `<canvas>`: sus animaciones **no pasan por la cascada CSS**, así que el bloque `prefers-reduced-motion` de `tokens.css` nunca las alcanzó |

Los dos `transition: all` del marcado son el detalle que más importa del inventario: un
barrido del CSS los daba por inexistentes.

---

## 2. Qué hay ahora

### 2.1 Ninguna transición de layout

Cada `all` se sustituyó por **la lista explícita de lo que de verdad cambia** en el
`:hover`, `:focus` o `.active` de ese elemento concreto — no por una lista genérica
copiada. `code-reviewer` verificó las trece una por una contra sus reglas: ninguna quedó
instantánea por faltarle una propiedad.

`background-color` y `border-color` **sí** son legítimas: son pintado, no layout. Esa
distinción tiene su propia trampa, documentada abajo.

### 2.2 La barra de progreso escala

De `width` a `transform: scaleX(var(--avance))` con `transform-origin: left`. El
`will-change` se pone solo mientras avanza y se retira al terminar — dejarlo puesto
reserva una capa de composición permanente para un elemento que casi todo el tiempo está
quieto.

De paso se retiró la «excepción consciente» que la T4.4 se había concedido en
`.progreso__barra` del sistema. No hacía falta ninguna excepción.

### 2.3 Chart.js se apaga desde JavaScript

Es el único movimiento del panel que no se puede apagar desde CSS. Se consulta
`matchMedia` **antes de crear la primera gráfica** —hacerlo después dejaría las seis
nacidas con la animación puesta— y se escucha el cambio en caliente.

### 2.4 Movimiento nuevo, y solo el que aclara

| Qué | Qué aclara |
|---|---|
| `fila-entra` | Las filas llegan de arriba abajo: se ve que es contenido nuevo y en qué orden viene |
| `seccion-entra` | Sin ella, catorce tablas parecidas se sustituyen sin transición y cuesta saber si el clic hizo algo |

El escalonado está **acotado a 12 filas** con paso de 25 ms. Con 50 filas y un retardo
por fila, la última entraría más de un segundo después: el escalonado dejaría de aclarar
para volverse espera.

**`/formulario` no lleva ninguna de las dos.** Es decisión del ADR, no descuido: es el
registro «denso y quieto», se usa hora tras hora y la velocidad de captura manda sobre la
estética.

---

## 3. Lo que encontraron los dos gates

`code-reviewer` (0 CRITICAL, 0 HIGH, 2 MEDIUM, 3 LOW) y `a11y-architect` (2 HIGH, 2
MEDIUM, 1 LOW). Los dos dieron por separado con el mismo MEDIUM del listener.

### 3.1 La fila podía quedar invisible con el foco dentro — HIGH

`fila-entra` usaba `backwards`, que deja la fila en su **fotograma inicial** durante todo
su retardo: hasta 275 ms para la fila 12, más los 200 ms de la animación. Con
`opacity: 0` en ese fotograma, los botones de esa fila —«Editar», «Subir comprobante»—
eran enfocables con Tab siendo completamente transparentes, **anillo de foco incluido**.

Es SC 2.4.7 (Focus Visible), y el criterio no admite excepción por ser breve. Corregido
retirando `opacity` del keyframe: el desplazamiento de 6 px basta para que la llegada se
lea, y la fila nunca deja de verse.

### 3.2 La barra no exponía su avance — HIGH

Ni rol ni valor programático: quien usa lector de pantalla no tenía forma de conocer el
avance de una corrida que dura minutos (SC 4.1.2). Corregido con `role="progressbar"`,
`aria-valuemin/max/now` y `aria-labelledby`.

**Sin `aria-live`**, y a propósito: con sondeo cada pocos segundos durante minutos serían
decenas de anuncios. `role="progressbar"` se lee cuando el operador navega al control,
que es lo que aquí hace falta.

### 3.3 El «restaurar» de Chart.js no restauraba — MEDIUM/HIGH

Al volver de `reduce` a `no-preference` se escribía `undefined` en
`Chart.defaults.animation`. Eso no restaura el valor de fábrica: lo **borra**.

No se dio por bueno el hallazgo sin comprobarlo. Una sonda en navegador lo confirmó:
sin la preferencia activa, `Chart.defaults.animation` se quedaba en `undefined` en lugar
de en su objeto. Corregido capturando el valor de fábrica una sola vez, antes de tocarlo.

### 3.4 El cambio de preferencia tiraba el trabajo del operador — MEDIUM (los dos gates)

El listener recargaba la sección visible. `loadSection` reconstruye el `innerHTML` de
tarjetas y tabla, lo que:

- **descarta el filtro y la página** que el operador tenía puestos, porque
  `loadTableSection` reasigna el dataset completo y vuelve a la página 1 sin reaplicar
  `filterTable` — dejando el cuadro de búsqueda con texto y la tabla sin filtrar;
- **destruye el nodo con el foco**, que cae a `<body>` sin aviso (SC 2.4.3).

Las dos cosas le pasan a quien acaba de pedir *menos* movimiento. Corregido actualizando
las gráficas **en sitio** (`chart.update('none')`) sin tocar tablas ni tarjetas.

### 3.5 La capa de composición se quedaba reservada — MEDIUM

`ponerAvance` solo suelta el `will-change` en 0 y en 100. Pero `fraccion` es monótona y
el backend **no la normaliza a 100** al cancelar, al agotarse el presupuesto, al
interrumpirse ni al fallar. Una búsqueda cancelada al 42 % dejaba la capa reservada hasta
la siguiente corrida — justo lo contrario de lo que decía el comentario del propio
código. Corregido con un `soltarAvance()` explícito en los cinco caminos terminales.

### 3.6 Listener `animationend` que podía no dispararse — LOW

Si una hoja anula la animación, el evento no llega nunca y el `{once:true}` queda
registrado sin disparar. Ahora se comprueba `animationName !== 'none'` antes de esperarlo.

### 3.7 Lo que los gates descartaron

Vale la pena anotarlo porque eran dudas planteadas a propósito:

- **La doble cobertura de `prefers-reduced-motion` es necesaria, no redundante.**
  `tokens.css` fuerza `animation-duration: 1ms` globalmente pero **no toca
  `animation-delay`**. Sin el bloque específico de `componentes.css`, una fila con
  `backwards` seguiría respetando su retardo de hasta 275 ms: animación instantánea, pero
  fila invisible durante la espera.
- **`seccion-entra` no agrava la pérdida de foco.** `display:none → block` ya la rompía
  antes; `opacity` no oculta contenido para tecnología de asistencia. Sigue siendo
  trabajo de la T4.10.
- **SC 2.2.2 no aplica**: ninguna animación dura más de 5 s. SC 2.3.3 es AAA, fuera del
  objetivo AA declarado.

---

## 4. Dos fallos que solo se vieron ejecutando

**La barra no se habría visto avanzar nunca.** La plantilla conservaba
`style="width:0%"` en línea sobre el relleno. Un estilo en línea gana a la hoja, así que
el elemento se quedaba con **0 px de ancho de layout** y `scaleX` escalaba la nada. Ni el
diff ni los tests de patrón lo veían: lo encontró `tools/verificar_movimiento.py` al
medir `offsetWidth`.

**El patrón del barrido marcaba en falso.** `transition:\s*background\b` casa también con
`background-color`, porque `\b` encuentra frontera de palabra antes del guion. El primer
barrido daba por prohibidas justo las propiedades correctas. Se cerró con `(?![-\w])` y
con un control que prueba las dos direcciones: casa lo viejo, no casa lo nuevo.

---

## 5. Verificación

| Qué | Resultado |
|---|---|
| Suite completa | **690 passed, 1 skipped** (baseline previo 637; +53 de la T4.6) |
| CE6 · transiciones de layout | 16 → **0**, contando las de los atributos `style=` |
| CE6 · `@keyframes` | Los tres tocan solo `transform`/`opacity` |
| CE7 · en navegador | **13/13** (`tools/verificar_movimiento.py`), con la preferencia emulada en las dos posiciones **y** cambiada en caliente |
| CE4 · CLS | 9/9 por debajo de 0.1. Peor caso 0.0284 |
| Estados (T4.5) | 5/5, sin regresión |

Las tres correcciones más importantes están comprobadas **en las dos direcciones**: con
el comportamiento anterior restaurado sobre una copia, la verificación reporta
`filas antes=11 despues=50` (el filtro se perdía), las gráficas siguen animando tras
activar la preferencia, y el `will-change` queda pegado al cancelar. Un verde que no sabe
ponerse rojo no vale nada.

---

## 6. Lo que esta tarea NO hace

- **No añade texto alternativo a las gráficas.** Es T4.10.
- **No arregla la navegación por `div` con `onclick`** ni el foco al cambiar de sección.
  T4.10.
- **No pone SRI a Chart.js.** Deuda del Plan 5.
- **No retira la clase `fila-entra`** una vez aplicada. Hoy no hace falta: los tres
  llamadores reconstruyen el `innerHTML` completo, así que las filas viejas se destruyen
  y las nuevas nacen sin clase. Queda anotado como **dependencia implícita**: una futura
  actualización de fila «in place» reintroduciría el problema y ningún test lo vería.

El respaldo previo al cambio está en `docs/auditoria/respaldos/2026-09-01/t46-antes/`
(9 archivos).
