# AUDITORÍA DEL REDISEÑO CONSTRUIDO (PR #43)

**Tarea:** Plan 4 · T4.1 · **Fecha:** 2026-09-16 · **Rama auditada:** `feat/rediseno-panel` (`35a7a50`)
**Auditor:** sesión externa al ejecutor del PR #43. Nadie lo había revisado desde fuera.

---

## 0. EL CRITERIO, FIJADO ANTES DE MIRAR

> Esta sección se escribió y se commiteó **antes** de abrir un solo documento del rediseño.
> El plan lo exige por un motivo concreto: si el criterio se formula después de ver el
> resultado, la auditoría deja de serlo y se convierte en una racionalización de lo que ya
> está construido. Lo que sigue es contra qué se juzga, no qué se encontró.

### 0.1 El dominio manda, y este dominio es una herramienta de trabajo

PanelNioval **no es una landing**. Es un panel interno que **una persona usa todos los días**
para cerrar llamadas: abre el formulario, lee un contacto, marca un resultado, pasa al
siguiente. Cientos de veces.

Eso fija el tono antes que cualquier gusto: **denso, callado y escaneable**. La regla de
`frontend-design-direction` es explícita — *«no fuerces una composición de landing sobre una
herramienta de uso diario repetido»*. Un rediseño que llegue con héroe centrado, degradados
decorativos y tarjetas enormes habrá fallado **aunque se vea bonito**, porque le cobra al
operador un peaje de lectura en cada repetición.

**Corolario que se aplicará sin piedad:** cualquier elemento que sea bonito y no ayude a
escanear cuenta como **coste**, no como mérito.

### 0.2 Lo que el dueño pidió por su nombre

El encargo nombra tres cosas. La auditoría comprueba que **existen de verdad**, no que
aparezcan en el título de un documento:

| Eje | Qué se exige para darlo por hecho |
|---|---|
| **Movimientos** | Un sistema declarado (duraciones, curvas, qué se anima y qué no) **y** respeto a `prefers-reduced-motion` |
| **Display** | Jerarquía visual y tipográfica decidida a propósito, no heredada del navegador |
| **Pantallas de carga** | Los **cuatro** estados —cargando, vacío, error, parcial— en cada superficie que pide datos |

### 0.3 La matriz de cobertura

3 superficies (tablero · formulario · importador) × 3 ejes (movimiento · display · estados de
carga) × los breakpoints declarados. Cada celda: **¿hay captura y decisión escrita?** Un hueco
es una celda sin una de las dos cosas.

### 0.4 La política anti-plantilla: ≥4 de 10, con la prueba delante

De las reglas del entorno. Se exige nombrar **cuáles** y con **qué captura** se prueban. Decir
«tiene buena jerarquía» sin señalar dónde no cuenta.

1. Jerarquía por contraste de escala · 2. Ritmo intencionado en el espaciado · 3. Profundidad
o capas · 4. Tipografía con carácter y estrategia de pares · 5. Color semántico, no decorativo
· 6. Estados de interacción diseñados · 7. Composición editorial o que rompe la rejilla ·
8. Textura o atmósfera · 9. Movimiento que aclara el flujo · 10. Visualización de datos como
parte del sistema.

### 0.5 Los cuatro defectos que descalifican

Prohibidos por las reglas del entorno. Se buscan **a propósito**, no se espera a tropezarlos:

- Rejilla de tarjetas uniforme sin jerarquía.
- Radio y sombra idénticos en todos los componentes.
- Gris sobre blanco con un único acento decorativo.
- Tarjetas dentro de tarjetas.

### 0.6 Qué puede fallar y quiero atrapar

- Un documento que **declara** un sistema que el CSS no implementa.
- Capturas que prueban el caso feliz y **ningún estado degradado**.
- `prefers-reduced-motion` citado en prosa y ausente del CSS.
- Los cuatro estados cubiertos en el tablero y **olvidados en el importador**, que es la
  superficie con la espera más larga (una corrida de Places tarda minutos).

### 0.7 Dato de T4.0 que esta auditoría ya trae encima

