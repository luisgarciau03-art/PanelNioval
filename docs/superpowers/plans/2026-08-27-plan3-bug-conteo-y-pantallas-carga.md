# PLAN 3 — BUG DE CONTEO EN EL SHEET Y PANTALLAS DE CARGA DEL IMPORTADOR

**Fecha de diseño:** 2026-08-27
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie afectada:** `/importador`, `/api/importador/*`, `_worker_importador`, `_exportar_a_sheets`
**Rama de trabajo:** `fix/conteo-importador-y-estados-carga` (desde `main` actualizado — **NUNCA `main`**)
**Baseline verificado el 2026-08-27:** `python -m pytest tests/ -q` → **230 passed**, exit 0

> **Este plan se ejecuta PRIMERO de los cuatro.** Razón en §2.4.

---

## 1. LOS BUGS, CON CAUSA RAÍZ Y LÍNEA EXACTA

El owner reportó dos síntomas: *"dice agregados al sheet 20 pero realmente nomás aparecen
10"* y *"bugs en las pantallas de carga"*. La lectura del código encuentra **nueve defectos
distintos** detrás de esos dos síntomas. Se listan con su evidencia; ninguno es hipótesis
sin línea que la sostenga.

### 1.1 Síntoma A — el número no coincide con lo que llega a la hoja

**B1 · El contador cuenta aprobados de Places, no filas escritas.**
`app.py:4525`: `_import_job['encontrados'] += len(resultados)`. `resultados` son los
negocios que pasaron los filtros de Places (reseñas ≥5, rating ≥3.5, con teléfono). El
número de filas que **de verdad** se escriben es `nuevos`, que sale de
`nuevos = _exportar_a_sheets(...)` en `app.py:4519` — y ese número **solo aparece en la
línea de log** (`app.py:4527-4529`). Nunca llega a un contador. La UI muestra `encontrados`
en el recuadro verde rotulado "Encontrados" (`app.py:4696`) y en el mensaje final escribe
*"N contactos encontrados · … · Guardados en Google Sheets"* (`app.py:4917-4918`), que se
lee como "N guardados". **No lo son.**

**B2 · Duplicados contra la hoja: la primera brecha.**
`_exportar_a_sheets` deduplica por `Nombre|Dirección` contra lo que ya hay en
`LISTA DE CONTACTOS` (`app.py:4425-4432`). Todo negocio que ya estaba se descarta ahí —
después de haber sido contado en `encontrados`. En una ciudad ya trabajada, esta sola
brecha explica un 20 contra 10.

**B3 · Duplicados entre categorías: la segunda brecha.**
`_buscar_negocios` mantiene `vistos` (`app.py:4329`) **por categoría**. Una ferretería que
aparece tanto en `'Ferreterías'` como en `'Distribuidoras Ferreterías'` se cuenta **dos
veces** en `encontrados` (`todos.extend(resultados)` en `app.py:4520`, sin deduplicar entre
categorías), mientras que `_exportar_a_sheets` de la segunda categoría **sí** la rechaza,
porque vuelve a leer la hoja y ya la ve escrita. Doble conteo garantizado.

**B4 · Fallo silencioso en la escritura.**
`_exportar_a_sheets` envuelve todo en `try/except Exception` y en el `except` hace
`print(...)` y **`return 0`** (`app.py:4471-4474`). Si Sheets devuelve un error de cuota, de
permisos o de red, la función devuelve 0, el worker sigue como si nada, `encontrados` queda
intacto y la corrida termina en `status: 'done'` con un ✅. **Cero filas escritas, éxito
reportado.** El `print` va a stdout del contenedor, donde el owner no mira.

### 1.2 Síntoma B — las pantallas de carga

**B5 · CAUSA RAÍZ: el estado del trabajo vive en memoria de proceso y hay dos procesos.**
`_import_job` es un diccionario a nivel módulo (`app.py:4311`) y gunicorn arranca con
`--workers 2` (`Procfile:1` y `Dockerfile:22`). El `POST /api/importador/iniciar` aterriza
en el worker A y lanza el hilo ahí (`app.py:4574`). Los `GET /api/importador/estado` que
llegan cada 3 s (`app.py:4878`) se reparten entre los dos workers: **la mitad interroga al
worker B**, que tiene su propio `_import_job` en `status: 'idle'`, `progreso: 0`,
`encontrados: 0`.

Eso produce exactamente lo que el owner ve: la barra salta a 0 %, "Encontrados" parpadea a
0, y la corrida "nunca termina" porque el `status: 'done'` del worker A solo lo ve la mitad
de los sondeos. **El mismo defecto afecta a `_cache`** (`app.py:112-113`): el `_cache.pop`
de un worker no invalida el del otro, así que el badge de caché del dashboard también miente
la mitad de las veces.

**B6 · La barra de progreso tiene tres valores posibles.**
`_import_job['progreso'] = i` con `i` el índice de la categoría (`app.py:4510`). Con dos
categorías, el progreso solo vale 0, 1 o 2 → 0 %, 50 %, 100 %. Durante toda la primera
categoría, que son minutos, la barra está en **0 %** y parece congelada.

