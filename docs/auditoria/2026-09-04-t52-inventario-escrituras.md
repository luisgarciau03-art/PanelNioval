# T5.2 — Inventario de escrituras a Google Sheets (M14)

**Fecha:** 2026-09-04 · **Rama:** `fix/endurecimiento-panel` · **Tarea:** T5.2

El plan pide este inventario como entregable, no solo como paso previo: «Este inventario es
la salida de la tarea tanto como el código».

---

## 1. Lo que cambió respecto a lo que el plan suponía

El plan decía, en su paso 2:

> «Los valores generados por el propio panel (timestamps, contadores) no lo necesitan, pero
> pasarlos por el escape **no hace daño** y evita tener que razonar caso por caso.»

**Eso es falso para las escrituras `RAW`, y aplicarlo habría corrompido datos.** La
documentación de gspread lo dice de su propio parámetro:

> `ValueInputOption.raw` — *The values will not be parsed by Sheets API and will be stored
> as-is. For example, formulas will be rendered as plain [text].*

Dos consecuencias, y las dos importan:

1. Una escritura `RAW` **ya es inmune** a la inyección de fórmulas. No hay nada que cerrar.
2. El escape antepone un apóstrofo, que en `USER_ENTERED` es la marca de «esto es texto» y
   no se almacena. En `RAW` **no se interpreta**: se guardaría como un carácter más del
   dato, y se vería en la celda.

Así que T5.2 escapa **solo** donde el `value_input_option` efectivo es `USER_ENTERED`.

## 2. Cuál es el `value_input_option` efectivo, que no es el que parece

Medido sobre **gspread 6.2.1** (lo instalado; `requirements.txt` pide `gspread>=5.12.0`).

| Llamada | Opción efectiva | ¿Inyectable? |
|---|---|---|
| `append_row` / `append_rows` sin opción | **RAW** (defecto de gspread) | No |
| `insert_row` / `insert_rows` sin opción | **RAW** | No |
| `update` / `batch_update` **sin opción** | **RAW** | No |
| `update_cell` / `update_acell` | **USER_ENTERED** | **Sí** |
| Explícito `'RAW'` | RAW | No |
| Explícito `'USER_ENTERED'` | USER_ENTERED | **Sí** |

⚠️ **Esta tabla dijo primero que `update`/`batch_update` sin opción eran `USER_ENTERED`. Era
falso.** `raw: bool = True` es el defecto del parámetro y gana cuando no se pasa
`value_input_option`, así que resuelven a **RAW**. El error venía de *leer* el fuente de
gspread —donde la cadena `user_entered` aparece, pero en la rama que exige `raw=False`— en
vez de ejecutarlo. El invariante se comprueba ahora **ejecutando** una escritura contra una
worksheet falsa y mirando el `valueInputOption` que sale.

No cambia ninguna de las 17 escrituras reales, porque todas las `update`/`batch_update` de
`app.py` pasan la opción explícita. Sí cambiaba la clasificación de una escritura *futura*:
darla por `USER_ENTERED` habría hecho que CE5 **exigiera escaparla**, y escapar una `RAW`
guarda el apóstrofo en la celda — el guarda habría forzado la corrupción que el resto de la
suite existe para evitar.

⚠️ **`update_cell` es la trampa.** No admite `value_input_option`: lo fija a `USER_ENTERED`
en su propio cuerpo. Leyendo `app.py` no se ve ninguna opción, lo que hace parecer que es
el caso seguro, y es justo el contrario.

Estos defectos son de una librería que el repo **no fija de versión**, así que
`tests/test_endurecimiento_escape_formulas.py::TestSupuestosSobreGspread` los convierte en
invariante: si una versión futura los cambia, la suite se rompe ruidosamente en vez de
desactivar el escape en silencio.

## 3. Las 17 escrituras reales

`E` = escapa ahora · `—` = no lo necesita (RAW o valor del panel)

