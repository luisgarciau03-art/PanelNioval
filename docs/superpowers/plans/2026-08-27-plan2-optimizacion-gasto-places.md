# PLAN 2 — OPTIMIZACIÓN DEL GASTO DE LA API DE GOOGLE PLACES

**Fecha de diseño:** 2026-08-27
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie afectada:** `_buscar_negocios` y `_worker_importador` en `app.py:4324-4545`
**Rama de trabajo:** `perf/gasto-places-importador` (desde `main` actualizado — **NUNCA `main`**)
**Decisión del owner (2026-08-27):** el gasto a optimizar es **Google Places (facturable)**
**Baseline verificado el 2026-08-27:** `python -m pytest tests/ -q` → **230 passed**, exit 0

---

## 1. QUÉ SE GASTA HOY Y POR QUÉ

Google Places es **la única API facturable del panel**. Barrido de imports sobre todo el
código: no hay llamadas a APIs de LLM en PanelNioval; Sheets y Telegram son de cuota, no de
factura. La `GMAPS_API_KEY` se cargó en el servidor de producción el 2026-08-27, así que el
gasto empieza a correr ahora — este es el momento correcto de acotarlo.

### 1.1 Los seis desperdicios, con archivo y línea

| # | Desperdicio | Dónde | Por qué cuesta |
|---|---|---|---|
| **D1** | **Place Details sin `fields`** | `app.py:4366` — `det = gmaps_client.place(pid, language='es')['result']` | El cliente `googlemaps` de Python habla con la **Places API legacy**. Sin parámetro `fields`, la respuesta trae todos los grupos de campos y se factura por **todos** ellos (Basic + Contact + Atmosphere), no solo por lo que se usa. Del objeto solo se leen **tres** cosas: `formatted_phone_number`, `website` y `opening_hours.weekday_text` (`app.py:4368-4382`). Todo lo demás — `name`, `formatted_address`, `rating`, `user_ratings_total`, `geometry` — ya venía **gratis** en la respuesta del Text Search y se toma de `lugar`, no de `det`. |
| **D2** | **Se paga Details antes de saber si es duplicado** | `app.py:4366` paga; `app.py:4425-4432` deduplica | El orden está invertido: primero se compra el detalle de cada negocio, y **después** se revisa contra `LISTA DE CONTACTOS` si ya estaba. En una ciudad ya trabajada, la mayor parte de esos Details se tira. Es el desperdicio más caro de los seis. |
| **D3** | **Tres variaciones de query que siempre corren** | `app.py:4332-4336` y `app.py:4392` | Se lanzan `"{cat} en {ciudad}"`, `"{cat} cerca de {ciudad}"` y `"{cat} {ciudad}"`. El `if lugares: break` de la línea 4392 rompe el bucle de **reintentos**, no el de variaciones: las tres corren siempre, aunque la primera ya haya devuelto todo. Con hasta 3 páginas cada una y 2 categorías, son **hasta 18 Text Search por ciudad**. |
| **D4** | **Sin caché de `place_id` → detalle** | no existe | Volver a correr la misma ciudad paga el precio íntegro otra vez. Los datos de una ferretería no cambian de una semana a otra. |
| **D5** | **Hoja completa leída una vez por categoría** | `app.py:4423` — `ws.get_all_values()` dentro de `_exportar_a_sheets` | Cuota de Sheets, no factura, pero se lee la hoja entera dos veces por corrida. Con `--workers 2` el caché de 300 s (`app.py:112-113`) es **por proceso**, así que tampoco ayuda de forma fiable. |
| **D6** | **Cero visibilidad del costo** | no existe | No hay contador de llamadas, ni estimación de costo, ni tope. El owner no puede saber qué costó una corrida ni frenar una que se dispare. Sin medición no hay optimización demostrable. |

### 1.2 Cota superior por ciudad, con las cuentas a la vista

Con `CATEGORIAS_IMPORTADOR = ['Ferreterías', 'Distribuidoras Ferreterías']` (`app.py:4309`):