**B7 · Recargar la página pierde el trabajo de vista.**
Solo `iniciar()` arranca el sondeo (`app.py:4878`). Si el operador recarga `/importador` a
media corrida, la UI aparece inerte: sin barra, sin log, sin stats. Y si vuelve a pulsar
Buscar, recibe *"Ya hay una búsqueda en curso"* (`app.py:4564`) sin ninguna forma de ver esa
búsqueda. Queda encerrado fuera de su propio trabajo.

**B8 · El botón se queda trabado y el sondeo no para nunca.**
`iniciar()` hace `await fetch(...)` sin `try/catch` (`app.py:4870-4874`): si la red falla,
la promesa revienta, el botón se queda en `⏳ Buscando...` deshabilitado para siempre y hace
falta recargar. `actualizarEstado()` tampoco tiene `try/catch` y `setInterval` no para si el
estado se queda en `'idle'` — p. ej. tras reiniciar el contenedor — así que sondea cada 3 s
indefinidamente.

### 1.3 Defecto adicional encontrado de camino

**B9 · Interpolación insegura del nombre de ciudad.**
`app.py:4840`: ``onclick="seleccionarCiudad('${c.ciudad}',this)"``. Los nombres de ciudad
vienen de `LISTA DE CONTACTOS`, escritos a mano. Un apóstrofo rompe el handler; una comilla
bien puesta inyecta. El propio codebase ya reconoce esta clase de bug: el comentario de
`app.py:2064` dice *"Escape HTML para columnas de texto plano (datos de hoja/importador
Places): cierra XSS almacenado"*. Ese escape existe en el dashboard y **falta aquí**.

---

## 2. OBJETIVO, ALCANCE Y ORDEN

**Objetivo.** Que el número que ve el operador sea el número de filas que hay en la hoja, que
un fallo de escritura se vea, y que la pantalla de progreso refleje el estado real del
trabajo aunque haya dos workers y aunque se recargue la página.

### 2.1 En alcance
Los nueve defectos B1–B9, con test de regresión cada uno.

### 2.2 Fuera de alcance
- Rediseño visual del importador → **Plan 4** (este plan arregla el **comportamiento** de
  las pantallas de carga; el Plan 4 les cambia el **aspecto**).
- Reducción de costo de Places → **Plan 2**.
- Catálogo y ranking de ciudades → **Plan 1**.

### 2.3 Criterios de éxito (medibles)

| # | Criterio | Cómo se mide |
|---|---|---|
| CE1 | El número que ve el operador es el que hay en la hoja | Corrida real en ciudad con duplicados conocidos: `nuevos_en_sheet` de la UI == filas añadidas contadas en la hoja |
| CE2 | Los cuatro números son distintos y están rotulados | La UI muestra `encontrados`, `nuevos_en_sheet`, `duplicados`, `descartados` sin ambigüedad |
| CE3 | Ningún negocio se cuenta dos veces entre categorías | Test: el mismo `place_id` en ambas categorías suma 1, no 2 |
| CE4 | Un fallo de escritura llega al operador | Test: `_exportar_a_sheets` lanza → estado `error` con la causa real, no `done` |
| CE5 | El estado es correcto con 2 workers | Prueba de integración con gunicorn `--workers 2`: 20 sondeos seguidos, ninguno devuelve `idle` con el trabajo corriendo |
| CE6 | La barra avanza de forma continua y monótona | Test: la secuencia de `progreso` es no decreciente y tiene >3 valores distintos |
| CE7 | Recargar no pierde el trabajo | Prueba en navegador: recargar a media corrida restaura barra, stats y log |
| CE8 | El botón nunca queda trabado | Test: fetch que falla → el botón vuelve a estar habilitado con mensaje de error |
| CE9 | El sondeo termina | Test: estado `idle` inesperado durante N ciclos → el sondeo para y avisa |
| CE10 | Nombres de ciudad escapados | Test: una ciudad llamada `O'Brien` renderiza y es clicable |
| CE11 | Baseline sin regresiones | `python -m pytest tests/ -q` ≥ 230 passed |

### 2.4 Por qué este plan va primero

**B5 hace que cualquier trabajo de UI sea inverificable.** Mientras el estado se reparta
entre dos workers, no hay forma de distinguir "la pantalla de carga nueva está mal" de "me
tocó el worker equivocado". El Plan 4 rediseñaría a ciegas. Y el Plan 2 necesita la
deduplicación por corrida (T3.3) que este plan construye. Orden: **3 → 2 → 1 → 4**.

---

## 3. TAREAS

> **Formato blueprint.** Cada tarea es autocontenida: un subagente de Opus en sesión fría la
> ejecuta leyendo solo su bloque.

### T3.0 — Tarea Cero: rama, respaldo y **reproducción documentada** *(bloquea todo)*

**Depende de:** nada. **Bloquea a:** T3.1–T3.10.