| # | `app.py` | Método | Ruta Flask | Opción | Origen | ¿Escapa? |
|---|---|---|---|---|---|---|
| 1 | 471 | `update_cell` | `POST /api/ventas/update-pago-url` | USER_ENTERED | usuario (`url_existente`) | **E** |
| 2 | 532 | `update_cell` | `POST /api/ventas/upload-pago` | USER_ENTERED | tercero (ImgBB) | **E** |
| 3 | 941 | `batch_update` | `POST /api/seguimiento/update` | USER_ENTERED | usuario, **sin allowlist** | **E** |
| 4 | 974 | `update` | `POST /api/mensajes/update` | USER_ENTERED | usuario (`Contenido`) | **E** |
| 5 | 3073 | `update_cell` | *ninguna — código muerto* | USER_ENTERED | constante `'Llamado'` | — |
| 6 | 3133 | `batch_update` | `POST /api/formulario/guardar` | RAW | usuario (casi todo el body) | — |
| 7 | 3154 | `append_row` | varias de `/api/bruce/*` | RAW | constante (encabezados) | — |
| 8 | 3203 | `append_row` | `POST /api/bruce/agregar` | RAW | usuario | — |
| 9 | 3230 | `batch_update` | `POST /api/bruce/actualizar` | USER_ENTERED | usuario, **sin allowlist** | **E** |
| 10 | 3323 | `batch_update` | `POST /api/formulario/telefono` | RAW | usuario, saneado a dígitos | — |
| 11 | 3357 | `batch_update` | `POST /api/formulario/correo` | RAW | usuario, validado + `_sanitizar_correo` | — |
| 12 | 3389 | `append_row` | `POST /api/catalogo/encolar` | RAW | constante | — |
| 13 | 3439 | `append_row` | `POST /api/catalogo/encolar` | RAW | usuario (`tienda`, `conclusion`) | — |
| 14 | 3526 | `batch_update` | `POST /api/catalogo/corregir-numero` | RAW | usuario, normalizado | — |
| 15 | 3551 | `batch_update` | `POST /api/catalogo/corregir-numero` | RAW | usuario, normalizado | — |
| 16 | 3595 | `batch_update` | `POST /api/catalogo/reintentar` | RAW | panel | — |
| 17 | 5116 | `append_rows` | hilo de `/api/importador/iniciar` | USER_ENTERED | usuario + Places | **E** (ya estaba) |

**Antes de T5.2 escapaba 1 de 17. Ahora escapan las 6 que lo necesitan** (1, 2, 3, 4, 9, 17);
las 11 restantes son `RAW` o escriben constantes.

### Falsos positivos del patrón ingenuo

`grep` de los nombres de método da 24 coincidencias; **8 no son escrituras**, porque
`.update(` es también método de `dict` y de `set`:

`app.py:51` (`app.config.update`), `148` (`_cache.clear()`), `333` (`all_keys.update`),
`5076`, `5119` (sets), `5203` (`cache_places.update`), y las líneas `5117` y `5483`, que son
comentarios.

Por eso el test de CE5 clasifica **por objeto receptor**, no por nombre de método — y falla
si aparece un receptor que no esté clasificado, en vez de ignorarlo.

## 4. Hallazgo fuera del alcance del plan, corregido porque bloqueaba la tarea

**`app.py:974` estaba roto con la versión instalada de gspread.**

Hasta gspread 5.x la firma era `update(range_name, values)`. En 6.x es
`update(values, range_name)`. La llamada usaba el orden viejo, así que pasaba la celda como
valores y la lista como rango. Con `gspread>=5.12.0` sin fijar, un `pip install` nuevo trae
6.2.1 y **`/api/mensajes/update` deja de escribir**.

Se corrigió porque escapar fórmulas en una llamada que no escribe no protege nada: el
criterio CE4 («toda escritura a Sheets escapa fórmulas») habría quedado cumplido *de nombre*
sobre una ruta muerta. El test usa una worksheet falsa que **impone la firma real de
gspread 6**; con un `MagicMock` cualquiera el orden daría igual y el test no mediría nada.

## 4.1 Riesgo residual de las escrituras RAW — no está «cerrado»

`security-reviewer` señaló que decir «las RAW ya son inmunes» **sobreclama**, y tiene razón.
RAW es seguro *en el punto de escritura*. El texto sigue guardado, y se reactiva si algo
aguas abajo lo reinterpreta:

- **Exportar a CSV o XLSX y reabrir en Excel.** El CSV no lleva metadato de «esto es texto»,
  así que un campo que empiece por `=`, `+`, `-` o `@` se ejecuta al abrirlo. La hoja
  `Respuestas de formulario 1` la escribe `/api/formulario/guardar` con RAW y texto de
  usuario sin sanear, y el personal la abre a diario.
- **Un ciclo RAW → `USER_ENTERED` dentro del propio panel.** El patrón ya existe:
  `/api/bruce/agregar` escribe con RAW y `/api/bruce/actualizar` con `USER_ENTERED`,
  **sobre las mismas columnas de la misma hoja**. Un valor guardado como texto plano se
  convierte en fórmula viva en cuanto alguien lo edita desde la segunda ruta.

O sea que la asimetría de `/api/bruce/*` no es solo fea: es la prueba de que ese camino
existe dentro del código, no una hipótesis. Sigue siendo correcto **no** aplicar el escape en
RAW (guardaría el apóstrofo en el dato), pero la mitigación real es sanear en la entrada, y
eso no lo hace T5.2.

## 5. Lo que este inventario deja abierto

- **Inconsistencia en `/api/bruce/*`:** `agregar` (#8) escribe con `RAW` y `actualizar` (#9)
  con `USER_ENTERED`, sobre la misma hoja. El mismo texto es seguro al crearlo y fórmula al
  editarlo. T5.2 lo cierra escapando #9, pero la asimetría de fondo sigue ahí.
- **Dos rutas escriben sin allowlist** (#3 y #9): cualquier clave del body que coincida con
  un encabezado llega a una celda. El escape impide la fórmula, no la escritura de campos no
  previstos. Es una superficie distinta y no la cierra T5.2.
- **`#5` es código muerto** (`marcar_contacto_procesado`, sin ningún llamador en el repo).
  Queda anotado como excepción con motivo en el test, no borrado: nada se borra.
- **Ningún módulo importado por `app.py` escribe a Sheets.** `worker_catalogo.py` y
  `envio_catalogo.py` sí escriben, pero solo se importan desde `worker_catalogo_run.py`, que
  corre en la PC del owner.

### 5.1 Dos CRITICAL preexistentes que T5.2 **no** cierra — necesitan tarea propia

`security-reviewer` los marcó CRITICAL y no son de este cambio: ya estaban. El escape impide
la **fórmula**, no la **escritura arbitraria**. Se reportan aquí porque el inventario es el
sitio donde constan, y porque el contexto de amenaza es real: el token del panel es
compartido y el panel está expuesto en internet.

1. **Sin allowlist de columnas ni cota superior de fila** — `/api/seguimiento/update`
   (`app.py:946`) y `/api/bruce/actualizar` (`app.py:3248`). Escriben *cualquier* clave del
   body que coincida con un encabezado, y `_row` no tiene tope. Con el token se puede:
   - **Sobrescribir la fila 1 (los encabezados).** Todo el sistema resuelve columnas por
     `headers.index(nombre)`, así que romper la fila 1 rompe en silencio cada lectura y
     escritura futura de esa hoja, para todo el personal.
   - Escribir columnas que la interfaz no expone, con solo acertar el nombre del encabezado.
   - Escribir en una fila absurdamente alta y expandir la grilla. `seguimiento` y `bruce`
     comparten spreadsheet, y el límite de celdas es del archivo entero: inflar una pestaña
     puede romper los `append_row` de las demás.

2. **`/api/mensajes/update` (`app.py:992`) es una primitiva de escritura de celda
   arbitraria.** `_row` y `_col` son índices crudos del body, sin cota y sin pasar siquiera
   por nombre de encabezado. Y esa hoja es la que alimenta **los teléfonos y plantillas que
   `envio_catalogo.py` envía por WhatsApp a clientes reales**.

**Corrección propuesta** (fuera de T5.2): allowlist explícita de columnas editables por ruta,
y cota `2 <= fila <= ws.row_count` / `1 <= col <= ws.col_count`, con 400 fuera de rango.
Encaja de forma natural con **T5.1**, que ya va a tocar todas las rutas para el rate
limiting. **Decisión del owner:** ampliar T5.1 o abrir una tarea T5.8.