La línea base mide **CLS 0.1924 en el tablero a 1440**, casi el doble del umbral. Si el
rediseño no aborda el desplazamiento de layout, es un hueco **aunque todo lo demás esté bien**:
el CLS es exactamente lo que el operador sufre cuando el panel le mueve un botón bajo el dedo.

---

*(Lo que sigue se escribió DESPUÉS de leer los documentos y el CSS. El criterio de
arriba no se ha tocado: `git log` lo demuestra — commit `4212917`.)*

---

# 1. EL VEREDICTO, EN UNA LÍNEA

> **El rediseño cumple el encargo y supera el criterio anti-plantilla — 5 cualidades probadas
> de las 10, sobre un mínimo de 4 — pero tiene 3 huecos bloqueantes, y ninguno es estético.**
> El más grave no está en el diseño sino en su evidencia: **las capturas del «después» del
> tablero están todas a cero**, así que el gate del owner en T4.2 compararía un «antes» con
> datos reales contra un «después» vacío. Los otros dos: la pantalla principal **no usa el
> sistema de diseño que el propio PR declara**, y hay **tarjetas dentro de tarjetas** con el
> mismo tratamiento, que las reglas prohíben por su nombre.

---

# 2. LO QUE EL REDISEÑO HACE BIEN, Y HAY QUE DECIRLO

Antes de los huecos, lo que esta auditoría confirma con evidencia:

**La dirección visual acertó el dominio.** El ADR elige *«editorial / Swiss disciplinado»* y lo
justifica exactamente como exige el criterio de §0.1: *«Se usa hora tras hora; la velocidad de
captura manda sobre la estética. Un rediseño que se vea mejor y capture más lento es un
retroceso»*. Descartó bento *«porque no resuelve tablas: las distorsiona»* y descartó
profundidad por capas porque *«es justo donde nacen los repaints»*. **Renunció a tres
cualidades a propósito** —textura, rompe-rejilla, profundidad— por estar en tensión con el CLS.
Eso no es un hueco: es una decisión declarada y bien argumentada.

**El formulario, que es donde se trabaja, se midió en pulsaciones:** de **~90 a 11** para una
captura completa, y de «no se puede sin ratón» a «sí». Ese es el número que importa en una
herramienta de uso diario, y es el que el rediseño eligió mover.

## 2.1 Validación cruzada del CLS: dos instrumentos independientes coinciden

| Medición | Tablero 1440, «antes» |
|---|---:|
| La del PR #43 (`tools/medir_cls.py`, datos sintéticos, servidor local) | **0.1941** |
| La mía en T4.0 (Playwright + PerformanceObserver, **producción real**) | **0.1924** |

**Difieren en un 0.9 %**, con herramientas, entornos y datos distintos. Ninguna de las dos se
apoya en la otra. Eso convierte el 0.19 en un hecho, no en una cifra de un informe.

Y el rediseño **lo arregla**: 9 de 9 puntos por debajo de 0.1, el tablero a 1440 baja a
**0.0253** y el peor caso queda en 0.0286. Las tres causas están diagnosticadas una por una —
Chart.js redimensionando el `<canvas>` (0.30 a 768 px), la cabecera creciendo sola a los 477 ms
(0.11), y la caja de ciudades *«con techo pero sin suelo»*.

**Mi criterio de §0.7 decía que si el rediseño no abordaba el CLS era un hueco aunque todo lo
demás estuviera bien. Lo aborda, y con método.**

---

# 3. MATRIZ DE COBERTURA

3 superficies × 3 ejes. Cada celda: **¿decisión escrita?** · **¿captura?** · **¿implementado en
código?** — las tres cosas, porque un documento que declara lo que el CSS no hace no cubre nada.

## 3.1 Eje MOVIMIENTO