**Contexto autocontenido.** El proyecto es `C:\Users\PC 1\PanelNioval`. `main` tiene
auto-deploy: se trabaja en rama. Antes de arreglar hay que **reproducir**: un arreglo sin
reproducción previa no se puede verificar.

**Qué hacer.**
1. Crear `fix/conteo-importador-y-estados-carga` desde `main` actualizado.
2. `python tools/respaldar_hojas.py`; confirmar que el respaldo **existe** antes de seguir.
3. Reproducir B1/B2/B3: correr el importador sobre una ciudad **que ya tenga contactos en la
   hoja**, anotar el número que muestra la UI y contar a mano las filas nuevas reales.
   Documentar la diferencia.
4. Reproducir B5: con gunicorn `--workers 2`, lanzar una corrida y sondear
   `/api/importador/estado` 20 veces seguidas. Anotar cuántas respuestas vinieron con
   `status: 'idle'`. **Esa proporción es la prueba del bug.**
5. Registrar el baseline de tests.

**Salida.** `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md`.

**Criterio de cierre.** Los dos síntomas reproducidos con números anotados. Si B5 no se
reproduce, se investiga por qué antes de seguir: puede que el balanceo no sea round-robin y
la causa raíz sea otra.

---

### T3.1 — Confirmar cada hipótesis antes de tocar código

**Depende de:** T3.0.

**Contexto autocontenido.** §1 de este documento lista nueve defectos deducidos leyendo el
código. Deducir no es confirmar. Antes de escribir un arreglo hay que probar que cada causa
raíz es la causa raíz.

**Qué hacer.** Depuración sistemática de cada defecto: hipótesis → experimento mínimo que la
distinga de sus alternativas → resultado. En particular:
- B5: confirmar que el `POST` y el `GET` aterrizan en PIDs distintos (registrar `os.getpid()`
  temporalmente en el log de ambos endpoints).
- B4: forzar una excepción en `_exportar_a_sheets` y comprobar que la corrida termina en
  `done` con ✅.
- B3: encontrar un `place_id` real que aparezca en las dos categorías.

Además, recorrer **todos** los botones y toques de `/importador` trazando su secuencia
completa de cambios de estado, para cazar defectos donde cada función funciona por separado
pero el estado final queda mal.

**Salida.** `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md` ampliado, con una
tabla Defecto · Hipótesis · Experimento · Confirmado/Descartado.

**Criterio de cierre.** Los nueve defectos con veredicto. Un defecto **descartado** también
es resultado válido y se documenta.

---

### T3.2 — Separar los contadores *(arregla B1 y B2)*

**Depende de:** T3.1.

**Contexto autocontenido.** Hoy hay un solo número, `encontrados`, y significa "aprobados
por los filtros de Places". Se necesitan cuatro números independientes:

| Contador | Significa | De dónde sale |
|---|---|---|
| `encontrados` | negocios que pasaron los filtros de Places | `len(resultados)` |
| `nuevos_en_sheet` | **filas realmente escritas** | valor de retorno de `_exportar_a_sheets` |
| `duplicados` | ya estaban en `LISTA DE CONTACTOS` | `len(resultados) - nuevos` |
| `descartados` | rechazados por reseñas, rating o falta de teléfono | `sum(stats.values())` (ya existe) |

**Qué hacer.**
1. Añadir los contadores al estado del trabajo y a `/api/importador/estado`.
2. En la UI, cuatro recuadros con rótulos que no se puedan malinterpretar. El **número
   grande y destacado es `nuevos_en_sheet`**: es el que responde a la pregunta del operador.
3. Reescribir el mensaje final. Hoy dice *"N contactos encontrados · … · Guardados en Google
   Sheets"*, que miente por yuxtaposición. Debe decir cuántos se guardaron, cuántos ya
   estaban y cuántos se descartaron, cada uno con su número.

**TDD — tests primero** (`tests/test_importador_conteo.py`):
- `test_nuevos_en_sheet_refleja_filas_escritas`
- `test_duplicados_se_reportan_por_separado_de_descartados`
- `test_encontrados_no_se_presenta_como_guardados`
- `test_estado_expone_los_cuatro_contadores`

**Gate.** `python-reviewer` + `code-reviewer`.

---

### T3.3 — Deduplicar entre categorías *(arregla B3)*

**Depende de:** T3.2.

**Contexto autocontenido.** `vistos` es local a `_buscar_negocios` (`app.py:4327`), o sea
por categoría. Hace falta un set de `place_id` **a nivel corrida**.

**Qué hacer.**
1. Set de `place_id` en el estado del trabajo, compartido por todas las categorías.
2. Un negocio ya visto en la corrida no se vuelve a procesar ni a contar.
3. Registrar en el log cuántos se saltaron por aparecer en más de una categoría — es
   información útil sobre el solapamiento de las dos búsquedas, no ruido.

> **Solapamiento con el Plan 2 (T2.3).** El Plan 2 necesita este mismo set para no pagar
> Place Details dos veces. Este plan lo construye primero; el Plan 2 lo reutiliza. **No se
> crean dos estructuras.**