```
Text Search  = 2 categorías × 3 variaciones × hasta 3 páginas   = hasta 18 llamadas
Place Details= 1 por cada negocio que pase reseñas≥5 y rating≥3.5,
               INCLUIDOS los duplicados que se tirarán después   = N llamadas
```

`N` es el número real que dispara la factura y hoy nadie lo mide.

> **No se ponen precios en este documento.** Las tarifas de Places cambian y citarlas de
> memoria sería inventar un dato. La tarea **T2.0 mide el costo real** en la consola de
> facturación de Google Cloud antes de tocar una línea, y **T2.7 vuelve a medir** después.
> El plan se evalúa contra esa medición, no contra una tabla de precios recordada.

---

## 2. OBJETIVO Y ALCANCE

**Objetivo.** Reducir el costo facturable por corrida del importador **al mínimo que
conserve la calidad del resultado**, y hacer ese costo visible y acotable por el owner.

### En alcance
- Pedir solo los campos que se usan en Place Details.
- Deduplicar **antes** de pagar, no después.
- Cortar variaciones y páginas que no aportan resultados nuevos.
- Caché persistente `place_id` → detalle con TTL.
- Medidor de costo por corrida + tope de presupuesto configurable.
- Reducir las lecturas completas de la hoja.

### Fuera de alcance
- Migrar a la Places API (New) con `FieldMask`. **Se evalúa en T2.1 y se decide en un ADR**;
  si conviene, sale como plan propio. No se hace a mitad de este.
- Bug de conteo y pantallas de carga → **Plan 3**.
- Catálogo y ranking de ciudades → **Plan 1**.

### Criterios de éxito (medibles)

| # | Criterio | Cómo se mide |
|---|---|---|
| CE1 | Existe una medición del costo **antes** | T2.0 deja el número real en el documento, sacado de la consola de facturación |
| CE2 | Place Details pide solo campos usados | Test que afirma que la llamada lleva `fields` y que la lista es exactamente la necesaria |
| CE3 | Cero Details pagados por duplicados ya en la hoja | Test: con una hoja que ya contiene el negocio, `place()` **no se llama** |
| CE4 | Menos Text Search por ciudad | Contador instrumentado: la corrida registra cuántos lanzó; debe bajar frente al baseline |
| CE5 | La segunda corrida de la misma ciudad cuesta mucho menos | Medición A/B: correr una ciudad dos veces; la segunda debe usar el caché |
| CE6 | Reducción del costo total ≥ 60 % | Comparación medida contra CE1, con la **misma ciudad** |
| CE7 | Sin pérdida de calidad | La misma ciudad devuelve el mismo conjunto de negocios aprobados que antes (diff = ∅) |
| CE8 | El owner ve el costo | La UI y el mensaje de Telegram reportan llamadas por SKU y costo estimado |
| CE9 | Existe un tope | Superado el presupuesto de la corrida, el trabajo se detiene y lo reporta; no se corta en silencio |
| CE10 | Baseline sin regresiones | `python -m pytest tests/ -q` ≥ 230 passed |

**CE7 es un gate duro.** Una optimización que ahorra dinero perdiendo prospectos no es una
optimización, es un recorte de producto.

---

## 3. TAREAS

> **Formato blueprint.** Cada tarea es autocontenida: un subagente de Opus en sesión fría la
> ejecuta leyendo solo su bloque.

### T2.0 — Tarea Cero: rama, respaldo y **medición del costo actual** *(bloquea todo)*

**Depende de:** nada. **Bloquea a:** T2.1–T2.8.

**Contexto autocontenido.** Sin un número de partida no se puede demostrar ninguna mejora.
El proyecto es `C:\Users\PC 1\PanelNioval`; `main` tiene auto-deploy, se trabaja en rama.

**Qué hacer.**
1. Crear `perf/gasto-places-importador` desde `main` actualizado.
2. Respaldar las hojas con `python tools/respaldar_hojas.py`; confirmar que el archivo
   **existe** antes de seguir.
3. **Medir el costo real**: en la consola de Google Cloud, en el proyecto dueño de la
   `GMAPS_API_KEY`, obtener el consumo de las SKU de Places (Text Search, Place Details y
   sus grupos de campos) del periodo actual. Anotar: llamadas por SKU y costo.