| Superficie | Decisión escrita | Captura | En el CSS | Veredicto |
|---|---|---|---|---|
| Tablero | ✅ `.fila-entra`, escalonado 12 filas × 25 ms | ✅ | ✅ `componentes.css:562` | **Cubierto** |
| Formulario | ✅ **ninguna animación, a propósito** («denso y quieto», decisión del ADR) | n/a | ✅ verificado: no las usa | **Cubierto** |
| Importador | ✅ `.seccion-entra`, barra de progreso `width`→`transform:scaleX` | ✅ `corrida.png` | ✅ | **Cubierto** |
| **Transversal** | ✅ sólo `transform`/`opacity`/`color`; nada de `transition: all` | — | ✅ **16 → 0** transiciones de layout | **Cubierto** |
| **`prefers-reduced-motion`** | ✅ | ✅ 13/13 en navegador | ✅ **3 bloques** (`tokens.css:231`, `componentes.css:503` y `:562`) + Chart.js vía `matchMedia` | **Cubierto** ⚠️ ver M2 |

**Hueco de documentación (M-DOC):** ningún documento trae la **tabla de duraciones y curvas**.
Los tokens existen en el CSS (`--dur-rapida/normal/lenta`, `--curva-salida/estandar`) pero el
sistema no los publica. Quien venga a añadir una animación no tiene contra qué alinearse.

## 3.2 Eje DISPLAY (jerarquía y tipografía)

| Superficie | Decisión escrita | Captura | En el CSS | Veredicto |
|---|---|---|---|---|
| Tablero | ✅ 3 pesos de cifra: 56 / ~30 / ~22 px, dos filas con título propio | ✅ `despues/dashboard-*.png` | ⚠️ **40 `font-size`, sólo 2 con token** | **HUECO B2** |
| Formulario | ✅ densidad y orden de lectura | ✅ | ⚠️ **12 `font-size`, 0 con token** | **HUECO B2** |
| Importador | ✅ escala con saltos reales, 56/28 px (2.0×) | ✅ | ✅ **18 de 19 con token** | **Cubierto** |
| **Cifras tabulares** | ✅ `tabular-nums` en KPI y tablas | — | ✅ | **Cubierto** |
| **Tipografía** | ✅ pila de sistema, **sin fuente web**, justificado por `font-display:swap` → reflow | — | ⚠️ `dashboard.css:3` y `formulario.css:3` redeclaran `'Segoe UI'` literal **contra el ADR** | **HUECO B2** |

## 3.3 Eje ESTADOS DE CARGA

Los cuatro estados existen como sistema (`.esqueleto*`, `.estado--vacio`, `.estado--error`,
`.estado--parcial`), con tres reglas duras que merecen citarse: el esqueleto **no se pinta por
debajo de 200 ms**; *«un error siempre trae salida»* (`Estados.error` **exige** `reintentar`);
y *«nada celebra sin verificar»*.

| Estado | Tablero | Formulario | Importador |
|---|---|---|---|
| **Cargando** | ✅ captura + esqueleto **en la plantilla**, no en el JS | ⚠️ **sin esqueleto propio** | ✅ `importador-carga.png`, esqueleto con forma de chip |
| **Vacío** | ✅ `vacio-tabla.png` | ✅ `step-fin`, ya separado del error | ⚠️ **no capturado** |
| **Error** | ✅ 2 capturas | ✅ `step-error` con reintento | ✅ con reintento |
| **Parcial** | ✅ `parcial.png` (cae el CDN de Chart.js) | ❌ **no existe** | ❌ **no existe** |

**Hueco M4.** Y hay un dato de método que lo agrava: **las 5 verificaciones en navegador de
`tools/verificar_estados.py` son todas del tablero.** Las otras dos superficies tienen capturas,
no verificación ejecutable.

**Lo que sí es excelente:** *«El esqueleto de la primera carga va en la plantilla, no en el JS.
Es lo único que evita el salto de layout del primer render.»* `templates/dashboard.html` trae
**34 apariciones** de esqueleto en el marcado servido. Esa decisión es la que hace que el CLS
baje de verdad, y está bien razonada.

## 3.4 Eje BREAKPOINTS

| | 320 | 375 | 768 | 1024 | 1440 |
|---|---|---|---|---|---|
| **«Antes» del PR #43** | ✅ | ❌ | ✅ | ❌ | ✅ |
| **«Después»** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Media query en CSS** | — | — | ✅ 640 px | ✅ 1024 px | — |

Desborde horizontal medido: tablero **461 px → 0** a 320; importador **50 chips de 607 fuera de
su caja → 0**. Causa raíz documentada y no obvia: *«`#main` es un elemento flex, y
`min-width: auto` lo ata al ancho mínimo de su contenido»*.