**TDD.**
- `test_mismo_place_id_en_dos_categorias_cuenta_una_vez`
- `test_el_log_reporta_los_saltados_por_solapamiento`

**Gate.** `python-reviewer` + `code-reviewer`.

---

### T3.4 — Que un fallo de escritura se vea *(arregla B4)*

**Depende de:** T3.2.

**Contexto autocontenido.** `app.py:4471-4474`:

```python
except Exception as e:
    print(f'[importador] sheets error: {e}')
    traceback.print_exc()
    return 0
```

Devolver 0 hace indistinguible "no había nada nuevo que escribir" de "la escritura explotó".

**Qué hacer.**
1. `_exportar_a_sheets` **propaga** la excepción en vez de devolver 0.
2. El worker la captura, pone el trabajo en `status: 'error'` con la causa real y **conserva
   lo ya escrito**: si la primera categoría se guardó y la segunda falló, eso se dice.
3. El error llega a la UI y al mensaje de Telegram. Hoy Telegram solo se manda en el camino
   feliz (`app.py:4533`); debe mandarse también cuando algo falla.
4. **Nada de valores por defecto silenciosos**: 0 filas escritas por error nunca puede
   presentarse igual que 0 filas escritas porque no había nada nuevo.

**TDD.**
- `test_excepcion_de_sheets_pone_el_trabajo_en_error`
- `test_error_conserva_el_conteo_de_lo_ya_escrito`
- `test_cero_filas_por_error_se_distingue_de_cero_filas_por_nada_nuevo`
- `test_telegram_avisa_tambien_cuando_falla`

**Gate.** `python-reviewer` + `code-reviewer` + **`silent-failure-hunter`** (esta tarea es
literalmente su especialidad).

---

### T3.5 — Estado compartido entre workers *(arregla B5 — la causa raíz)*

**Depende de:** T3.1.

**Contexto autocontenido.** `_import_job` (`app.py:4311`) y `_cache` (`app.py:112`) son
globales de proceso. Gunicorn corre `--workers 2` en `Procfile:1` y `Dockerfile:22`. Los
sondeos se reparten y la mitad ve un estado vacío.

**Tres opciones, con su tradeoff:**

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| **A** | `--workers 1 --threads 4` | Una línea. Cero código nuevo | Un solo proceso: si se traba, se traba el panel entero. Reduce el aislamiento que dan 2 workers |
| **B** | Estado en archivo/SQLite con lock, en volumen persistente | Sobrevive al reinicio. Arregla también `_cache`. El VPS ya corre un solo contenedor | Hay que escribir el lock bien. `worker_catalogo_run.py` ya tiene un patrón de lock en este repo del cual partir |
| **C** | Redis | La solución de libro | Un servicio más que operar en el VPS, para un panel interno de un puñado de usuarios |

**Recomendación: B.** Sobrevive a reinicios, arregla `_cache` de paso, y no añade
infraestructura al VPS. El repo ya resolvió locks huérfanos en `worker_catalogo_run.py`
(hay 10 tests de eso en la suite): se reutiliza ese aprendizaje.

**Qué hacer.**
1. Someter la decisión a un panel estructurado antes de implementar — es un go/no-go real.
2. Registrarla en un ADR.
3. Implementar la elegida, con lock y con manejo de lock huérfano (proceso muerto que dejó
   el lock puesto).
4. Aplicar la misma solución a `_cache` para que el badge deje de mentir.

**Salida.** `docs/adr/2026-08-27-estado-compartido-importador.md`.

**TDD.**
- `test_dos_procesos_leen_el_mismo_estado`
- `test_lock_huerfano_de_proceso_muerto_se_libera`
- `test_estado_sobrevive_al_reinicio`
- `test_escritura_concurrente_no_corrompe_el_estado`

**Gate.** `python-reviewer` + `code-reviewer` + `security-reviewer` (si el estado va a
archivo, ese archivo lleva nombres y ciudades de prospectos: `.gitignore`, `.dockerignore` y
permisos). **Verificación obligatoria con gunicorn `--workers 2` real**, no solo con tests
unitarios: el bug solo se manifiesta con dos procesos de verdad.

---

### T3.6 — Progreso real y continuo *(arregla B6)*

**Depende de:** T3.5.

**Contexto autocontenido.** `progreso = i` (`app.py:4510`) da 3 valores con 2 categorías.

**Qué hacer.**
1. Granularidad por **categoría × variación × página**: con 2 categorías, 3 variaciones y
   hasta 3 páginas hay hasta 18 pasos, más los pasos de exportación.
2. Etiqueta de fase legible: *"Ferreterías — variación 2 de 3, página 1"*, *"Guardando en
   Sheets…"*.
3. La barra **nunca retrocede**: el progreso es monótono no decreciente. Si el total
   estimado cambia (porque una variación se cortó), se ajusta el denominador sin que la
   fracción baje.
4. Al empezar la primera categoría el progreso ya no es 0: hay un paso de arranque.