4. **Corrida controlada de referencia**: elegir una ciudad de tamaño medio, correr el
   importador una vez y anotar el delta de llamadas por SKU que esa corrida produjo. Esa
   ciudad es la **ciudad de referencia** de todo el plan; T2.7 vuelve a correr *esa misma*.
5. Registrar el baseline de tests.

**Salida.** `docs/investigacion/2026-08-27-costo-places-antes.md` con llamadas por SKU,
costo, ciudad de referencia y fecha.

**Criterio de cierre.** El documento tiene números reales de la consola. **Si no se puede
acceder a facturación, la tarea se marca BLOQUEADA y se escala al owner** — el plan no
avanza a ciegas.

---

### T2.1 — Documentación actual del SKU de Places y decisión legacy vs New

**Depende de:** T2.0.

**Contexto autocontenido.** `requirements.txt` fija `googlemaps>=4.10.0`. Ese cliente Python
usa la **Places API legacy** (`client.places()` = Text Search legacy, `client.place()` =
Place Details legacy). La Places API (New) es otro endpoint, con cabecera `FieldMask` y
tarificación distinta. Antes de optimizar hay que saber contra qué API se está optimizando.

**Qué hacer.**
1. Consultar la **documentación vigente** (no la memoria del modelo) sobre:
   - Cómo factura Place Details legacy los grupos de campos y qué hace exactamente el
     parámetro `fields`.
   - Qué campos pertenecen a cada grupo, para saber en cuál caen
     `formatted_phone_number`, `website` y `opening_hours`.
   - Si Text Search legacy cobra por página de `next_page_token`.
   - Qué cambia con Places API (New) + `FieldMask`, y si el cliente `googlemaps` de Python
     la soporta o exige HTTP directo.
2. Escribir un ADR con la decisión: **quedarse en legacy optimizada** (recomendado para este
   plan, cambio de bajo riesgo) o **migrar** (plan aparte, riesgo alto).

**Salida.** `docs/adr/2026-08-27-places-legacy-vs-new.md`.

**Criterio de cierre.** El ADR cita documentación consultada en la sesión, con fecha. Ningún
dato de tarifa o de agrupación de campos sale de memoria.

---

### T2.2 — Place Details: pedir solo los campos que se usan *(el arreglo de una línea)*

**Depende de:** T2.1.

**Contexto autocontenido.** En `app.py:4366`:

```python
det = gmaps_client.place(pid, language='es')['result']
```

Y de `det` solo se leen tres cosas (`app.py:4368-4382`):
- `det.get('formatted_phone_number', '')` — filtro obligatorio: sin teléfono se descarta
- `det.get('website', 'No disponible')`
- `det.get('opening_hours', {}).get('weekday_text', 'No disponible')`

El resto de las columnas exportadas salen de `lugar`, que es la respuesta del Text Search y
ya está pagada.

**Qué hacer.** Añadir `fields=[...]` con exactamente esos tres campos (según los nombres que
T2.1 haya confirmado en la documentación vigente).

**TDD — el test se escribe primero** (`tests/test_costo_places.py`):
- `test_place_details_pide_fields_explicitos` — el mock de `place()` recibe `fields`
- `test_place_details_no_pide_campos_que_nadie_usa` — la lista no incluye `reviews`,
  `photos`, `editorial_summary` ni ningún campo de Atmosphere
- `test_columnas_exportadas_no_cambian` — la fila que llega a Sheets es idéntica a la de
  antes del cambio (protege CE7)

**Gate.** `python-reviewer` + `code-reviewer`.

---

### T2.3 — Deduplicar **antes** de pagar Place Details

**Depende de:** T2.2.

**Contexto autocontenido.** Hoy el orden es: Text Search → **pagar Details** → filtrar por
teléfono → exportar → y ahí, en `_exportar_a_sheets` (`app.py:4425-4432`), recién se
descubre que el negocio ya estaba en la hoja y se descarta. Cada uno de esos descartes es
una llamada de Details ya pagada y tirada.