---

# 4. POLÍTICA ANTI-PLANTILLA: 5 CUALIDADES PROBADAS DE 10

El mínimo exigido son 4. Cada una con **dónde se prueba**, como pide el criterio de §0.4.

| # | Cualidad | Prueba |
|---|---|---|
| **1** | **Jerarquía por contraste de escala** | `despues/dashboard-1440.png`: 3 tarjetas grandes + 5 pequeñas donde el «antes» tenía **8 idénticas**. `dashboard.css:57-85`: cifras de 56 / 1.9em / 1.35em, franja de 5 px vs 4 px, dos filas con título propio |
| **5** | **Color semántico, no decorativo** | `dashboard.css:162-169`: cada resultado de llamada con su par banda/texto. `dashboard.js:48-61`: **el color de la gráfica sale de la etiqueta, no de la posición** — antes bastaba que Google reordenara las claves para pintar APROBADO de rojo. 7 familias cromáticas con función |
| **6** | **Estados de interacción diseñados** | Sistema de **dos anillos de foco** con justificación numérica: *«`--azul` da 7.57:1 sobre blanco pero **1.43:1** sobre la barra lateral — invisible justo donde más se navega con teclado»*. Controles inalcanzables con teclado: **4 → 0**. Campos sin nombre accesible: **22 → 0** |
| **9** | **Movimiento que aclara el flujo** | Dos animaciones en todo el sistema, cada una con su porqué. Transiciones de layout **16 → 0**. `prefers-reduced-motion` en 3 bloques **y** en Chart.js vía `matchMedia`, *«porque el CSS no alcanza a lo que se dibuja en `<canvas>`»* |
| **10** | **Datos como parte del sistema** | 11 tokens `--dato-*` que **lee el JavaScript**. Chart.js auto-hospedado (venía de un CDN en `<head>` sin `defer`: **15.1 s** medidos hasta el primer pintado). Terceros por página **245 KB → 0.5 KB** |

**Cualidad 2 (ritmo intencionado): parcial.** Existen 8 tokens de espaciado, pero
`dashboard.css` usa **22 valores `em` literales distintos**, doce de ellos apretados entre
0.65em y 0.88em. Eso no es ritmo: es deriva. Cuenta como hueco B2, no como cualidad.

**Renunciadas a propósito y bien justificadas:** 3 (profundidad), 7 (rompe-rejilla), 8
(textura) — las tres en tensión declarada con el CLS.

## 4.1 Los cuatro defectos prohibidos, buscados a propósito

| Defecto | Veredicto |
|---|---|
| Rejilla de tarjetas uniforme sin jerarquía | ✅ **Corregido.** Era exactamente el estado previo (*«las ocho tarjetas pesaban EXACTAMENTE lo mismo»*) |
| Gris sobre blanco con un acento decorativo | ✅ **No aplica.** 7 familias con función semántica. El único decorativo puro es el degradado de cabecera |
| Radio y sombra idénticos en todo | ⚠️ **Parcial — M1.** Hay escalas (4 radios, 3 sombras), pero el **tablero usa el mismo literal de sombra y el mismo radio de 14 px** para tarjeta, gráfica y tabla |
| **Tarjetas dentro de tarjetas** | ❌ **PRESENTE — B3** |

---

# 5. LOS HUECOS

## 5.1 BLOQUEANTES

### B1 · Las capturas del «después» del tablero están a cero — *tablero*

`docs/diseno/despues/dashboard-1440.png` muestra **todos los KPI en 0** y las dos gráficas
vacías con los ejes de 0.0 a 1.0. Mi captura del «antes» en T4.0, tomada de producción, muestra
**7,180 contactos, 6,148 llamadas, 1,494 aprobados** y las gráficas pobladas.

**Por qué bloquea:** T4.2 es el gate del owner sobre la dirección visual, y se resuelve
comparando antes/después. Con este par, el owner compararía **un panel lleno contra uno
vacío**, y lo que vería no es el rediseño: es la diferencia entre tener datos y no tenerlos. La
jerarquía de tres pesos de cifra —la cualidad nº 1, la principal del rediseño— **no se puede
juzgar sobre tres ceros**.