> **Solapamiento con el Plan 2 (T2.4).** El Plan 2 corta variaciones que no aportan. Cuando
> se ejecute, el denominador de progreso deja de ser fijo. Esta tarea debe implementar el
> denominador **ajustable desde el principio** para que el Plan 2 no tenga que rehacerla.

**TDD.**
- `test_progreso_es_monotono_no_decreciente`
- `test_progreso_tiene_mas_de_tres_valores_distintos`
- `test_denominador_se_ajusta_sin_que_la_fraccion_baje`
- `test_la_etiqueta_de_fase_nombra_categoria_variacion_y_pagina`

**Gate.** `python-reviewer` + `code-reviewer`.

---

### T3.7 — Frontend robusto *(arregla B7, B8, B9)*

**Depende de:** T3.5, T3.6.

**Contexto autocontenido.** El JS del importador (`app.py:4860-4945`) sondea cada 3 s
(`app.py:4878`), no restaura estado al cargar, no maneja errores de red y no escapa nombres
de ciudad (`app.py:4840`).

**Qué hacer.**
1. **Restaurar estado al cargar.** Al abrir `/importador`, consultar
   `/api/importador/estado`; si hay un trabajo corriendo, mostrar barra, stats y log, y
   arrancar el sondeo. El operador nunca vuelve a quedar encerrado fuera de su trabajo.
2. **`try/catch` en las dos llamadas.** Un fallo de red muestra un aviso y **rehabilita el
   botón**. Nunca queda trabado.
3. **Sondeo con retroceso y con final.** Intervalo creciente al alargarse la corrida; si el
   estado llega `idle` inesperadamente N ciclos seguidos (contenedor reiniciado), el sondeo
   para y lo dice.
4. **Botón de cancelar.** `POST /api/importador/cancelar` que marca el trabajo como
   cancelado; el worker lo comprueba entre pasos y sale limpio conservando lo ya escrito.
5. **Escapar el nombre de ciudad.** Sustituir la interpolación de `app.py:4840` por
   `dataset` + listener delegado. Nada de nombres de la hoja dentro de un atributo HTML.

> El punto 5 es también hallazgo del **Plan 1 (T1.7)**. Quien llegue primero lo arregla; el
> otro **verifica y no duplica**.

**TDD + verificación en navegador.**
- `test_estado_se_restaura_al_cargar_con_trabajo_en_curso`
- `test_fallo_de_red_rehabilita_el_boton`
- `test_sondeo_para_tras_n_ciclos_en_idle`
- `test_cancelar_detiene_el_worker_conservando_lo_escrito`
- `test_ciudad_con_apostrofo_renderiza_y_es_clicable`
- Verificación funcional real: recargar a media corrida y confirmar que se restaura.

**Gate.** `code-reviewer` + **`security-reviewer` obligatorio** (interpolación en HTML de
datos que vienen de la hoja de clientes) + `silent-failure-hunter` (los `catch` nuevos son
sitios donde un error puede quedarse tragado).

---

### T3.8 — Verificación de extremo a extremo

**Depende de:** T3.2–T3.7.

**Qué hacer.**
1. `python -m pytest tests/ -q` → ≥ 230 passed, sin regresiones.
2. **La prueba que responde al reporte del owner**: correr el importador sobre una ciudad
   con duplicados conocidos y comprobar que `nuevos_en_sheet` de la UI **es igual** al número
   de filas que aparecieron en `LISTA DE CONTACTOS`. Contar las filas de verdad, no confiar
   en el log.
3. Repetir la prueba de los 20 sondeos de T3.0 con gunicorn `--workers 2`: **cero**
   respuestas `idle` mientras el trabajo corre.
4. Recargar la página a media corrida: la UI se restaura.
5. Provocar un fallo de Sheets a propósito: la corrida termina en `error` con la causa, no
   en ✅.
6. **Comprobar los contadores en las dos direcciones**: que cuentan un duplicado que se sabe
   que existe, **y** que no cuentan como duplicado un negocio que se sabe nuevo. Un contador
   plausible y equivocado engaña igual que ninguno.

**Gate.** Los seis puntos con salida de comando pegada en la tabla PROGRESO. Nada se declara
resuelto por inspección visual.

---

### T3.9 — Cierre

**Depende de:** T3.8.

**Qué hacer.** Actualizar `CLAUDE.md` (baseline nuevo, nota sobre el estado compartido),
`docs/RUNBOOK.md` (qué significa cada contador, cómo cancelar una corrida, dónde vive el
estado). Commits convencionales en español (`fix:` y `test:`). PR con
`gh pr create --base main`. Handoff.

**Gate de merge.** Baseline verde + reviews sin CRITICAL/HIGH abiertos. Nada se mergea con
la suite en rojo.

---