La clave de deduplicación existente es `f"{fila[1]}|{fila[7]}"`, o sea `Nombre|Dirección`
(`app.py:4429`). Ambos campos vienen del Text Search: `lugar.get('name')` y
`lugar.get('formatted_address')`. **Se pueden comparar sin pagar nada.**

**Qué hacer.**
1. Al arrancar la corrida, leer **una sola vez** las claves existentes de la hoja y
   guardarlas en el estado del trabajo.
2. En `_buscar_negocios`, antes del `place()`, construir la clave desde `lugar` y saltar si
   ya existe. Contarlo como `duplicados`, no como descartado por filtros.
3. Mantener un set de `place_id` **a nivel corrida** (no por categoría) para que un negocio
   que aparece en las dos categorías no se cotice dos veces.

> El punto 3 es el mismo arreglo que el **Plan 3 (T3.3)** necesita para el conteo. Si el
> Plan 3 ya corrió, **reutilizar** la estructura existente, no crear una segunda.

**TDD.**
- `test_no_llama_place_si_el_negocio_ya_esta_en_la_hoja`
- `test_no_llama_place_dos_veces_para_el_mismo_place_id_entre_categorias`
- `test_negocio_nuevo_si_llama_a_place`

**Gate.** `python-reviewer` + `code-reviewer` + `silent-failure-hunter` (un salto de
deduplicación mal puesto descarta prospectos buenos sin avisar — es exactamente CE7).

---

### T2.4 — Cortar variaciones y páginas que no aportan

**Depende de:** T2.3.

**Contexto autocontenido.** `app.py:4332-4336` define tres variaciones de query. El
`if lugares: break` de `app.py:4392` está dentro del bucle `for intento in range(3)` (los
reintentos), no del `for query in variaciones`. Resultado: las tres variaciones se ejecutan
siempre, cada una con hasta 3 páginas.

**Qué hacer.**
1. Medir primero: instrumentar cuántos `place_id` **nuevos** aporta cada variación y cada
   página en la ciudad de referencia. Decidir con el dato, no con la intuición.
2. Regla de corte: si una variación aporta 0 `place_id` nuevos, no se ejecutan las
   siguientes. Si una página aporta 0 nuevos, no se pide la siguiente.
3. El corte y sus umbrales quedan en constantes con nombre, no en números mágicos.
4. **Registrar en el log lo que se cortó.** Un tope silencioso se lee como "cubrí todo"
   cuando no lo hizo.

**TDD.**
- `test_no_lanza_la_segunda_variacion_si_la_primera_no_aporto_nuevos`
- `test_no_pide_la_siguiente_pagina_si_la_actual_no_aporto_nuevos`
- `test_el_log_registra_cada_corte`

**Gate.** `python-reviewer` + `code-reviewer`. **Verificación de CE7 obligatoria**: correr
la ciudad de referencia y comparar el conjunto de negocios aprobados contra el de T2.0. Si
falta alguno, el corte fue demasiado agresivo y se revierte.

---

### T2.5 — Caché persistente `place_id` → detalle

**Depende de:** T2.4.

**Contexto autocontenido.** El caché actual (`app.py:112-113`, `_cache` con `CACHE_TTL=300`)
es un diccionario **en memoria del proceso** y gunicorn corre con `--workers 2`
(`Procfile:1`, `Dockerfile:22`): cada worker tiene el suyo. Para el detalle de Places hace
falta algo que sobreviva al reinicio del contenedor.

**Qué hacer.**
1. Caché en disco (JSON o SQLite) bajo un directorio persistente del contenedor, con TTL
   largo (los datos de una ferretería no cambian semana a semana; el TTL se decide y se
   justifica, se sugiere 30-90 días).
2. Clave = `place_id`. Valor = los tres campos de T2.2 + marca de tiempo.
3. **El caché nunca falla la corrida**: si no se puede leer o escribir, se registra y se
   sigue llamando a la API. Un caché roto degrada el costo, no el servicio.
4. El archivo va a `.gitignore` y a `.dockerignore` — **puede contener teléfonos de
   negocios**, que es dato personal según las reglas del proyecto.

