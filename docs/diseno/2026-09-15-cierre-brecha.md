# CIERRE DE LA BRECHA — movimiento, estados y los huecos de T4.1

**Tarea:** Plan 4 · T4.3 · **Fecha:** 2026-09-16 · **Rama:** `feat/plan4-cierre-brecha` (desde `feat/rediseno-panel`)
**Depende de:** T4.2, aprobado **«tal cual»** y sin ajustes pedidos por el negocio.

---

## 1. Lo primero que apareció: **la rama del PR #43 tenía la suite en rojo**

Antes de tocar nada, el baseline:

```
1 failed, 899 passed, 2 skipped
FAILED tests/test_plan4_accesibilidad.py::TestElPanelNoDependeDeUnCdnParaPintar
       ::test_el_archivo_es_exactamente_el_que_se_reviso
```

Y el proyecto no mergea con la suite en rojo. **El PR llevaba así desde el 4 de septiembre sin
que nadie lo viera**, porque el fallo **sólo ocurre en Windows**.

### 1.1 La causa

El propio `.gitattributes` que el PR añadió declara `* text=auto`, y sus excepciones binarias
cubren imágenes y ZIP pero **no `.js`**. Así que el Chart.js auto-hospedado se normaliza:

| | CRLF | LF | bytes | sha256 |
|---|---:|---:|---:|---|
| Blob en git | 0 | 20 | 205,222 | `0e2326c68680…` ✅ |
| **En disco, en Windows** | **20** | 0 | **205,242** | `106b7562318f…` ❌ |

El test hashea **el archivo en disco**. En el runner de Linux el checkout es LF y pasa; en la
máquina del owner es CRLF y falla.

**Lo que lo hace grave no es el rojo: es qué test era.** El que garantiza que el archivo de
terceros del repo es **exactamente el que se descargó y se revisó**. Un guardián de integridad
que falla siempre en la máquina donde se mira acaba tratado como ruido, y entonces deja de
guardar nada.

### 1.2 El arreglo

Una línea en `.gitattributes`:

```
static/js/vendor/** binary
```

Un artefacto de terceros **nunca** se normaliza: tiene que quedarse byte a byte como se
descargó. Tras el re-checkout, el archivo en disco vuelve a 205,222 bytes y su sha256 coincide.

**Baseline tras el arreglo: 900 passed, 2 skipped.** Que es, exactamente, la cifra que el PR
declaraba en su documentación — medida en una máquina donde el test sí pasaba.

---

## 2. CE3 — el criterio de cierre de esta tarea, verde con la lista delante

**Barrido de `static/css/*.css`.** Las reglas del entorno permiten animar sólo `transform`,
`opacity`, `clip-path` y `filter` con moderación; prohíben `width`, `height`, `top`, `left`,
`margin`, `padding` y `font-size` porque sacan el trabajo del compositor.

| `@keyframes` | Archivo | Anima |
|---|---|---|
| `esqueleto-brillo` | `componentes.css` | `transform` |
| `fila-entra` | `componentes.css` | `transform` |
| `seccion-entra` | `componentes.css` | `opacity`, `transform` |
| `fadeIn` | `formulario.css` | `opacity`, `transform` |

**Propiedades animadas en todo el proyecto: `transform` y `opacity`. Prohibidas: ninguna.**

`transition: all`: **cero**. Las dos apariciones del texto son comentarios que explican que se
retiró.

**CE3 queda verde y no hubo nada que corregir** — el trabajo ya estaba bien hecho en T4.6.

---

## 3. B5 · El buscador ignora los acentos — **corregido**

El hueco de mayor daño de T4.1: el filtro hacía `toLowerCase()` y nada más, así que teclear
`leon` no encontraba `León`.

**TDD.** Cuatro tests en `tests/test_plan4_importador.py::TestElBuscadorIgnoraLosAcentos`; tres
fallaron antes del cambio y el cuarto —la guarda de rendimiento— pasó desde el principio, que
es lo que debía.

**El arreglo**, en `static/js/importador.js`:

```js
function sinAcentos(s) {
  return String(s == null ? '' : s)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}
```

Aplicada en **las dos puntas** —al construir `buscable` y una vez sobre lo tecleado—, porque
normalizar un solo lado no sirve de nada. Es la gemela de `normalizar()` que el generador de
catálogo ya tenía en Python.

### 3.1 La optimización de T4.9 se respeta

El coste de una pulsación bajó de **713 ms a 3.1 ms** en T4.9 precisamente por no recorrer el
catálogo en cada tecla. `sinAcentos()` se llama **una vez por chip al construir** y **una por
pulsación**, nunca dentro del bucle. Hay un test que lo fija.

⚠️ **Se modificó un test preexistente**, y conviene decir por qué: `test_el_texto_buscable_se_calcula_al_construir`
medía esa invariante contando `toLowerCase` en el filtro. El arreglo desplazó esa llamada dentro
de `sinAcentos()`. **La invariante es la misma y se sigue midiendo igual** —una sola llamada—;
lo que cambió es el proxy. Se conservó la intención y se añadió una comprobación extra de que no
queda ninguna conversión suelta fuera.

### 3.2 Verificación funcional, que ningún test de string puede dar

Los tests de este archivo afirman sobre el **texto** del JS, porque el CI sólo tiene Python. Eso
demuestra que el código dice lo que debe, **no que funcione**. Así que se ejecutó la
`sinAcentos()` real —extraída del archivo— con Node contra el catálogo real:

```
  leon               -> León, Guadalupe, Nuevo León
  merida             -> Mérida
  queretaro          -> Querétaro, San Juan del Río, Querétaro
  nezahualcoyotl     -> Nezahualcóyotl
  torreon            -> Torreón
  san luis potosi    -> San Luis Potosí
  juarez             -> Juárez, Chihuahua, Naucalpan de Juárez
  cuauhtemoc         -> Cuauhtémoc, Ciudad de México, Cuauhtémoc, Chihuahua
  LEON               -> León, Guadalupe, Nuevo León
  '  Merida  '       -> Mérida
  tehuacan           -> Tehuacán
  culiacan           -> Culiacán

  control negativo 'zzzqqq' -> 0 resultados
  ciudades con acento: 203 | alcanzables sin teclear tilde: 203
```

Las 12 encuentran su ciudad, incluidas mayúsculas y con espacios alrededor, **y el control
negativo devuelve cero** — el barrido se comprobó en las dos direcciones.

⚠️ **Sobre el 203 contra el 319:** esta rama todavía trae el catálogo de **606** ciudades,
porque el PR #43 se apiló sobre el Plan 1 antes de su ampliación. En producción son **1,004
ciudades y 319 con acento**. El arreglo sirve igual para las dos: no depende del tamaño.

---

## 4. B3 · Tarjetas dentro de tarjetas — **corregido**

`.men-card` nacía con fondo, borde **y sombra** dentro de `.table-box`, que ya tiene fondo y
sombra. Blanco sobre blanco con dos sombras azules apiladas.

**Se retira la sombra de la interior y se conserva su filete izquierdo**, que es lo que la
distingue y lo que el propio sistema declara (`importador.css`: *«separación por filete, no por
tarjeta dentro de tarjeta»*).

Tres tests lo fijan, **uno de ellos como control negativo**: que `.table-box` **sí** conserve la
suya. La elevación no desaparece; se queda donde corresponde.

---

## 5. B4 · El CLS de interacción — **medido, y RETIRADO**

El hueco decía que las 9 cifras del PR miden el desplazamiento **al cargar** y que los cuatro
bloques con `hidden` del importador empujarían el layout al pulsar «Buscar». Era una hipótesis
razonable —la planteó el gate de `ux-researcher` y yo la acepté— y **nadie la había medido**.

**Medida ahora**, reproduciendo lo que hace la app (quitarles el `hidden`) en vez de gastar una
corrida real de Places, 3 pasadas por punto:

| Superficie | Ancho | CLS de carga | **CLS de interacción** |
|---|---:|---:|---:|
| importador | 1440 | 0.0050 | **0.0000** |
| importador | 320 | 0.0271 → 0.0000 | **0.0000** |

**No reproduce, y el DOM explica por qué.** Los cuatro bloques —`progress-box` (línea 89),
`stats-row` (99), `medidor-box` (124), `result-box` (138)— están **todos por debajo** del campo
de búsqueda (77). **No hay nada debajo de ellos.** Al aparecer extienden la página hacia abajo;
no mueven nada. Y un salto de layout exige que algo se mueva.

**B4 queda RETIRADO.** El hueco real no era el comportamiento: era la **ausencia de evidencia**.
Ahora existe, y **CE6 puede firmarse también sobre la interacción**, no sólo sobre la carga.

---

## 6. B2 · El sistema de diseño en el tablero y el formulario — **NO se cierra aquí**

Es el único de los cinco que queda, y **se declara sin hacer en vez de despacharlo mal**.

**El tamaño real:**

| Archivo | `font-size` con token | Espaciado con token |
|---|---|---|
| `dashboard.css` | 2 / 40 | 9 / 86 |
| `formulario.css` | 0 / 12 | 0 / 31 |

Son **~160 sustituciones** sobre las dos superficies que el operador usa a diario, y muchas no
son mecánicas: `0.65em`, `0.68em`, `0.7em`, `0.72em`… no caen en escalones limpios de la escala,
así que cada una es una **decisión de a qué escalón redondear**.

**Por qué no se hace en esta pasada, dicho como es:** un reemplazo masivo sin comparación visual
antes/después es exactamente la forma de romper un rediseño que el owner acaba de aprobar. Y la
herramienta para compararlo —`tools/comparar_capturas.py`, que el propio PR trae— merece usarse
en condiciones, no de pasada al final de una tarea larga.

**Qué hace falta para cerrarlo bien:**

1. Capturar el «antes» con `capturar_superficies.py --sinteticos` sobre esta rama.
2. Sustituir por escalones, archivo por archivo, empezando por `formulario.css` (51 líneas, 43
   sustituciones) que es el más pequeño y el de mayor tráfico.
3. Recapturar y **comparar píxel a píxel** con `comparar_capturas.py`.
4. Y de paso, las dos redeclaraciones de `'Segoe UI'` que contradicen al ADR —
   `dashboard.css:3` y `formulario.css:3` — mientras `importador.css:20` sí lo respeta.

**No bloquea el gate del owner** (ya está dado) **pero sí bloquea el merge**, y sigue en pie.

---

## 7. Estado de los huecos de T4.1 tras esta tarea

| | Hueco | Estado |
|---|---|---|
| **B5** | El buscador no normaliza acentos | ✅ **Corregido** y verificado funcionalmente |
| **B3** | Tarjetas dentro de tarjetas | ✅ **Corregido** con control negativo |
| **B4** | CLS de interacción sin medir | ✅ **Medido: 0.0000. RETIRADO** |
| **B2** | El sistema no llega al tablero ni al formulario | ⏳ **Abierto**, con plan escrito |
| **🆕** | La suite de la rama estaba en rojo en Windows | ✅ **Corregido** (`.gitattributes`) |

**Baseline: 907 passed, 2 skipped** (900 tras arreglar el rojo + 7 tests nuevos).

---

## 8. Lo que esta tarea NO hace

- **No cierra B2** (§6), ni las 8 mejoras de la auditoría.
- **No rebasa el PR #43 sobre `main`.** Sigue `CONFLICTING` en `CLAUDE.md`, **a propósito**: su
  versión reintroduce las afirmaciones falsas sobre Railway que el cierre del Plan 1 corrigió.
  Es trabajo de **T4.4**, y al resolverlo hay que conservar la versión de `main`.
- **No verifica nada en navegador con lector de pantalla.** Sigue siendo gate humano.
- **No toca el catálogo de esta rama**, que sigue en 606 ciudades hasta el rebase de T4.4.