## 4. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T3.0, T3.1 | `superpowers:systematic-debugging` | skill | superpowers | Obligatorio ante cualquier bug **antes** de proponer fixes: hipótesis → experimento → veredicto. Nueve defectos deducidos leyendo código necesitan confirmación, no fe. |
| A | T3.1 | `debugger` | agente | catalogo-agentes | Diagnóstico de causa raíz sobre logs y trazas; complementa a la skill de proceso con criterio de especialista. |
| A | T3.1 | `click-path-audit` | skill | community | Traza **cada botón** de `/importador` por su secuencia completa de cambios de estado. Diseñada exactamente para bugs donde cada función funciona y el estado final queda mal — que es B7 y B8. |
| A | T3.0 | `claude-mem:mem-search` | skill | claude-mem | El proyecto ya tiene la observación *"Critical Bug: Sheet Record Count Mismatch in Importer Panel"* y otra que sitúa la causa en `_worker_importador`. Recuperarlas ahorra la mitad de T3.1. |
| A | T3.1 | `Explore` | agente | built-in | Barrido para encontrar todos los consumidores de `_import_job` y `_cache` sin quemar contexto. |
| A | T3.0 | `error-detective` **[OPCIONAL]** | agente | catalogo-agentes | *Condición:* si los logs del contenedor en el VPS tienen histórico de errores de Sheets que confirmen B4 en producción. |
| B | T3.5 | `council` | skill | community | Estado compartido: A, B o C es un go/no-go con tradeoff real de operación. Panel de 4 voces, no la primera idea. |
| B | T3.5 | `architecture-decision-records` | skill | ECC | Congela la decisión y las dos alternativas descartadas. |
| B | todas | `blueprint` | skill | community | Brief autocontenido por paso para ejecución en frío. |
| B | T3.5 | `architect` **[OPCIONAL]** | agente | catalogo-agentes | *Condición:* si se elige la opción C (Redis) y hay que diseñar la topología en el VPS. |
| C | T3.2–T3.7 | `superpowers:test-driven-development` | skill | superpowers | Cada bug se convierte en un test que falla antes de arreglarlo. Es la única forma de saber que el arreglo arregla. |
| C | T3.2–T3.7 | `tdd-guide` | agente | catalogo-agentes | Hace cumplir tests-primero y vigila cobertura. |
| C | T3.2–T3.6 | `python-pro` | agente | catalogo-agentes | Implementación idiomática en Flask + Python 3.11, que es el stack real. |
| C | T3.2–T3.7 | `orch-fix-defect` | skill | ECC | Pipeline prehecho para corrección de defecto: reproducir como test que falla → arreglar a verde → review → commit con gate. Es exactamente la forma de este plan. |
| C | T3.5 | `docker-patterns` | skill | ECC | El estado compartido toca volúmenes y el `Dockerfile`; patrones de volumen y de arranque del contenedor. |
| C | T3.5 | `deployment-patterns` | skill | ECC | Si la opción elegida cambia el arranque de gunicorn, hay que tocar `Procfile` y `Dockerfile` sin romper el despliegue del VPS. |
| C | T3.7 | `frontend-patterns` | skill | ECC | Restauración de estado, sondeo con retroceso y listeners delegados. |
| C | T3.4, T3.7 | `error-handling` | skill | ECC | Patrones de error tipado, propagación y mensajes de cara al usuario: el corazón de B4 y B8. |
| D | T3.2–T3.7 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack; se suma al code-reviewer. |
| D | T3.2–T3.7 | `code-reviewer` | agente | catalogo-agentes | Obligatorio tras escribir o modificar código. |
| D | T3.4, T3.7 | **`silent-failure-hunter`** | agente | catalogo-agentes | **La herramienta central de este plan.** B4 es un `return 0` que traga excepciones; los `catch` nuevos de T3.7 pueden crear más. Caza errores tragados, fallbacks malos y propagación faltante. |
| D | T3.5, T3.7 | `security-reviewer` | agente | catalogo-agentes | Obligatorio: el estado va a disco con datos de prospectos, y la UI interpola nombres de la hoja en HTML. |
| D | T3.2–T3.7 | `python-testing` | skill | ECC | pytest, mocks de gspread, fixtures de estado concurrente. |
| D | T3.7, T3.8 | `webapp-testing` | skill | skills-local (ver nota §4.1) | La restauración al recargar y el botón trabado solo se prueban en navegador real. |
| D | T3.8 | `browser-qa` | skill | ECC | Verificación visual e interactiva de la UI tras el despliegue. |
| D | T3.8 | `pr-test-analyzer` | agente | catalogo-agentes | ¿Los tests cubren el comportamiento reportado por el owner, o solo que el código corre? |
| D | T3.8 | `qa-expert` **[OPCIONAL]** | agente | catalogo-agentes | *Condición:* si tras T3.8 se quiere una estrategia de QA para todo el importador, no solo para estos nueve defectos. |
| D | T3.8 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: la salida del comando delante antes de declarar nada resuelto. |
| D | T3.8 | `verification-loop` | skill | ECC | Verificación de sesión completa antes del PR. |
| E | T3.9 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md` y RUNBOOK al día con los contadores nuevos. |
| E | T3.9 | `github-ops` | skill | ECC | PR con historial completo y formato convencional. |
| E | T3.9 | `superpowers:finishing-a-development-branch` | skill | superpowers | Decide merge / PR / cleanup con los gates puestos. |
| E | T3.9 | `claude-mem:babysit` **[OPCIONAL]** | skill | claude-mem | *Condición:* si el PR queda esperando CI o review. |
| E | T3.9 | `handoff` | skill | skills-local (ver nota §4.1) | Contexto comprimido para la siguiente sesión. |

**Fuentes canónicas usadas: 5 de 6** — catalogo-agentes, ECC, community, claude-mem,
superpowers, más built-in. **claude-ads no aplica**; justificación en §7.

### 4.1 Nota sobre `skills-local`

El Nivel 2 de la biblioteca usa la etiqueta `skills-local`, que no es una de las 6 fuentes
canónicas. Se reporta tal cual y **no cuenta** para el mínimo de diversidad; el plan lo
cumple sin ella.

---

## 5. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewer del stack | code-reviewer | security-reviewer | silent-failure-hunter | Baseline |
|---|---|---|---|---|---|---|
| T3.0 | — (reproduce y registra) | — | — | — | — | ✅ anota el número |
| T3.1 | — (veredicto por defecto) | — | — | — | — | — |
| T3.2 | ✅ TDD, 4 tests | python-reviewer | ✅ | — | — | ✅ sin regresiones |
| T3.3 | ✅ TDD, 2 tests | python-reviewer | ✅ | — | — | ✅ sin regresiones |
| T3.4 | ✅ TDD, 4 tests | python-reviewer | ✅ | — | ✅ **obligatorio** | ✅ sin regresiones |
| T3.5 | ✅ TDD, 4 tests + prueba con 2 workers reales | python-reviewer | ✅ | ✅ estado en disco | — | ✅ sin regresiones |
| T3.6 | ✅ TDD, 4 tests | python-reviewer | ✅ | — | — | ✅ sin regresiones |
| T3.7 | ✅ TDD, 5 tests + navegador | — | ✅ | ✅ **obligatorio** | ✅ | ✅ sin regresiones |
| T3.8 | ✅ los 6 puntos con salida pegada | ✅ | ✅ | ✅ | ✅ | ✅ ≥230 passed |
| T3.9 | ✅ suite completa antes del merge | — | ✅ | — | — | ✅ verde para mergear |

---

## 6. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | El estado compartido introduce un lock huérfano que bloquea el importador | Media | **Alto** — el panel deja de importar | Reutilizar el patrón ya resuelto en `worker_catalogo_run.py`, que tiene 10 tests de lock huérfano en la suite. Test explícito de liberación | `git revert` de T3.5; se cae de vuelta al estado en memoria (con B5, pero funcionando) |
| R2 | Cambiar `--workers` degrada el panel bajo carga | Baja | Medio | Se recomienda la opción B, que **no** cambia el número de workers | Volver a `--workers 2` en `Procfile` y `Dockerfile` |
| R3 | Propagar la excepción de Sheets rompe corridas que hoy "funcionan" tragando errores | **Alta** | Medio — pero es el objetivo | Es intencional: hacer visible lo que estaba oculto. El RUNBOOK documenta los errores esperados y qué hacer con cada uno | Ninguno: revertirlo restauraría el fallo silencioso |
| R4 | Corregir el conteo revela que se importaba mucho menos de lo que se creía | Media | Medio — reputacional, no técnico | Se comunica al owner con los números de T3.0 y T3.8 lado a lado. El bug no se creó ahora, se hizo visible | — |
| R5 | Solapamiento con Plan 1 (T1.7) y Plan 2 (T2.3, T2.4) | **Alta** | Bajo | Marcado en T3.3, T3.6 y T3.7 con la instrucción explícita de reutilizar y no duplicar | — |
| R6 | El archivo de estado se commitea con nombres de prospectos | Baja | **Alto** — dato personal en el repo | `.gitignore` y `.dockerignore` **en el mismo commit** que crea el archivo | Si ocurre: retirar al respaldo fechado y limpiar historial con clon completo previo |
| R7 | El botón de cancelar deja la hoja a medias | Media | Bajo | El worker comprueba la cancelación **entre pasos**, nunca a mitad de un `append_rows`. Lo escrito antes del corte es válido y el dedup impide duplicarlo al reintentar | Volver a correr la ciudad: el dedup lo resuelve |

**Rollback general.** Rama `fix/conteo-importador-y-estados-carga`, **un commit por defecto
corregido**, para poder revertir uno sin perder los demás. El más delicado es T3.5: si
falla, se revierte solo y los otros ocho arreglos siguen en pie.

---

## 7. EVALUACIÓN DE LA SUITE claude-ads — POR QUÉ NO APLICA

**Obligatorio evaluarla; esta es la constancia por escrito.**

Se revisaron las ~60 herramientas de `claude-ads` contra el contenido de este plan:

- Las skills de plataforma (`ads-google`, `ads-meta`, `ads-tiktok`, `ads-linkedin`,
  `ads-microsoft`, `ads-amazon`, `ads-apple`, `ads-youtube`) auditan cuentas publicitarias.
  Este plan no toca ninguna cuenta publicitaria.
- La familia `audit-*` (`audit-google`, `audit-meta`, `audit-tracking`, `audit-creative`,
  `audit-budget`, `audit-compliance`) audita píxeles, creatividades y presupuestos de medios
  pagados. No hay píxeles ni creatividades en el importador.
- Los agentes de creativo (`copy-writer`, `creative-strategist`, `visual-designer`,
  `format-adapter`) producen anuncios. Este plan no produce contenido.
- `ads-math`, la única pieza de la suite con encaje en este proyecto, es una calculadora de
  CPA y break-even. Aquí **no aplica**: este plan no toca costos. Se usa en el **Plan 2**,
  donde el costo es el sujeto.

`claude-ads` queda fuera de este plan por ausencia de sujeto, no por descuido.

---

## 8. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T3.0 | Tarea Cero: rama, respaldo y reproducción | **HECHA** | `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md` · repro 20 vs 10 · B4 `done` con 0 filas · 10/20 sondeos `idle` · baseline **230 passed** · respaldo `docs/auditoria/respaldos/2026-08-27/` (6 archivos) | 2026-08-27 |
| T3.1 | Confirmar los 9 defectos con experimento | **HECHA** | `docs/investigacion/...-reproduccion-bugs-importador.md` §7 · 9/9 CONFIRMADOS · **4 defectos nuevos** (B10 guard por proceso, B11 filtro renumera, B12 insignias rancias, B13 estado muerto) · **2 hipotesis DESCARTADAS** (doble init, `if lugares: break`) · B9 sube a severidad ALTA (XSS almacenado autoservicio) | 2026-08-27 |
| T3.2 | Separar los cuatro contadores (B1, B2) | **HECHA** | `3c8c6a0` · 237 passed (7 tests nuevos) · gates python-reviewer + code-reviewer: 0 CRITICAL, 1 HIGH que cierra T3.4, MEDIUM y LOW aplicados | 2026-08-27 |
| T3.3 | Deduplicar entre categorías (B3) | **HECHA** | `fd38673` · 252 passed (5 tests nuevos) · gates python-reviewer + code-reviewer: 0 CRITICAL/HIGH, MEDIUM aplicado · **B15 nuevo**: `descartados` venia inflado hasta 6x · dedup ANTES del `place()`, listo para Plan 2 T2.3 | 2026-08-27 |
| T3.4 | Fallo de escritura visible (B4) | **HECHA** (adelantada antes de T3.3) | `a5b413f` · 247 passed (10 tests nuevos) · gates python-reviewer + code-reviewer + **silent-failure-hunter**: 0 CRITICAL; los 2 HIGH y los 2 MEDIUM encontrados se corrigieron en el mismo commit · **B14 nuevo**: el mismo fallo silencioso existia en la LECTURA de Places | 2026-08-27 |
| T3.5 | Estado compartido entre workers (B5) | **HECHA** | `cd3bfcb` · 275 passed (23 tests nuevos) · ADR `docs/adr/2026-08-27-estado-compartido-importador.md` · **council eligio A, no la B del plan** (premisa de B falsa: daemon=True muere igual) · gates python-reviewer + code-reviewer + **security-reviewer**: 1 CRITICAL (CMD del Dockerfile roto) y 2 HIGH corregidos en el mismo commit · **falta verificacion con gunicorn real en el VPS (gate del owner)** | 2026-08-27 |
| T3.6 | Progreso real y continuo (B6) | **HECHA** | `0062da8` · 288 passed (13 tests nuevos) · barra de 3 valores a 12, tramos parejos de 9 puntos · denominador ajustable listo para Plan 2 T2.4 · gates python-reviewer + code-reviewer: 0 CRITICAL/HIGH, 3 MEDIUM corregidos | 2026-08-27 |
| T3.7 | Frontend robusto (B7, B8, B9 + B10 cliente, B12, B13) | **HECHA** | `9bd8f6c` · 314 passed (26 tests nuevos) · gates code-reviewer + **security-reviewer PASS** + **silent-failure-hunter**: 1 CRITICAL (Telegram decia 'Completado' de una corrida detenida) y 2 HIGH corregidos · `node --check` sobre el JS embebido | 2026-08-27 |
| T3.8 | Verificación de extremo a extremo | **HECHA** | `2410011` · `docs/investigacion/2026-08-27-verificacion-plan3.md` · **314 passed** · medicion antes/despues: **10/20 sondeos `idle` → 0/20** · 8 de 11 criterios cerrados · **3 son gates del owner** (corrida real, gunicorn en VPS, navegador) | 2026-08-27 |
| T3.9 | Cierre: docs, PR, handoff | **HECHA** | `2410011` · CLAUDE.md baseline 230→314 + aviso del `-qq` · RUNBOOK con seccion del importador · ADR del estado compartido | 2026-08-27 |

**Avance del plan: 10 / 10 tareas (100 %)**