**TDD.**
- `test_segunda_llamada_al_mismo_place_id_no_pega_a_la_api`
- `test_entrada_de_cache_expirada_si_vuelve_a_pegar`
- `test_cache_ilegible_no_rompe_la_corrida`
- `test_el_archivo_de_cache_esta_ignorado_por_git`

**Gate.** `python-reviewer` + `code-reviewer` + **`security-reviewer` obligatorio**: el
caché guarda teléfonos, o sea datos personales en disco.

---

### T2.6 — Medidor de costo por corrida y tope de presupuesto

**Depende de:** T2.5.

**Contexto autocontenido.** Hoy nada cuenta llamadas. El owner recibe un mensaje de Telegram
al terminar (`app.py:4478-4491`) con ciudad, total y tiempo, pero **nada de costo**.

**Qué hacer.**
1. Contador por SKU dentro del estado del trabajo: `text_search`, `place_details`,
   `cache_hits`, `duplicados_evitados`.
2. Estimación de costo con tarifas en **una constante configurable por variable de entorno**
   (`PLACES_COSTO_TEXT_SEARCH`, `PLACES_COSTO_DETAILS`), no hardcodeadas: las tarifas
   cambian y el código no debe mentir cuando cambien.
3. Exponerlo en `/api/importador/estado`, en la UI y en el mensaje de Telegram.
4. **Tope**: `PLACES_PRESUPUESTO_CORRIDA`. Al superarlo, la corrida se detiene, marca estado
   `presupuesto_agotado` y **lo reporta**. No se corta en silencio.

**TDD.**
- `test_contador_suma_una_por_cada_text_search`
- `test_cache_hit_no_suma_al_contador_de_details`
- `test_corrida_se_detiene_al_superar_el_presupuesto`
- `test_estado_reporta_presupuesto_agotado_con_lo_ya_guardado`

**Gate.** `python-reviewer` + `code-reviewer` + `silent-failure-hunter` (el tope es
precisamente un sitio donde algo puede pararse sin que nadie se entere).

---

### T2.7 — Verificación: medir de nuevo y comparar

**Depende de:** T2.2–T2.6.

**Qué hacer.**
1. `python -m pytest tests/ -q` → ≥ 230 passed.
2. **Correr la misma ciudad de referencia de T2.0**, dos veces (la segunda prueba el caché).
3. Sacar de la consola de facturación el delta de llamadas por SKU de cada corrida.
4. Tabla comparativa antes/después: llamadas por SKU, costo, y **% de reducción**.
5. **Verificar CE7**: diff del conjunto de negocios aprobados antes vs. después. Debe ser
   vacío. Si no lo es, se investiga qué optimización lo causó antes de mergear.
6. **Comprobar el medidor en las dos direcciones**: que cuenta una llamada que se sabe que
   ocurrió, **y** que no cuenta una que se sabe que fue cache hit. Un contador plausible y
   equivocado engaña igual que ninguno.

**Salida.** `docs/investigacion/2026-08-27-costo-places-despues.md`.

**Gate.** Si la reducción no llega al 60 % de CE6, **no se bloquea el merge**: se documenta
el número real alcanzado y qué desperdicio quedó sin resolver. Un 45 % medido y honesto vale
más que un 60 % declarado.

---

### T2.8 — Cierre

**Depende de:** T2.7.

**Qué hacer.** Actualizar `CLAUDE.md` (nuevas variables de entorno) y `docs/RUNBOOK.md`
(cómo leer el medidor, cómo ajustar el tope, cómo purgar el caché). Documentar las variables
en `.env.example` **sin valores**. Commits convencionales en español. PR con
`gh pr create --base main`. Handoff.

**Gate de merge.** Baseline verde + reviews sin CRITICAL/HIGH abiertos.

---