**Qué lo cierra:** recapturar las tres superficies con datos, con el mismo procedimiento de
anonimización de T4.0. No toca una línea de código.

### B2 · La pantalla principal no usa el sistema de diseño que el PR declara — *tablero y formulario*

El PR construye un sistema de **118 tokens** y luego sus dos superficies principales lo ignoran:

| Archivo | `font-size` | Con token | Sin token |
|---|---:|---:|---:|
| `componentes.css` | 20 | **20** | 0 |
| `importador.css` | 19 | 18 | 1 |
| **`dashboard.css`** | **40** | **2** | **38** |
| **`formulario.css`** | **12** | **0** | **12** |

Y las dos **redeclaran la tipografía contra el ADR**: `body{font-family:'Segoe UI',sans-serif}`
en `dashboard.css:3` y `formulario.css:3`, cuando el ADR decidió una pila de sistema
multiplataforma y `importador.css:20` sí la respeta, con el comentario *«la pila de sistema del
ADR, no la 'Segoe UI' que estaba por omisión»*. **El propio PR sabe cuál es la correcta y la
aplica en una de tres superficies.**

⚠️ **Y no es sólo tipografía: el espaciado va igual.** `componentes.css` usa tokens en **29 de
29** declaraciones de `padding`/`margin`/`gap` e `importador.css` en **50 de 52**; pero
`dashboard.css` va **9 de 86** y `formulario.css` **0 de 31**. La adopción del sistema no es
desigual, es **binaria**: se aplicó al importador y a la librería de componentes, y las otras
dos superficies se quedaron como estaban. Detalle en §8.1.

**Por qué bloquea:** un sistema de diseño que la pantalla principal no usa **no es un sistema,
es documentación**. `--texto-2xl` tiene 1 uso en todo el proyecto y `--texto-3xl` tiene 2. La
siguiente persona que toque el tablero heredará los 22 valores en `em` y la deriva continuará.
Es el riesgo que el propio ADR nombró: *«Swiss mal ejecutado se degrada a "plano otra vez" y no
se notaría el salto»*.

### B3 · Tarjetas dentro de tarjetas, con el mismo tratamiento — *tablero*

Prohibido por las reglas del entorno y por el propio importador, que escribe la intención
contraria (`importador.css:60`: *«separación por filete, no por tarjeta dentro de tarjeta»*).

```
.table-box  → background: var(--superficie) · radius 14px · box-shadow 0 2px 10px rgba(0,71,204,.08)
  └ .men-card → background: var(--superficie) · radius 12px · border · box-shadow 0 1px 6px rgba(0,71,204,.07)
```

Blanco sobre blanco, las dos con sombra azul, la interior además con borde
(`dashboard.css:109` y `:201`, inyectado por `dashboard.js:1428`). Hay más casos con
tratamiento parcial (`.stat` y `.chips-caja` dentro de `.card` del importador), pero ése es el
único con **fondo + sombra dentro de fondo + sombra**.

**Por qué bloquea:** es uno de los cuatro defectos que las reglas prohíben por su nombre, y
está en la pantalla principal.

## 5.2 MEJORAS (no bloquean el gate del owner)

