# PLAN 3 — El conteo que miente y las pantallas de carga rotas (reincidencia)

**Diseñado:** 2026-09-15 · **Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie:** `https://panelnioval.duckdns.org/importador`
**Orden de ejecución dentro de la tanda:** **3.º** (ver índice)

---

## INVARIANTES — releer al iniciar CADA tarea (no continuar sin esto)

- **OBJETIVO DEL PROYECTO:** que el importador de PanelNioval ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**, no en una rama.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs mergeados a `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`.
- **RAMA:** una por plan, creada desde `main` actualizado · **NUNCA `main`** (el VPS auto-deploya `main`) · commits convencionales en español.
- **BASELINE (nada avanza si falla):** `cd "C:\Users\PC 1\PanelNioval" && python -m pytest tests/` → **≥ 626 passed, 1 skipped**, exit 0. **SIN `-q`**: `pytest.ini` ya lo trae; el segundo lo convierte en `-qq` y **oculta la línea del resumen**.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*`].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes — anonimizar a `+52…XXXX`; (5) rebasar, cerrar o reordenar los PR #42/#43/#44 fuera del orden de aterrizaje del índice.
- **DECISIONES YA TOMADAS (no reabrir):** modelo de relevancia = logarítmico × `factor_nioval` (ADR `2026-08-28`, tres candidatos medidos sobre 589 municipios); HTML extraído a `templates/`+`static/` (PR #43); estado del importador compartido en disco (ADR `2026-08-27`); Places con `fields` explícitos + caché 30 d (PR #38, mergeado).
- **SECUENCIA:** **Plan 1 → Plan 4 → Plan 3 → Plan 2.** Es dependencia real: PR #43 está **apilado sobre** PR #42, y el bug del Plan 3 debe arreglarse una sola vez, en la estructura final (`static/js/importador.js`).

---

## 0. ESTADO DE PARTIDA VERIFICADO EN DISCO (2026-09-15)

### 0.1 El dato incómodo: este bug ya se cerró una vez

El síntoma que reportas —*«dice agregados al sheet 20 pero realmente nomás aparecen 10»*, más
pantallas de carga con fallas— es **literalmente** el que cerró el Plan 3 del 2026-08-27:

| Evidencia | Valor |
|---|---|
| PR | **#36, mergeado** en `ae0e1c9` — *«el numero que ve el operador es el que hay en la hoja»* |
| Tareas | **10/10 HECHAS** |
| Defectos | **9/9 confirmados** con experimento, más **4 nuevos** hallados durante la ejecución (B10–B13) |
| Reproducción original | `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md` — repro **20 vs 10** documentada |
| Medición antes/después | sondeos `idle`: **10/20 → 0/20** |
| Tests | baseline 230 → **314** |
| Herramienta de repro | `tools/reproducir_bugs_importador.py` — **sigue en el repo** |

**Que lo reportes vivo significa que una de estas tres cosas es cierta**, y este plan no
escribe una línea de código hasta saber cuál:

| Hipótesis | Qué la haría cierta | Cómo se descarta |
|---|---|---|
| **H1 — Despliegue rancio** | El VPS sirve código anterior a `ae0e1c9` | Huella de comportamiento en la respuesta servida (T3.1) |
| **H2 — Regresión** | Algo mergeado después (#38, #40, #41) o los planes 1 y 4 de esta tanda volvieron a romperlo | Correr la repro de agosto sobre el `main` de hoy (T3.2) |
| **H3 — Caso residual** | El fix cubrió 9 defectos pero no el camino concreto que tú viste | Reproducir **tu** escenario, no el de agosto (T3.2) |

### 0.2 La restricción que complica H1: `/salud` no dice qué versión corre

El endpoint `/salud` (`app.py:298`) es deliberadamente mudo. Su comentario lo dice:

> *«**No dice nada más.** Ni versión, ni commit, ni hostname, ni rutas.»*

Es una decisión de seguridad del Plan 5 y **no se revierte**. Consecuencia práctica: no se
puede preguntar al VPS qué SHA corre. H1 se descarta por **huella de comportamiento** —
comprobar si la respuesta servida contiene un rasgo que solo existe después de `ae0e1c9`—,
no por un número de versión.

### 0.3 Los cuatro contadores, y por qué se confunden

El PR #36 separó un contador que antes era uno solo. Hoy son cuatro (`app.py:4944`), y **no
son intercambiables**:

| Contador | Significa | El que tú citas |
|---|---|---|
| `encontrados` | Negocios que Places devolvió y pasaron los filtros de la búsqueda | ← probablemente el «20» |
| `nuevos_en_sheet` | Filas que **de verdad se escribieron** en la hoja | ← debería ser el «10» |
| `duplicados` | Ya estaban en LISTA DE CONTACTOS | |
| `descartados` | Filtrados por calidad (pocas reseñas, calificación baja, sin teléfono) | |

Si el panel en producción muestra un solo número grande, o rotula `encontrados` como si
fueran guardados, estamos ante **H1**. Si muestra los cuatro y aun así `nuevos_en_sheet` no
cuadra con la hoja, es **H2 o H3** — y ahí sí hay un defecto nuevo.

### 0.4 Dependencia dura con el Plan 4

El PR #43 **saca el HTML y el JS de `app.py`** (−3,240 líneas) a `templates/importador.html`
y `static/js/importador.js`. Si este plan arregla el front-end antes de que el Plan 4
aterrice, **el arreglo se escribe dos veces**: una en `app.py` y otra en el archivo extraído,
con riesgo de que la segunda se pierda en el conflicto. Por eso este plan va **después** del
Plan 4 en el orden de ejecución, aunque tu numeración lo ponga tercero.

`SUPUESTO: el síntoma que reportas se observó en el panel de producción (panelnioval.duckdns.org),
no en una rama local. — afecta Plan 3, Tarea T3.1.`

---

## 1. OBJETIVO, ALCANCE Y CRITERIOS DE ÉXITO

### 1.1 Objetivo

Que el número que el operador ve al terminar una corrida sea **exactamente** el número de
filas nuevas en la hoja, y que ninguna pantalla de carga afirme algo que no está pasando —
verificado **contra el panel en producción**, no contra la suite de tests.

### 1.2 Alcance

**Dentro:** diagnóstico diferencial H1/H2/H3, el fix del caso que resulte cierto, auditoría de
los estados de carga y su corrección, verificación de extremo a extremo en producción.

**Fuera:** rediseño visual de los estados (Plan 4 — este plan arregla que **mientan**, no que
sean feos), el modelo de ciudades (Plan 1) y el gasto de Places (Plan 2).

### 1.3 Criterios de éxito medibles

| # | Criterio | Cómo se mide | Gate |
|---|---|---|---|
| **CE1** | La causa está **identificada**, no supuesta | H1/H2/H3 resuelta con evidencia; las otras dos descartadas por escrito | T3.2 |
| **CE2** | Existe un test que **falla** reproduciendo tu caso exacto | Ejecución en rojo antes del fix | T3.3 |
| **CE3** | `nuevos_en_sheet` == filas nuevas reales en la hoja | Corrida real: contar la hoja antes y después y comparar con el número de la UI | T3.7 |
| **CE4** | Ningún estado de carga afirma algo falso | Recorrido de los 6 estados (reposo, corriendo, completado, detenido, error, tope) con captura de cada uno | T3.5 · T3.6 |
| **CE5** | Verificado **en producción**, no en local | Repetición de CE3 y CE4 sobre `panelnioval.duckdns.org` | T3.7 |
| **CE6** | Sin regresiones | `pytest tests/` ≥ 626 passed tras cada tarea | todas |

---

## 2. TAREAS

---

### T3.0 — Tarea Cero: rama, respaldo y recuperación del expediente de agosto

**Depende de:** cierre del Plan 4 (el HTML ya extraído).

**Contexto autocontenido.** PanelNioval es un panel Flask. Su `/importador` lanza una corrida
en un hilo, guarda el avance en un estado compartido en disco (ADR `2026-08-27`), y el
navegador lo consulta cada 3 s contra `/api/importador/estado`. En agosto se cerró un plan
completo sobre exactamente este bug; entrar a arreglarlo sin leer ese expediente es garantizar
que se repita el trabajo.

**Qué hacer.**
1. Rama `fix/conteo-importador-reincidencia` desde `main` actualizado (ya con los planes 1 y 4).
2. Baseline: `python -m pytest tests/`. Anotar el número exacto.
3. Leer, completos: `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md`,
   `docs/investigacion/2026-08-27-verificacion-plan3.md`, el ADR del estado compartido, y la
   sección «Importador de prospectos» de `docs/RUNBOOK.md`.
4. `claude-mem:mem-search` sobre: importador, conteo, B1–B15, pantallas de carga.
5. Listar los **13 defectos** ya cerrados (B1–B13) y los 2 hallados de paso (B14, B15). Esa
   lista es lo que **no** hay que volver a diagnosticar.
6. Respaldo a `docs/auditoria/respaldos/2026-09-15-plan3/`.

**Salida.** `docs/investigacion/2026-09-15-expediente-bug-conteo.md` con la lista de defectos
ya cerrados y su evidencia.

**Criterio de cierre.** Los 13 defectos listados con su commit. Sin eso, el diagnóstico de
T3.2 va a redescubrir cosas resueltas.

---

### T3.1 — Reproducir **tu** síntoma, y descartar H1 (despliegue rancio)

**Depende de:** T3.0. **Ninguna línea de código se toca antes de cerrar esta tarea.**

**Contexto autocontenido.** El síntoma reportado es: *«dice agregados al sheet 20 pero
realmente nomás aparecen 10»*, más fallas en las pantallas de carga. Existe
`tools/reproducir_bugs_importador.py`, construido en agosto justo para esto. El endpoint
`/salud` **no revela la versión desplegada** (§0.2), así que H1 se descarta por huella de
comportamiento.

**Qué hacer.**
1. **Huella de despliegue.** Elegir un rasgo que solo existe después de `ae0e1c9` —por ejemplo
   que `/api/importador/estado` devuelva **los cuatro contadores separados** y no uno solo, o
   que la respuesta del importador incluya los campos que el PR #36 añadió—. Consultar el
   panel en producción y comprobar si el rasgo está.
   - **Si el rasgo NO está → H1 confirmada.** El problema es de despliegue, no de código.
     Saltar a T3.2 con esa conclusión; el plan se reduce a arreglar el despliegue.
   - **Si el rasgo SÍ está**, el VPS tiene el fix y el bug es otro: seguir con H2/H3.
2. **Reproducción del síntoma.** Con `tools/reproducir_bugs_importador.py` sobre el `main` de
   hoy, y con una corrida controlada: anotar los cuatro contadores y **contar a mano** las
   filas nuevas en la hoja.
3. Registrar exactamente **qué número mostró la UI y qué número tenía la hoja**, con captura.

**Salida.** `docs/investigacion/2026-09-15-reproduccion-sintoma.md`.

**Criterio de cierre.** El síntoma está reproducido **con números concretos** y H1 queda
confirmada o descartada con evidencia. Si el síntoma **no reproduce**, decirlo: es un
resultado, y el plan pasa a T3.5 (pantallas de carga) sin inventar un bug.

---

### T3.2 — Diagnóstico diferencial: H2 (regresión) contra H3 (caso residual)

**Depende de:** T3.1.

**Contexto autocontenido.** Si el VPS tiene el fix y el síntoma reproduce, hay dos caminos.
**H2:** algo mergeado después de `ae0e1c9` rompió lo que ya funcionaba — candidatos: PR #38
(gasto de Places, que **tocó la ruta de conteo**: movió el descarte de duplicados antes de
pagar el detalle, y eso cambia qué se cuenta como `duplicados`), PR #40 (CI, no toca `app.py`),
PR #41 (docs), y los planes 1 y 4 de esta tanda. **H3:** el fix nunca cubrió tu camino —
candidatos: corrida multi-categoría, corrida detenida a la mitad, tope de presupuesto,
o fallo de escritura parcial en Sheets.

**Qué hacer.**
1. **Bisección dirigida, no a ciegas.** Correr la repro de agosto sobre `ae0e1c9` (justo tras
   el fix) y sobre el `main` de hoy. Si pasa en el primero y falla en el segundo → **H2**, y la
   bisección entre ambos da el commit.
2. Si pasa en los dos → **H3**: el camino que tú viste no está cubierto. Enumerar las rutas
   donde `nuevos_en_sheet` se actualiza (hay **tres** en `app.py`: la normal ~5781, la de
   parada ~5873, y la de error ~5918) y verificar cada una con un escenario propio.
3. **Prestar atención especial a `saltados`** (`incidencias['ya_en_hoja']`): el PR #38 lo
   introdujo, y el comentario del código dice que se suma **a la vez** a `encontrados` y a
   `duplicados`. Si además se sumara en algún camino a `nuevos_en_sheet`, ahí está el «20 vs 10».
4. Nombrar la causa raíz en una frase.

**Salida.** `docs/investigacion/2026-09-15-diagnostico-conteo.md` con la causa raíz, el commit
culpable si es H2, y las dos hipótesis descartadas por escrito.

**Criterio de cierre.** **CE1.** Una causa, con evidencia. *«Podría ser X»* no cierra la tarea.

---

### T3.3 — Test que falla (RED)

**Depende de:** T3.2.

**Contexto autocontenido.** El proyecto tiene 626 tests y el bug pasó igual: eso significa que
el caso que tú viste **no está cubierto**. El test nuevo no es burocracia — es la prueba de que
se entendió el defecto. Las suites del importador viven en `tests/test_importador_conteo.py`,
`tests/test_importador_progreso.py`, `tests/test_importador_estado_compartido.py` y
`tests/test_importador_frontend.py`.

**Qué hacer.**
1. Escribir el test **en la suite que corresponda** al camino de T3.2, con el nombre describiendo
   el comportamiento (`test_nuevos_en_sheet_no_cuenta_los_saltados_al_detener_la_corrida`).
2. **Ejecutarlo y ver el rojo.** Anotar el mensaje de fallo en PROGRESO. Un test que pasa antes
   del fix no reproduce nada.
3. Si el defecto es de front-end, el test va sobre `static/js/importador.js`, siguiendo el
   patrón de `tests/test_importador_frontend.py` (el proyecto ya valida el JS con `node --check`).

**Criterio de cierre.** **CE2:** salida en rojo pegada en PROGRESO, con el mensaje exacto.

---

### T3.4 — Fix (GREEN), una sola vez y en la estructura final

**Depende de:** T3.3.

**Contexto autocontenido.** El HTML y el JS ya viven en `templates/` y `static/` (Plan 4 cerrado).
El fix va **ahí**, no en `app.py`. Los tres caminos que actualizan `nuevos_en_sheet` comparten
la misma invariante y el fix debe cubrirlos a los tres, no solo al que reprodujo.

**Qué hacer.**
1. Cambio mínimo que ponga el test en verde.
2. **Verificar los tres caminos**, no solo el reproducido: normal, parada solicitada, y error
   de escritura. El comentario del código ya explica la regla y hay que respetarla: si la
   escritura reventó, `nuevos_en_sheet` y `duplicados` **no se inventan**, porque contarlos
   como duplicados afirmaría que «ya estaban», que es falso.
3. Correr la suite completa.
4. Si es **H1** (despliegue), aquí no hay código: la tarea es arreglar el despliegue y dejar
   escrito en `RUNBOOK.md` cómo se detecta un VPS rancio sin endpoint de versión.

**Criterio de cierre.** Test en verde, suite ≥ baseline, gates sin CRITICAL/HIGH.

---

### T3.5 — Auditoría de las pantallas de carga: ¿cuál miente?

**Depende de:** T3.4. **Puede correr en paralelo con T3.3/T3.4 si el bug de conteo es de backend.**

**Contexto autocontenido.** El importador tiene seis estados visibles: reposo, corriendo,
completado, detenido, error y tope de presupuesto agotado. En agosto se midió que **10 de 20
sondeos devolvían `idle`** cuando había una corrida en marcha —la barra se quedaba clavada— y
se corrigió a 0/20. Además, el Plan 3 de agosto encontró un CRITICAL: **Telegram anunciaba
"Completado" de una corrida que en realidad se había detenido.** Ese tipo de defecto —el
estado que afirma lo que no es— es el que hay que volver a cazar.

**Qué hacer.**
1. Recorrer los **seis** estados provocando cada uno a propósito (no esperando a que ocurran):
   corrida normal, parada a la mitad, error de Sheets, tope de presupuesto, ciudad sin
   resultados, y recarga del navegador a mitad de corrida.
2. Para cada uno anotar: qué muestra la UI, qué dice el backend, y **si coinciden**.
3. Usar `click-path-audit` para trazar cada botón por su secuencia completa de cambios de
   estado: el defecto clásico aquí es el de dos funciones que por separado funcionan y juntas
   se cancelan.
4. Prestar atención a **recargar la página a mitad de corrida** — el estado vive en disco y en
   memoria, y ese es el punto donde las dos fuentes se pueden separar.

**Salida.** `docs/investigacion/2026-09-15-auditoria-estados-carga.md` + una captura por estado.

**Criterio de cierre.** Los 6 estados recorridos, cada uno con veredicto **coincide / miente**.

---

### T3.6 — Corregir los estados que mienten

**Depende de:** T3.5. **Se salta si los 6 coinciden** (anotarlo, no borrar la fila).

**Qué hacer.** TDD por cada estado defectuoso: test en rojo que capture la afirmación falsa,
fix mínimo, verde. El arreglo va en `static/js/importador.js` y/o en la ruta
`/api/importador/estado`, según de dónde venga la mentira. **No se rediseña la apariencia** —
eso es del Plan 4, ya cerrado; aquí solo se corrige lo que afirma algo falso.

**Criterio de cierre.** **CE4:** los 6 estados coinciden con el backend, con captura.

---

### T3.7 — Verificación de extremo a extremo, en producción

**Depende de:** T3.4 y T3.6.

**Contexto autocontenido.** El Plan 3 de agosto cerró 10/10 y el bug te llegó igual. La lección
es que **verificar en local no basta**: tres de sus once criterios quedaron como gates del
owner (corrida real, gunicorn en el VPS, navegador) y esos tres son justo los que separan
«pasa la suite» de «funciona para el operador».

**Qué hacer.**
1. PR, gates, merge, despliegue, `smoke_panel.py` en verde.
2. **En producción**, corrida real sobre una ciudad pequeña:
   - contar las filas de la hoja **antes**;
   - lanzar la corrida y observar los estados;
   - contar las filas **después**;
   - comprobar que `después − antes == nuevos_en_sheet` de la UI. **Ese es CE3.**
3. Repetir el recorrido de estados de T3.5 contra producción (**CE5**).
4. Comprobar que el aviso de Telegram dice lo mismo que la UI.

**Salida.** `docs/investigacion/2026-09-15-verificacion-produccion-plan3.md` + capturas.

**Criterio de cierre.** **CE3 y CE5 verdes con la aritmética a la vista.** Si la corrida real
depende del owner, la tarea queda **BLOQUEADA**, no «hecha con nota».

---

### T3.8 — Cierre: documentación, PROGRESO y relevo

**Depende de:** T3.7.

**Qué hacer.**
1. `RUNBOOK.md`: qué significa cada contador (ya hay sección — ampliarla con el defecto nuevo)
   y **cómo detectar un despliegue rancio sin endpoint de versión** (aprendizaje de T3.1).
2. Anotar en el expediente por qué el fix de agosto no bastó. Es el dato más valioso del plan.
3. Cerrar PROGRESO, actualizar el índice, sobrescribir `RELEVO-actual.md` → **Plan 2, T2.0**.

**Criterio de cierre.** El índice marca 3/4 y el relevo apunta al Plan 2.

---

## 3. TABLA DE ASIGNACIÓN DE HERRAMIENTAS, POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| **A** | T3.0 | `claude-mem:mem-search` | skill | claude-mem | **Obligatorio en etapa A.** El expediente de los 13 defectos cerrados y sus trampas vive en memoria de sesiones pasadas; sin él, T3.2 redescubre lo resuelto. |
| **A** | T3.0 | `claude-mem:timeline-report` **[OPCIONAL]** | skill | claude-mem | **Condición de uso:** si `mem-search` no basta para entender la secuencia de los 9+4 defectos de agosto. |
| **A** | T3.0, T3.2 | `Explore` | agente | built-in | Localizar los **tres** sitios donde se actualiza `nuevos_en_sheet` sin cargar `app.py` entero. |
| **A** | T3.1 | `production-audit` | skill | community | Auditoría de prontitud de producción con **evidencia local**: exactamente el método para descartar H1 sin acceso al VPS. |
| **B** | T3.2 | `superpowers:systematic-debugging` | skill | superpowers | **Obligatorio.** La regla del proyecto y el sentido común: ningún fix antes del diagnóstico. Este plan lo hace estructura, no consejo. |
| **B** | T3.2 | `debugger` | agente | catalogo-agentes | Bisección dirigida entre `ae0e1c9` y el `main` de hoy: análisis de causa raíz sobre un defecto reincidente. |
| **B** | T3.2 | `error-detective` | agente | catalogo-agentes | Correlaciona el defecto con los cambios de #38 —que tocó la misma ruta de conteo— en vez de mirar el síntoma aislado. |
| **B** | T3.5 | `click-path-audit` | skill | community | **Diseñada exactamente para esto**: traza cada botón por su secuencia completa de cambios de estado y caza los que juntos se cancelan. Es la mejor herramienta de las 653 para los estados de carga. |
| **C** | T3.3, T3.4, T3.6 | `superpowers:test-driven-development` | skill | superpowers | El test en rojo es la prueba de que se entendió el defecto. Sin él el fix es una conjetura. |
| **C** | T3.3 | `tdd-guide` | agente | catalogo-agentes | Vigila que el RED sea real y que el test se escriba antes del fix, no después. |
| **C** | T3.4 | `python-pro` | agente | catalogo-agentes | El fix de backend toca lógica concurrente con lock y estado compartido: implementación cuidadosa. |
| **C** | T3.4, T3.6 | `orch-fix-defect` | skill | ECC | Pipeline prehecho por tipo de cambio: reproducir como test de regresión → verde → review → commit con gate. Encaja al milímetro con este plan. |
| **C** | T3.6 | `frontend-patterns` | skill | ECC | Los estados viven en `static/js/importador.js`: patrones de estado de UI y manejo de sondeos. |
| **D** | T3.4 | `python-reviewer` | agente | catalogo-agentes | **Reviewer del stack (backend)**, además de `code-reviewer`. |
| **D** | T3.6 | `typescript-reviewer` | agente | catalogo-agentes | **Reviewer del stack (front).** Cubre JavaScript explícitamente; `static/js/importador.js` es JS puro. Se suma, no sustituye. |
| **D** | T3.4, T3.6, T3.7 | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio. |
| **D** | T3.4, T3.6 | `silent-failure-hunter` | agente | catalogo-agentes | **Obligatorio.** El antecedente es directo: en agosto encontró aquí **1 CRITICAL** (Telegram decía «Completado» de una corrida detenida) y 2 HIGH. El defecto de esta familia es precisamente el error tragado. |
| **D** | T3.4 | `security-reviewer` | agente | catalogo-agentes | Se toca la escritura a Sheets y el estado compartido en disco: datos de clientes y rutas de archivo. |
| **D** | T3.3, T3.6 | `python-testing` | skill | ECC | Fixtures y `parametrize` para cubrir los tres caminos de actualización del contador. |
| **D** | T3.7 | `pr-test-analyzer` | agente | catalogo-agentes | Pregunta clave de este plan: ¿los tests nuevos cubren **comportamiento real**? Los 626 anteriores no atraparon este bug. |
| **D** | T3.5, T3.7 | `webapp-testing` | skill | skills-local | Recorrido de los 6 estados en navegador con capturas. (Fuente `skills-local`: no cuenta para diversidad.) |
| **D** | T3.7 | `canary-watch` | skill | ECC | Verificación del URL desplegado tras el merge: el gate que separa «pasa la suite» de «funciona». |
| **D** | T3.7 | `superpowers:verification-before-completion` | skill | superpowers | CE3 exige la aritmética a la vista. Esta skill prohíbe el «ya quedó» sin salida. |
| **E** | T3.7 | `github-ops` | skill | ECC | PR y merge con checks verificados. |
| **E** | T3.8 | `doc-updater` | agente | catalogo-agentes | `RUNBOOK.md` con los contadores y la detección de despliegue rancio. |
| **E** | T3.8 | `handoff` | skill | skills-local | Relevo hacia el Plan 2. |
| **Transversal** | todo | `blueprint` | skill | community | Formato de tareas autocontenidas. |
| **Transversal** | — | **claude-ads** | — | claude-ads | ⚠️ **Evaluada y descartada con motivo.** Se revisó la suite completa: `ads-audit`, `ads-math`, `ads-landing` y los agentes `audit-*`. Ninguna aplica: este plan no toca publicidad, ni conversión, ni gasto. `ads-math` —la única con encaje plausible— calcula CPA y ROAS sobre gasto publicitario, y aquí no hay ninguno; su parienta útil está asignada en el **Plan 2**, donde sí hay dinero que traducir. No es «no lo consideré». |

**Fuentes usadas en el Plan 3: 5 de 6 canónicas** (catalogo-agentes, ECC, community,
claude-mem, superpowers) + built-in. **claude-ads descartada con justificación escrita.**

---

## 4. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewers | Baseline | Gate extra |
|---|---|---|---|---|
| T3.0 | — | — | **≥ 626** | 13 defectos listados con su commit |
| T3.1 | — | — | — | Síntoma reproducido con **números**; H1 resuelta |
| T3.2 | — | `debugger` + `error-detective` | — | **CE1: una causa, con evidencia** |
| T3.3 | **RED obligatorio** | — | — | **CE2: salida en rojo pegada en PROGRESO** |
| T3.4 | GREEN | `python-reviewer` + `code-reviewer` + `silent-failure-hunter` + `security-reviewer` | ≥ 626 + nuevos | Los **tres** caminos verificados |
| T3.5 | — | `click-path-audit` | — | 6 estados con veredicto y captura |
| T3.6 | RED→GREEN por estado | `typescript-reviewer` + `code-reviewer` + `silent-failure-hunter` | ≥ 626 + nuevos | **CE4** |
| T3.7 | CI verde | `pr-test-analyzer` | ≥ 626 sobre `main` | **CE3 y CE5 con la aritmética a la vista** |
| T3.8 | — | `doc-updater` | ≥ 626 | Índice 3/4 · relevo → Plan 2 |

---

## 5. RIESGOS Y PLAN DE ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | Se arregla **sin diagnosticar** y el bug vuelve por tercera vez | **Alta** — es el error que ya ocurrió | Crítico | T3.1 y T3.2 son tareas propias con gate: **ninguna línea de código antes de CE1** | Ninguno necesario: el riesgo es de proceso |
| R2 | El síntoma **no reproduce** y se inventa un bug para tener algo que arreglar | Media | Alto — se toca código sano | T3.1 permite explícitamente cerrar con «no reproduce» como resultado válido | El plan pasa a T3.5 sin tocar el conteo |
| R3 | Es **H1** (despliegue rancio) y se gastan 5 tareas buscando un bug de código | Media | Medio | T3.1 descarta H1 **primero**, por huella de comportamiento | El plan se reduce a T3.4 (despliegue) + T3.8 |
| R4 | El fix se escribe en `app.py` y el Plan 4 lo borra al extraer el HTML | Media | Alto — se pierde silenciosamente | La **secuencia** del índice: este plan va **después** del Plan 4 | Reaplicar sobre `static/js/importador.js` |
| R5 | La corrida real de T3.7 depende del owner y CE3 se declara «verde» sin ella | **Alta** — pasó en agosto (3 de 11 criterios quedaron como gates del owner) | Crítico — es justo por lo que el bug llegó a producción | T3.7 obliga a marcar **BLOQUEADA**, no «hecha con nota» | El PR no se mergea hasta que CE3 esté medido |
| R6 | La corrida real gasta dinero de Places | Alta | Bajo | Ciudad pequeña y, si existe, con el tope de presupuesto del Plan 2 activo | El tope corta solo |

**Rollback del plan completo:** `git revert` del merge. El respaldo de T3.0 conserva los
archivos previos. **Nada se borra:** lo retirado vive en
`docs/auditoria/respaldos/2026-09-15-plan3/`.

---

## 6. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T3.0 | Tarea Cero: rama, respaldo y expediente de agosto | **HECHO** | `docs/investigacion/2026-09-15-expediente-bug-conteo.md` — **15** defectos (los 13 pedidos + B14/B15) con commit `ae0e1c9` y la guarda que los vigila hoy; baseline **1,193 passed, 2 skipped**; respaldo en `docs/auditoria/respaldos/2026-09-15-plan3/` | 3 correcciones al plan (dos sitios de `nuevos_en_sheet`, no tres; `saltados` no entra en el contador; el invariante de auto-deploy es falso). Respaldo de **hojas** pendiente: sin credenciales aqui, es requisito de T3.7 |
| T3.1 | Reproducir el síntoma y descartar H1 (despliegue) | **HECHO** | `docs/investigacion/2026-09-15-reproduccion-sintoma.md` + `tools/huella_despliegue.py` — **H1 DESCARTADA**: 5 marcadores del fix + 1 posterior, front-end idéntico al de `main` (975 B de diferencia = CRLF), instrumento verificado en las dos direcciones contra un doble pre-fix | El síntoma **no reproduce**: la repro de agosto pasa entera sobre el `main` de hoy y la UI rotula bien los dos números. Hallazgo: `_exportar_a_sheets` devuelve filas **enviadas**, no confirmadas por Google, y **ningún doble puede ver ese fallo**. Sin captura de corrida real: sigue siendo el gate CE1 |
| T3.2 | Diagnóstico diferencial H2 vs H3 | **HECHO** | `docs/investigacion/2026-09-15-diagnostico-conteo.md` — **H1 CONFIRMADA con prueba directa**: `51520f3` (lo servido del 24-ago al 16-sep) **no contiene** `ae0e1c9`, y su `app.py` es **byte a byte** el de la reproducción de agosto (`git diff` = 0 líneas). H2 descartada: la repro pasa idéntica en `ae0e1c9` y en `main` | **El código llevaba arreglado desde el 27-ago; lo que fallaba era el despliegue.** Llegó a producción el 16-sep como efecto colateral de T1.6. **CE1 cerrado.** T3.3 cambia de objeto: la guarda que falta no es de conteo, es de despliegue rancio |
| T3.3 | Test que falla (RED) | PENDIENTE | | |
| T3.4 | Fix (GREEN) en la estructura final | PENDIENTE | | |
| T3.5 | Auditoría de los 6 estados de carga | PENDIENTE | | |
| T3.6 | Corregir los estados que mienten | PENDIENTE | | |
| T3.7 | Verificación de extremo a extremo en producción | PENDIENTE | | |
| T3.8 | Cierre: docs, PROGRESO y relevo | PENDIENTE | | |

**Avance del plan: 0 / 9 tareas (0 %)**

**Supuestos vivos de este plan:**
- `SUPUESTO: el síntoma se observó en producción (panelnioval.duckdns.org), no en una rama local. — afecta Plan 3, Tarea T3.1.`
- `SUPUESTO: si T3.1 no reproduce el conteo erróneo, el plan sigue por los estados de carga (T3.5) y no fuerza un fix de conteo. — afecta Plan 3, Tareas T3.3 y T3.4.`