## 4. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T2.0 | `claude-mem:mem-search` | skill | claude-mem | Ya hay observaciones sobre el despliegue de `GMAPS_API_KEY` y sobre los endpoints de Places verificados en producción el 2026-08-27. |
| A | T2.0 | `benchmark` | skill | ECC | Medir la línea base y detectar regresiones antes/después de un PR: es exactamente lo que exige CE1. |
| A | T2.0 | `cost-tracking` **[OPCIONAL]** | skill | community | *Condición:* si el owner quiere además el gasto agregado en un tablero, no solo el delta de esta corrida. |
| A | T2.1 | `documentation-lookup` | skill | ECC | Documentación **vigente** de la API vía Context7, no la memoria del modelo. Obligatorio: las tarifas y los grupos de campos cambian. |
| A | T2.1 | `docs-lookup` | agente | catalogo-agentes | Recupera la referencia de la API con ejemplos de código, complementando la skill. |
| A | T2.0 | `Explore` | agente | built-in | Barrido para confirmar que Places es la única API facturable y que no hay otro consumidor oculto. |
| B | T2.1 | `architecture-decision-records` | skill | ECC | Congelar la decisión legacy-vs-New con las alternativas descartadas. |
| B | T2.1 | `council` | skill | community | Migrar de API o no es un go/no-go con tradeoff real: riesgo alto contra ahorro incierto. Panel de 4 voces. |
| B | T2.0–T2.6 | `blueprint` | skill | community | Brief autocontenido por paso para que un agente frío ejecute cualquiera. |
| B | T2.4 | `benchmark-optimization-loop` | skill | ECC | El corte de variaciones se decide midiendo variantes, no por intuición. Es la skill diseñada para ese bucle. |
| C | T2.2–T2.6 | `superpowers:test-driven-development` | skill | superpowers | Todo cambio de este plan es verificable con un test que cuenta llamadas: RED antes de tocar. |
| C | T2.2–T2.6 | `tdd-guide` | agente | catalogo-agentes | Hace cumplir tests-primero y cobertura. |
| C | T2.2–T2.6 | `python-pro` | agente | catalogo-agentes | Implementación idiomática en el stack real del proyecto. |
| C | T2.4, T2.5 | `performance-optimizer` | agente | catalogo-agentes | Identificar el cuello real y no optimizar lo que no pesa. El sujeto del plan es su especialidad. |
| C | T2.5 | `content-hash-cache-pattern` | skill | ECC | Patrón de caché con invalidación automática y capa de servicio separada — justo la forma que necesita el caché de `place_id`. |
| C | T2.5 | `data-throughput-accelerator` **[OPCIONAL]** | skill | ECC | *Condición:* si tras T2.4 el cuello resulta ser la lectura de la hoja (D5) y no las llamadas a Places. |
| C | T2.6 | `backend-patterns` | skill | ECC | Forma del payload del medidor y manejo de error del tope. |
| D | T2.2–T2.6 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack, se suma al code-reviewer. |
| D | T2.2–T2.6 | `code-reviewer` | agente | catalogo-agentes | Obligatorio tras escribir o modificar código. |
| D | T2.5, T2.6 | `security-reviewer` | agente | catalogo-agentes | Obligatorio: el caché persiste teléfonos de negocios (dato personal) y el plan añade variables de entorno. |
| D | T2.3, T2.4, T2.6 | `silent-failure-hunter` | agente | catalogo-agentes | Deduplicación, corte de variaciones y tope de presupuesto son los tres sitios donde algo puede descartarse sin avisar. Es su especialidad exacta. |
| D | T2.2–T2.6 | `python-testing` | skill | ECC | pytest, mocks del cliente `googlemaps`, parametrización de los contadores. |
| D | T2.7 | `ads-math` | skill | **claude-ads** | Calculadora financiera de CPA y break-even que funciona con datos pegados y sin acceso a API. Traduce el delta de facturación a **costo por prospecto aprobado**, que es el número que el owner necesita para decidir. Es la lectura de negocio de CE6. |
| D | T2.7 | `pr-test-analyzer` | agente | catalogo-agentes | Confirma que los tests miden comportamiento (llamadas evitadas), no solo que el código corre. |
| D | T2.7 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: la reducción se declara con la salida del comando delante, no de memoria. |
| D | T2.7 | `production-audit` **[OPCIONAL]** | skill | community | *Condición:* antes de desplegar el tope de presupuesto al VPS, auditoría de qué se rompe en producción si el tope se dispara a media corrida. |
| E | T2.8 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md`, RUNBOOK y `.env.example` al día. |
| E | T2.8 | `github-ops` | skill | ECC | PR con historial completo y formato convencional. |
| E | T2.8 | `superpowers:finishing-a-development-branch` | skill | superpowers | Decide merge / PR / cleanup con los gates puestos. |
| E | T2.8 | `handoff` | skill | skills-local (ver nota §4.1) | Contexto comprimido para la siguiente sesión. |

**Fuentes canónicas usadas: 6 de 6** — catalogo-agentes, ECC, claude-ads, community,
claude-mem, superpowers, más built-in.

### 4.1 Nota sobre `skills-local`

El Nivel 2 de la biblioteca usa la etiqueta `skills-local`, que no es una de las 6 fuentes
canónicas de la tabla de Fuentes. Se reporta tal cual y **no cuenta** para el mínimo de
diversidad; el plan lo cumple sin ella.

---

## 5. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewer del stack | code-reviewer | security-reviewer | Baseline |
|---|---|---|---|---|---|
| T2.0 | — (mide y registra) | — | — | — | ✅ anota el número |
| T2.1 | — (ADR con docs citadas) | — | — | — | — |
| T2.2 | ✅ TDD, 3 tests | python-reviewer | ✅ | — | ✅ sin regresiones |
| T2.3 | ✅ TDD, 3 tests + silent-failure-hunter | python-reviewer | ✅ | — | ✅ sin regresiones |
| T2.4 | ✅ TDD, 3 tests + **verificación CE7** | python-reviewer | ✅ | — | ✅ sin regresiones |
| T2.5 | ✅ TDD, 4 tests | python-reviewer | ✅ | ✅ teléfonos en disco | ✅ sin regresiones |
| T2.6 | ✅ TDD, 4 tests | python-reviewer | ✅ | ✅ variables de entorno | ✅ sin regresiones |
| T2.7 | ✅ suite completa + medición A/B + diff CE7 | ✅ | ✅ | ✅ | ✅ ≥230 passed |
| T2.8 | ✅ suite completa antes del merge | — | ✅ | — | ✅ verde para mergear |

---

## 6. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | **Optimizar de más y perder prospectos** | Media | **Crítico** — el importador deja de servir | CE7 es gate duro en T2.4 y T2.7: diff vacío del conjunto aprobado contra la ciudad de referencia | `git revert` del commit de la optimización culpable; cada una va en su propio commit para poder revertirlas por separado |
| R2 | `fields` mal nombrado devuelve menos de lo que se cree y el teléfono llega vacío | Media | Alto — todos los negocios se descartan por "sin teléfono" | T2.1 confirma los nombres en la documentación vigente; el test de T2.2 afirma que la fila exportada no cambia | Revertir T2.2, que es un cambio de una línea |
| R3 | No hay acceso a la consola de facturación | Media | Alto — no se puede medir | T2.0 se marca **BLOQUEADA** y se escala al owner. Alternativa: instrumentar contadores en código y estimar. No se avanza a ciegas | — |
| R4 | El caché sirve datos rancios (una ferretería cerró) | Media | Medio | TTL justificado + botón de purga documentado en el RUNBOOK | Borrar el archivo de caché: es reconstruible |
| R5 | El archivo de caché se commitea con teléfonos dentro | Baja | **Alto** — dato personal en el repo | `.gitignore` y `.dockerignore` **en el mismo commit** que crea el caché, más el test `test_el_archivo_de_cache_esta_ignorado_por_git` | Si ocurre: el archivo se retira al respaldo fechado y se limpia el historial con clon completo previo |
| R6 | El tope de presupuesto corta una corrida a mitad y deja la hoja inconsistente | Media | Medio | El estado reporta `presupuesto_agotado` **con lo ya guardado**; las filas escritas antes del corte son válidas | Subir `PLACES_PRESUPUESTO_CORRIDA` y volver a correr; el dedup evita duplicar lo ya escrito |
| R7 | Solapamiento con Plan 3 (dedup por corrida) | **Alta** | Bajo | T2.3 dice explícitamente que si el Plan 3 ya corrió, se reutiliza su estructura | — |

**Rollback general.** Rama `perf/gasto-places-importador`, **un commit por optimización**
(T2.2, T2.3, T2.4, T2.5, T2.6 separados) para poder revertir la culpable sin perder las
otras. El caché en disco no se borra al revertir: se aparta.

---

## 7. EVALUACIÓN DE LA SUITE claude-ads

**Se evalúa y se usa.** `ads-math` entra en la etapa D de T2.7 con uso real, no decorativo:
es una calculadora de CPA, ROAS y break-even que funciona con datos pegados y sin acceso a
API, y traduce el delta de facturación de Places al número que le importa al owner —
**cuánto cuesta cada prospecto aprobado, antes y después**. Sin esa traducción, CE6 es un
porcentaje técnico; con ella, es una decisión de negocio.

El resto de la suite (`ads-google`, `ads-meta`, `ads-tiktok`, `audit-*`, `copy-writer`,
`visual-designer`, `creative-strategist`, `format-adapter`) presupone cuentas
publicitarias, píxeles y creatividades. PanelNioval no compra medios: el importador es
prospección en frío sobre Google Places. No aplica, y esta es la constancia por escrito.

---

## 8. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T2.0 | Tarea Cero: rama, respaldo y medición del costo actual | 🚫 **BLOQUEADA** (importe) · **HECHA** (conteo) | Sin `gcloud`, cuenta de servicio solo con Sheets/Drive, sin navegador → **escalada al owner**. Sustituida por conteo exacto de llamadas: `tools/medir_llamadas_places.py` · `docs/investigacion/2026-08-28-costo-places-antes.md` · respaldo `docs/auditoria/respaldos/2026-08-28/` | 2026-08-28 |
| T2.1 | Docs del SKU de Places + ADR legacy vs New | **HECHA** | `2bb1980` · ADR `docs/adr/2026-08-28-places-legacy-vs-new.md`, con la documentación citada y fechada y verificada además contra el cliente instalado | 2026-08-28 |
| T2.2 | Place Details con `fields` explícitos | **HECHA** | `2bb1980` · 326 passed · deja de facturar Basic (26 campos) y Atmosphere (18) | 2026-08-28 |
| T2.3 | Deduplicar antes de pagar Details | **HECHA** | `2bb1980` · **ciudad ya trabajada: 80 → 0 Place Details** · gates python-reviewer + silent-failure-hunter: 0 CRITICAL/HIGH, 4 MEDIUM corregidos | 2026-08-28 |
| T2.4 | Cortar variaciones y páginas sin aporte | **HECHA** | `ba18bd9` · 335 passed · **Text Search 18 → 13** · 3 cortes, todos por aporte MEDIDO de cero · gates python-reviewer (1 HIGH corregido, verificado en las dos direcciones) + code-reviewer APPROVE · ⚠️ **CE7 sin verificar** (necesita corrida real: gate del owner); los dos cortes con riesgo se desactivan con una constante | 2026-08-28 |
| T2.5 | Caché persistente `place_id` → detalle | **HECHA** | `031f0f5` · 344 passed · **2ª corrida de la misma ciudad: 80 → 0 Place Details** · ahorra sobre todo a los RECHAZADOS sin teléfono, que nunca llegan a la hoja y se repagaban indefinidamente · TTL 30 d · gate security-reviewer: 0 CRITICAL/HIGH, 2 correcciones (poda real en disco, 0600 + O_EXCL) | 2026-08-28 |
| T2.6 | Medidor de costo y tope de presupuesto | PENDIENTE | | |
| T2.7 | Verificación: medición A/B + diff de calidad | PENDIENTE | | |
| T2.8 | Cierre: docs, PR, handoff | PENDIENTE | | |

**Avance del plan: 6 / 9 tareas (67 %)** · T2.0 bloqueada en su mitad monetaria