| # | Hueco | Superficie | Detalle |
|---|---|---|---|
| **M1** | La escala de radios y sombras existe pero se esquiva | tablero, formulario | **11 valores distintos** de `border-radius` sobre una escala de 4. Literales sueltos de 3, 4, 6, 7, 8, 10, 12, 14 y 20 px. `--sombra-2` **nunca se usa**; `--sombra-1` y `--sombra-3`, una vez cada uno. El tablero usa el mismo literal de sombra para tarjeta, gráfica y tabla |
| **M2** | `prefers-reduced-motion` colapsa duraciones, pero el `transform` de hover sigue saltando | todas | `.card:hover{transform:translateY(-3px)}`, `.color-opt:hover{scale(1.15)}`, `.bruce-casilla:hover{scale(1.3)}`. Con la preferencia activa el elemento **salta** en vez de animarse. No incumple AA, pero contradice el espíritu |
| **M3** | 5 tokens declarados sin un solo uso | — | `--azul-cian`, `--sombra-2`, `--esp-7`, `--esp-8`, `--linea-suelta` |
| **M4** | `parcial` sólo existe en el tablero; el formulario no tiene esqueleto propio; el importador no tiene `vacio` capturado | formulario, importador | Y **las 5 verificaciones en navegador son todas del tablero** |
| **M5** | El rediseño se construyó contra **606** ciudades; producción ya sirve **1,004** | importador | ✅ **Sin riesgo de CLS**: `.chips-caja` está fija en `min-height:240px; max-height:240px` con scroll, así que no crece. Pero **nunca se ha visto a la escala nueva**, y las 10 menciones a «606» en tests, JS y plantilla son comentarios —ninguna aserción—, así que **no rompen nada**: sólo quedan viejas |
| **M6** | La forma del esqueleto no coincide con la del contenido en Mensajes | tablero | `dashboard.js:1428` sustituye un esqueleto de ~300 px por un `.men-grid` de tarjetas. El propio T4.10 anota `.esqueleto-tarjeta{height:92px}` como «a vigilar a mano» |
| **M7** | Cuatro bloques con `hidden` empujan al aparecer | importador | `.stats-row`, `#progress-box`, `#medidor-box` y `.resultado` no reservan espacio; al arrancar la corrida empujan lo que tengan debajo |
| **M8** | El peor caso de CLS baila entre documentos | — | 0.0284 – 0.0373 según el doc, y **T4.5 da dos valores distintos (0.0286 / 0.0288) para la misma corrida en dos secciones**. Todos cumplen < 0.1, así que no cambia el veredicto; pero una cifra que cambia sin explicación resta credibilidad al resto |
| **M9** | El sistema de movimiento no publica su tabla de duraciones y curvas | — | Los tokens existen en `tokens.css`; ningún documento los tabula |

---

# 6. LO QUE LOS PROPIOS DOCUMENTOS ADMITEN

No es un hallazgo de esta auditoría: está escrito en sus secciones de límites, y **eso es un
punto a favor del PR**. Se recoge para que el owner lo tenga junto:

- **Lectores de pantalla reales** — no verificados. Gate humano.
- **Zoom de texto al 200 %** (SC 1.4.4) — no verificado.
- **`dashboard.js` (1,920 líneas) e `importador.js` (948)** superan el límite de 800 de las
  reglas globales. Es la decisión **D6**, abierta, no un descuido.
- **`?skip=` en `/api/formulario/siguiente`** sigue dando 500 con un valor no numérico.
- **El teléfono no se enmascara en pantalla** — lo que enlaza con el hallazgo de privacidad del
  Plan 1.
- **Seis gates humanos** que ninguna herramienta cierra (anuncio del listbox, los siete
  diálogos y Escape, que las gráficas se lean con sus cifras y no como «canvas»…).
- **Una discrepancia entre dos gates dejada por escrito** en vez de escondida:
  `accessibility-tester` pidió `aria-activedescendant` y contradecía al `a11y-architect` de
  T4.9. Se mantuvo el patrón y se anotó el desacuerdo.
- El PR **corrigió una medición errónea del propio plan**: las tres superficies no sumaban
  5,067 líneas sino 3,235. **Error de 1,839 líneas**, que es lo que hacía inalcanzable el CE1
  original.

---

# 7. QUÉ ENTREGA T4.1 A T4.2

**El gate del owner puede celebrarse**, con una condición previa y una advertencia:

1. **Cerrar B1 antes de enseñar nada.** Recapturar el «después» con datos. Sin eso, la
   comparación no mide el rediseño.
2. **B2 y B3 no bloquean el juicio estético del owner** —son deuda de implementación, no de
   dirección— pero **sí deben cerrarse antes del merge**, y T4.3 es su sitio natural.
3. **Lo que el owner tiene que juzgar es la dirección**, no los huecos: *editorial/Swiss,
   denso y escaneable, sin fuente web, sin profundidad ni textura, con el color como
   significado*. Es una dirección defendible y bien argumentada para una herramienta de uso
   diario, y la auditoría la respalda.

**Lo que esta auditoría NO hace:** no juzga si el rediseño *gusta*. Mide si cumple el encargo
—movimientos, display, pantallas de carga—, si respeta la política anti-plantilla y si lo
declarado está en el código. Lo demás es el gate del owner, y es T4.2.

---

# 8. PUNTUACIÓN POR DIMENSIONES (gate `design-system`)

Se puntúa sólo lo que tiene evidencia medida. Las dimensiones sin dato se declaran como tales
en vez de rellenarse con una impresión.

| # | Dimensión | Nota | Evidencia |
|---|---|:---:|---|
| 1 | **Consistencia de color** | **9** | **0 literales hexadecimales fuera de `tokens.css`** en todo el proyecto (eran 31). Resta 1 por 5 tokens declarados sin uso |
| 2 | **Jerarquía tipográfica** | **4** | Escala de 7 escalones con saltos reales… que la pantalla principal no usa. Ver 8.1 |
| 3 | **Ritmo de espaciado** | **4** | 8 tokens `--esp-1..8`… mismo problema. Ver 8.1 |
| 4 | **Consistencia de componentes** | **5** | Tarjetas dentro de tarjetas (B3); el mismo literal de sombra y radio de 14 px para tarjeta, gráfica y tabla; `.btn-green` del formulario sigue paralelo al sistema (admitido en T4.9) |
| 5 | **Comportamiento responsive** | **9** | Desborde horizontal **461 px → 0** a 320; 5 anchos capturados; causa raíz (`min-width:auto` en flex) documentada |
| 6 | Modo oscuro | **n/a** | No se intentó y no se pedía |
| 7 | **Animación** | **9** | Dos animaciones en todo el sistema, cada una justificada. Transiciones de layout **16 → 0**. `prefers-reduced-motion` en CSS **y** en Chart.js. Resta 1 por M2 (el `transform` de hover salta) |
| 8 | **Accesibilidad** | **9** | Pares de contraste bajo AA **17 → 0**, medidos sobre color **efectivo** (opacidad acumulada y degradados). Controles inalcanzables **4 → 0**. Campos sin nombre **22 → 0**. Foco de dos anillos con justificación numérica |
| 9 | **Densidad de información** | **8** | Apropiada al dominio: denso y escaneable, sin héroe ni relleno decorativo |
| 10 | **Acabado (estados)** | **6** | Los cuatro estados existen como sistema, pero `parcial` sólo llega al tablero y las 5 verificaciones en navegador son todas del tablero (M4) |

## 8.1 El dato que convierte B2 en el hueco estructural

La adopción del sistema **no es pareja: es binaria**. Medido sobre la rama:

| Archivo | `font-size` con token | Espaciado con token |
|---|---|---|
| `componentes.css` | **20 / 20** | **29 / 29** |
| `importador.css` | 18 / 19 | **50 / 52** |
| **`dashboard.css`** | **2 / 40** | **9 / 86** |
| **`formulario.css`** | **0 / 12** | **0 / 31** |

Dicho de otro modo: **el sistema se aplicó al importador y a la librería de componentes, y las
otras dos superficies se quedaron como estaban.** No es que se desviaran un poco — es que
`formulario.css` no usa **ni un solo** token de tipografía ni de espaciado en sus 51 líneas.

**Por qué esto importa más que cualquier detalle estético:** el rediseño no falló en diseñar el
sistema —está bien diseñado, y el importador lo demuestra— sino en **aplicarlo donde el
operador pasa el día**. Y como el resultado *se ve* correcto en las capturas, el hueco es
invisible salvo que alguien cuente, que es lo que ha hecho esta auditoría.

## 8.2 Detección de «AI slop»: negativa

Se buscaron los siete patrones genéricos del catálogo. **Ninguno está presente:** no hay
degradados gratuitos (el único es el de cabecera, declarado como decorativo), no hay morado
sobre azul por defecto, no hay glass morphism, no hay animaciones al hacer scroll, no hay héroe
centrado sobre degradado, y la pila tipográfica es una decisión argumentada —pila de sistema
para evitar el reflow de `font-display:swap`—, no una omisión.

**El rediseño es opinionado y sabe por qué.** Ese no es su problema.
