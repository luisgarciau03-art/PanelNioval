# PLAN 1 — Relevancia de ciudades a nivel nacional, en producción

**Diseñado:** 2026-09-15 · **Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie:** `https://panelnioval.duckdns.org/importador`
**Orden de ejecución dentro de la tanda:** **1.º** (ver índice)

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

Todo lo de esta sección se comprobó ejecutando comandos, no leyendo documentos. El ejecutor
**no debe volver a asumir nada de aquí**: debe reverificarlo en T1.0, porque `main` puede
haber avanzado.

| Hecho | Valor medido | Cómo se comprobó |
|---|---|---|
| Rama de `main` | `82995c3` | `git log --oneline main -1` |
| Baseline de la suite | **626 passed, 1 skipped** (117 s) | `python -m pytest tests/` sobre `fix/endurecimiento-panel` |
| `app.py` | **6,610 líneas** | `wc -l app.py` |
| **PR #42** (este plan) | **OPEN · MERGEABLE · CI en verde** (Suite de pytest SUCCESS, Barrido de secretos SUCCESS) | `gh pr view 42` |
| Catálogo construido en #42 | **606 municipios** con `region`, `clave_inegi`, `alias`, `potencial_mercado` e `indicadores` | `git show feat/relevancia-ciudades-nacional:datos/ciudades_mx.json \| grep -c '"nombre"'` |
| Herramienta generadora | `tools/generar_catalogo_ciudades.py` (552 líneas) | listado de archivos del PR |
| PR #43 depende de #42 | **SÍ, apilado** | `git merge-base --is-ancestor feat/relevancia-ciudades-nacional feat/rediseno-panel` → 0 |

### 0.1 Qué está construido y NO debe reimplementarse

El PR #42 cierra las 10 tareas del plan de 2026-08-27. Ya existen, probados y con CI verde:

- `datos/ciudades_mx.json` — 606 municipios, datos **exógenos** (DENUE 05_2026 + Censo 2020).
- `docs/adr/2026-08-28-modelo-relevancia-ciudades.md` — el modelo, con los **tres candidatos
  calculados de verdad** sobre 589 municipios y el porqué de los dos descartes.
- `tools/generar_catalogo_ciudades.py` — regenera el catálogo desde las fuentes.
- 4 suites nuevas: `test_catalogo_ciudades.py`, `test_importador_ciudades.py`,
  `test_importador_ui_ciudades.py`, `test_prospectos_ciudades.py` (882 líneas de test).

**Este plan no rediseña nada de eso.** Lo verifica, cierra la brecha de cobertura que tú
señalaste, y lo pone en producción.

### 0.2 La brecha real contra lo que se pidió

Tu encargo dice dos cosas, y el PR #42 cubre una y media:

| Lo pedido | Estado | Qué falta |
|---|---|---|
| «ordenar por relevancia a nivel país México, ramo ferretero» | ✅ **Construido** — modelo exógeno DENUE, `potencial_mercado` 0-100 | Verificarlo en vivo (T1.4, T1.6) |
| «debe contemplar **todas las ciudades de la región**» | ⚠️ **Sin verificar** — hay 606 municipios y el campo `region` existe, pero **nadie midió si 606 es "todas"** | **T1.2 y T1.3** |
| Que el operador lo vea | ❌ **No desplegado** — PR #42 lleva abierto desde 2026-08-29 | **T1.5, T1.6** |

`SUPUESTO: "todas las ciudades de la región" significa todo municipio mexicano con presencia
ferretera real (umbral DENUE por definir en T1.2), no los 2,469 municipios del país — muchos
no tienen una sola ferretería y agregarlos solo alarga la lista. — afecta Plan 1, Tarea T1.2.`

---

## 1. OBJETIVO, ALCANCE Y CRITERIOS DE ÉXITO

### 1.1 Objetivo

Que el operador, al abrir `/importador` en producción, vea las ciudades ordenadas por
relevancia del ramo ferretero **a escala nacional**, con **cobertura completa por región**, y
pueda entender por qué una ciudad está donde está.

### 1.2 Alcance

**Dentro:** verificación de cobertura del catálogo, extensión del catálogo si falta cobertura,
aterrizaje del PR #42, despliegue y verificación en vivo.

**Fuera:** rediseño visual del importador (Plan 4), el bug de conteo (Plan 3), el gasto de
Places (Plan 2), y **cambiar el modelo de puntuación** (decisión cerrada en el ADR).

### 1.3 Criterios de éxito medibles

| # | Criterio | Cómo se mide | Gate |
|---|---|---|---|
| **CE1** | Ninguna ciudad con presencia ferretera relevante queda fuera del catálogo | Diferencia entre el universo DENUE (umbral de T1.2) y `datos/ciudades_mx.json` = **0 municipios** | T1.3 |
| **CE2** | Cada macro-región lista **todas** sus ciudades del catálogo | Para las 8 regiones: `count(json.region==R)` == `count(UI filtro==R)` | T1.4 |
| **CE3** | El orden es exógeno: una ciudad sin historial de NIOVAL **no** puntúa 0 | `min(potencial_mercado)` > 5 sobre el catálogo completo | T1.4 |
| **CE4** | El top-10 nacional es defendible ante el dueño del negocio | Revisión humana del top-30 con sus indicadores a la vista | T1.4 (gate del owner) |
| **CE5** | Está en producción | `smoke_panel.py` en verde **y** el `/importador` real sirve el catálogo nuevo | T1.6 |
| **CE6** | Sin regresiones | `pytest tests/` ≥ 626 passed tras cada tarea | todas |

---

## 2. TAREAS

Cada tarea trae su contexto autocontenido: un subagente de Opus en sesión fría debe poder
ejecutarla sin haber leído las anteriores.

---

### T1.0 — Tarea Cero: anclaje, rama, respaldo y revalidación del punto de partida

**Depende de:** nada. Es la primera tarea de la tanda completa.

**Contexto autocontenido.** El proyecto es PanelNioval, un panel Flask de una sola pieza
(`app.py`, 6,610 líneas) que sirve tres superficies: `/` (tablero), `/formulario` (captura de
llamadas) y `/importador` (busca prospectos en Google Places y los escribe en Google Sheets).
Se despliega en un VPS Vultr que **auto-deploya `main`**. Hay tres PR abiertos sin mergear
(#42, #43, #44) y este plan aterriza el #42.

**Qué hacer.**
1. Crear la rama `feat/relevancia-nacional-produccion` desde `main` actualizado (`git fetch && git checkout -b ... origin/main`).
2. Ejecutar el baseline y **anotar el número exacto**: `python -m pytest tests/`. Si da menos de 626 passed, **parar y reportar** — algo se rompió antes de empezar.
3. Reverificar el estado del PR #42: `gh pr view 42 --json state,mergeable,statusCheckRollup`. Si dejó de ser `MERGEABLE`, anotarlo: T1.5 tendrá que rebasar.
4. Respaldar a `docs/auditoria/respaldos/2026-09-15/`: `app.py`, `datos/ciudades_mx.json` (desde la rama del PR), y la salida del baseline.
5. Escribir la línea de ANCLA de la tarea siguiente.

**Salida.** `docs/auditoria/2026-09-15-estado-de-partida-plan1.md` con los cinco números
medidos (baseline, líneas de `app.py`, SHA de `main`, estado del PR #42, conteo del catálogo).

**Criterio de cierre.** El documento existe y el respaldo también, **antes** de que ninguna
tarea toque código.

---

### T1.1 — Recuperar el contexto previo y no re-litigar lo cerrado

**Depende de:** T1.0.

**Contexto autocontenido.** El importador tiene historia: se migró desde un script suelto, se
le añadió escape de fórmulas de Sheets, se corrigió la columna CONTACTO, se desplegó la
`GMAPS_API_KEY` en el VPS, y en agosto se diseñó y construyó el modelo de relevancia. Parte de
esa historia vive en la memoria persistente de claude-mem y parte en `docs/`. Entrar a tocar
el modelo sin leerla es la forma más rápida de reabrir una decisión ya cerrada con datos.

**Qué hacer.**
1. `claude-mem:mem-search` sobre: importador, ciudades, relevancia, DENUE, Places, PanelNioval.
   Buscar en particular la observación *"City Relevance Algorithm Uses Only Existing Contact
   Sheet Data — Not Industry Importance"*, que es el origen de todo esto.
2. Leer, de la rama `feat/relevancia-ciudades-nacional`:
   `docs/adr/2026-08-28-modelo-relevancia-ciudades.md`,
   `docs/investigacion/2026-08-28-relevancia-ferretera-mexico.md`,
   `docs/investigacion/2026-08-29-verificacion-plan1.md`.
3. Producir una página con: **qué está decidido y no se reabre**, y **qué quedó abierto**.

**Salida.** `docs/investigacion/2026-09-15-contexto-plan1.md`.

**Criterio de cierre.** El documento lista al menos 5 decisiones cerradas con su fuente
(ADR o ID de observación), y la lista de lo abierto coincide con §0.2 de este plan.

---

### T1.2 — Auditoría de cobertura: ¿606 municipios son «todas las ciudades de la región»?

**Depende de:** T1.1. **Esta es la tarea que responde a tu requisito nuevo.**

**Contexto autocontenido.** `datos/ciudades_mx.json` tiene 606 municipios. El plan de agosto
los eligió con un umbral (`≥20 ferreterías` según el ADR). Tú pediste explícitamente que
contemple **todas las ciudades de la región**. Nadie ha medido cuántos municipios con
actividad ferretera quedan fuera de ese umbral, ni si alguna región quedó con cobertura
desigual (p. ej. el Sureste, donde los municipios son más chicos, podría estar sub-representado
por un umbral pensado para el Bajío).

**Qué hacer.**
1. Con `tools/generar_catalogo_ciudades.py` como base, calcular el **universo completo**:
   cuántos municipios mexicanos tienen ≥1 ferretería en DENUE, y su distribución por región.
2. Cruzar contra los 606 del catálogo. Producir, **por región**: municipios en el universo,
   municipios en el catálogo, cobertura %, y los excluidos con más ferreterías.
3. Evaluar tres umbrales (≥20 actual, ≥10, ≥5) y reportar para cada uno: total de ciudades,
   cobertura por región, y **la ciudad más pequeña que entraría**.
4. Recomendar umbral con motivo, atendiendo al equilibrio regional, no solo al total.

**Salida.** `docs/investigacion/2026-09-15-cobertura-catalogo-ciudades.md` con la tabla por
región y la recomendación.

**Criterio de cierre.** El documento responde con un número, no con un adjetivo: *«quedan
fuera N municipios con ≥X ferreterías, concentrados en las regiones A y B»*. Si N = 0 con el
umbral actual, **T1.3 se cierra sin cambios** y se anota así.

---

### T1.3 — Cerrar la brecha de cobertura

**Depende de:** T1.2. **Se salta si T1.2 mide brecha cero** (anotarlo en PROGRESO, no borrar la fila).

**Contexto autocontenido.** El catálogo se genera, no se escribe a mano:
`tools/generar_catalogo_ciudades.py` lee DENUE y el Censo y emite `datos/ciudades_mx.json`.
Extender la cobertura es **cambiar un umbral y regenerar**, no editar JSON a mano. El modelo
de puntuación **no se toca** (decisión cerrada).

**Qué hacer.** TDD, en este orden:
1. **RED:** test en `tests/test_catalogo_ciudades.py` que afirme la cobertura objetivo de T1.2
   (p. ej. *«toda región tiene ≥ X % del universo de su región»*). Debe **fallar** ahora.
2. **GREEN:** ajustar el umbral en el generador, regenerar el catálogo, correr el test.
3. Verificar que el rango de `potencial_mercado` **sigue sin producir ceros** (CE3): al bajar
   el umbral entran municipios chicos y la normalización logarítmica podría acercarlos a 0.
4. Correr la suite completa: las 4 suites del catálogo deben seguir verdes.

**Salida.** `datos/ciudades_mx.json` regenerado + test nuevo + nota en el ADR (sección
«Revisión 2026-09-15», **anexo, no reescritura**).

**Criterio de cierre.** CE1 y CE3 verdes; baseline ≥ 626 + los tests nuevos.

---

### T1.4 — Verificar el orden nacional y el filtro por región, de verdad

**Depende de:** T1.3.

**Contexto autocontenido.** El riesgo de un modelo de puntuación es que sea correcto en el
código y absurdo en la lista. El ADR reporta un top encabezado por Puebla (90.7), Guadalajara
(90.2), León (89.0) y Monterrey (88.7) — plausible para ferretería mayorista, pero **nadie del
negocio lo ha mirado**. Además, el filtro por macro-región es la mitad de tu requisito: si
filtra pero no lista todas, la cobertura ganada en T1.3 no llega al operador.

**Qué hacer.**
1. Generar el **top-30 nacional** con sus indicadores a la vista (ferreterías, mayoreo,
   construcción, población) en tabla legible.
2. Generar, por cada una de las regiones, su **top-10 y su conteo total**.
3. Verificar CE2 programáticamente: para cada región, las ciudades del JSON == las que la UI
   lista con ese filtro. Test automatizado, no inspección visual.
4. Verificar CE3: `min(potencial_mercado)` sobre el catálogo completo.
5. **Gate del owner (CE4):** presentar el top-30 y preguntar si el orden es defendible. Si el
   owner señala una ciudad fuera de lugar, **no ajustar el modelo**: registrar el caso en el
   ADR como dato para una revisión futura, y continuar. Cambiar la fórmula por un caso suelto
   es sobreajuste.

**Salida.** `docs/investigacion/2026-09-15-verificacion-orden-nacional.md` + tests de CE2/CE3.

**Criterio de cierre.** CE2 y CE3 automatizados y verdes; CE4 con respuesta del owner anotada
(aprobado / aprobado con reservas / bloqueado).

---

### T1.5 — Aterrizar el PR #42

**Depende de:** T1.4.

**Contexto autocontenido.** PR #42 (`feat/relevancia-ciudades-nacional`) lleva abierto desde
2026-08-29, con CI en verde y `MERGEABLE`. Desde entonces `main` recibió el commit `82995c3`.
El trabajo de T1.3/T1.4 vive en `feat/relevancia-nacional-produccion`. Hay que unir ambos y
mergear **una sola vez**. **PR #43 está apilado sobre #42**: si se fuerza un squash que cambie
los SHA, el #43 queda descolgado — por eso el orden y el método importan.

**Qué hacer.**
1. Rebasar `feat/relevancia-nacional-produccion` sobre `feat/relevancia-ciudades-nacional`, o
   empujar los commits de T1.3/T1.4 directamente a la rama del PR #42 (**preferido**: mantiene
   un único PR y no descuelga al #43).
2. Confirmar CI verde en el PR actualizado.
3. Gates: `python-reviewer` + `code-reviewer` sobre el diff **nuevo** (no sobre los 12k de
   agosto, ya revisados); `security-reviewer` si T1.3 tocó lectura de archivos o rutas.
4. Mergear con `gh pr merge 42 --squash` **solo si**: suite verde, CI verde, 0 CRITICAL/HIGH.
5. **Inmediatamente después:** verificar que `feat/rediseno-panel` (PR #43) sigue `MERGEABLE`
   contra el nuevo `main`. Si no, anotarlo: es el primer insumo del Plan 4.

**Salida.** PR #42 mergeado; SHA anotado en PROGRESO.

**Criterio de cierre.** `git log main -1` contiene el merge y `pytest` sobre `main` ≥ 626.

---

### T1.6 — Desplegar y verificar en producción

**Depende de:** T1.5.

**Contexto autocontenido.** El VPS auto-deploya `main`. Que el merge haya ocurrido **no**
prueba que el panel lo esté sirviendo: el despliegue puede fallar en silencio, y el RUNBOOK
(§«Smoke test post-deploy») manda correr el smoke tras cada merge. Este es el criterio que
convierte el trabajo de agosto en algo que tú puedes ver.

**Qué hacer.**
1. Esperar/forzar el deploy y correr `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>`. Debe imprimir `Todo OK ✅`.
2. Abrir `/importador` en el navegador y comprobar, con captura:
   - el contador de ciudades muestra el total nuevo (no el de la lista estática vieja);
   - el filtro por macro-región existe y lista todas las ciudades de la región elegida;
   - una ciudad sin historial de NIOVAL aparece con puntuación > 0 y **no** al final.
3. Guardar las capturas en `docs/diseno/2026-09-15-plan1-produccion/`.

**Salida.** Capturas + `docs/auditoria/2026-09-15-verificacion-produccion-plan1.md`.

**Criterio de cierre.** **CE5 verde.** Si el smoke falla, la tarea queda **BLOQUEADA** (no
"hecha con nota"): es el único criterio que prueba que el trabajo llegó al operador.

---

### T1.7 — Cierre: documentación, PROGRESO y relevo

**Depende de:** T1.6.

**Qué hacer.**
1. Actualizar `CLAUDE.md` (baseline nuevo si cambió) y `docs/RUNBOOK.md` (sección del
   importador: qué significa el orden y cómo se regenera el catálogo).
2. Cerrar la tabla PROGRESO de este plan y el marcador global del índice.
3. Sobrescribir `docs/superpowers/plans/RELEVO-actual.md` apuntando a **Plan 4, T4.0**.
4. Guardar contexto con `claude-mem` / `handoff`.

**Criterio de cierre.** El índice marca 1/4 planes completos y el relevo apunta a Plan 4.

---

## 3. TABLA DE ASIGNACIÓN DE HERRAMIENTAS, POR ETAPA

Fuentes: **catalogo-agentes**, **ECC**, **community**, **claude-mem**, **superpowers**,
**claude-ads**, más el built-in de Claude Code.

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| **A** | T1.1 | `claude-mem:mem-search` | skill | claude-mem | La decisión de no re-litigar el modelo está en observaciones de sesiones pasadas, no en el repo. Es la única fuente que las tiene. |
| **A** | T1.1 | `claude-mem:timeline-report` **[OPCIONAL]** | skill | claude-mem | Solo si `mem-search` devuelve fragmentos sueltos y hace falta la narrativa del sprint de agosto. |
| **A** | T1.0, T1.2 | `Explore` | agente | built-in | Barrer `tools/generar_catalogo_ciudades.py` (552 líneas) y las 4 suites del catálogo sin quemar el contexto de la sesión principal. |
| **A** | T1.2 | `data-researcher` | agente | catalogo-agentes | La brecha de cobertura es un problema de *fuentes de datos* (DENUE, Censo): validar el universo y su calidad es exactamente su especialidad. |
| **A** | T1.2 | `market-research` | skill | ECC | Encuadra «relevancia del ramo ferretero» como pregunta de mercado con atribución de fuente, no como intuición. |
| **B** | T1.2 | `data-analyst` | agente | catalogo-agentes | Elegir umbral es una decisión de distribución (cola pesada, equilibrio regional): requiere leer percentiles, no opinar. |
| **B** | T1.2 | `council` | skill | community | Los tres umbrales (≥20/≥10/≥5) son un tradeoff real —cobertura vs ruido— con defensores legítimos. Panel de 4 voces antes de fijarlo. |
| **B** | T1.3 | `architecture-decision-records` | skill | ECC | El cambio de umbral **anexa** al ADR existente; el formato evita que alguien lo lea como un modelo nuevo. |
| **C** | T1.3 | `superpowers:test-driven-development` | skill | superpowers | Cobertura es una afirmación verificable: el test de cobertura debe fallar antes de regenerar el catálogo. |
| **C** | T1.3 | `tdd-guide` | agente | catalogo-agentes | Acompaña el ciclo RED→GREEN y vigila que el test no se escriba después del hecho. |
| **C** | T1.3 | `python-pro` | agente | catalogo-agentes | El generador es Python con normalización logarítmica: implementación idiomática y con tipos. |
| **C** | T1.3 | `python-patterns` | skill | ECC | Referencia de idioms al tocar el generador. |
| **C** | T1.3, T1.5 | `django-build-resolver` **[OPCIONAL]** | agente | catalogo-agentes | **Solo si** regenerar el catálogo rompe imports o dependencias de pip. **No existe build-resolver de Flask** en las 653 (ver §3.3 del índice); éste es el único especializado en errores de pip/import de Python. |
| **D** | T1.3, T1.4 | `python-reviewer` | agente | catalogo-agentes | **Reviewer del stack.** Va **además** de `code-reviewer`, no en su lugar. |
| **D** | T1.3, T1.4, T1.5 | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio tras escribir código. |
| **D** | T1.3 | `security-reviewer` | agente | catalogo-agentes | El generador lee archivos de datos y escribe JSON: rutas, permisos y tamaño de entrada. Obligatorio por tocar E/S de archivos. |
| **D** | T1.4 | `python-testing` | skill | ECC | Los tests de CE2/CE3 son parametrizados por región: fixtures y `parametrize` bien hechos. |
| **D** | T1.4 | `silent-failure-hunter` | agente | catalogo-agentes | El `cargarCiudades()` del importador tiene un `catch` que cae a la lista estática: un fallo silencioso ahí haría que CE2 pase en test y falle en vivo. |
| **D** | T1.6 | `webapp-testing` | skill | skills-local | Verificación en navegador de las tres comprobaciones visuales de T1.6. (Fuente `skills-local`: no cuenta para el mínimo de diversidad — ver §3.2 del índice.) |
| **D** | T1.6 | `canary-watch` | skill | ECC | Verifica un **URL desplegado** tras el release: exactamente el gate de CE5. |
| **D** | T1.4, T1.6 | `superpowers:verification-before-completion` | skill | superpowers | Prohíbe declarar CE4/CE5 cerrados sin la salida del comando a la vista. |
| **E** | T1.5 | `github-ops` | skill | ECC | Merge del PR con `gh`, comprobando checks antes de apretar. |
| **E** | T1.5 | `claude-mem:babysit` **[OPCIONAL]** | skill | claude-mem | **Solo si** el CI del PR #42 tarda o falla de forma intermitente: vigila hasta que esté verde. |
| **E** | T1.7 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md` y `RUNBOOK.md` al día con el baseline y el procedimiento del catálogo. |
| **E** | T1.7 | `handoff` | skill | skills-local | Genera el relevo con el estado real, no con un resumen de memoria. |
| **Transversal** | todo el plan | `blueprint` | skill | community | El formato de este documento: contexto autocontenido por tarea para sesiones frías. |
| **Transversal** | T1.2 | `ads-math` **[OPCIONAL]** | skill | claude-ads | **Condición de uso:** si el owner quiere traducir «ampliar el catálogo» a costo — cada ciudad nueva es una corrida de ~80 Place Details. Convierte cobertura en pesos. Es el puente natural con el Plan 2. |

**Fuentes usadas en el Plan 1: 6 de 6 canónicas** (catalogo-agentes, ECC, community,
claude-mem, superpowers, claude-ads) + built-in.

---

## 4. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewers | Baseline | Gate extra |
|---|---|---|---|---|
| T1.0 | — | — | **≥ 626** (medir y anotar) | Respaldo existe **antes** de tocar nada |
| T1.1 | — | — | — | ≥5 decisiones cerradas con fuente |
| T1.2 | — | `data-analyst` revisa la distribución | — | La brecha es un **número**, no un adjetivo |
| T1.3 | TDD: RED antes que GREEN | `python-reviewer` + `code-reviewer` + `security-reviewer` | ≥ 626 + nuevos | CE1 y CE3 verdes |
| T1.4 | CE2 y CE3 automatizados | `silent-failure-hunter` | ≥ 626 + nuevos | **CE4 = gate del owner** |
| T1.5 | CI del PR en verde | `python-reviewer` + `code-reviewer` sobre el diff nuevo | ≥ 626 sobre `main` | 0 CRITICAL/HIGH · PR #43 sigue mergeable |
| T1.6 | — | — | — | **CE5: smoke en verde + 3 capturas** |
| T1.7 | — | `doc-updater` | ≥ 626 | RELEVO apunta a Plan 4 T4.0 |

---

## 5. RIESGOS Y PLAN DE ROLLBACK

| # | Riesgo | Probabilidad | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | Bajar el umbral en T1.3 mete municipios diminutos y **reintroduce ceros** en la puntuación (rompe CE3) | Media | Alto — devuelve el problema original con otro nombre | CE3 es test automatizado, corre en T1.3 antes de cerrar | Revertir el umbral al ≥20 del ADR: un solo valor en el generador |
| R2 | Mergear #42 **descuelga** el PR #43 (está apilado) | Media | Alto — el Plan 4 arrancaría con 28k líneas en conflicto | T1.5 exige comprobar `MERGEABLE` de #43 **inmediatamente después** del merge | `git rebase --onto main <base-vieja> feat/rediseno-panel`; la rama local existe |
| R3 | El VPS no despliega y CE5 no se cumple | Media | Alto — el trabajo no llega al operador | T1.6 es tarea propia, con gate duro; no se declara «hecho» sin smoke verde | El panel sigue sirviendo el `main` anterior: el estado previo es el rollback |
| R4 | El owner rechaza el top-30 (CE4) | Baja | Medio | El plan **prohíbe ajustar el modelo** por casos sueltos: se registra y se sigue | Ninguno: es registro, no cambio de código |
| R5 | `main` avanzó y el baseline ya no es 626 | Media | Bajo | T1.0 lo mide y lo fija como número de esta tanda | Anotar el número real en INVARIANTES de los 4 planes |
| R6 | Regenerar el catálogo requiere fuentes DENUE que no están en disco | Media | Alto — bloquea T1.3 | T1.2 verifica la disponibilidad de las fuentes **antes** de planear la regeneración | Si no hay fuentes: T1.3 se marca BLOQUEADA (gate del owner) y el plan cierra con la cobertura actual, documentada |

**Rollback del plan completo:** `git revert` del merge squash de #42 sobre `main`. El VPS
vuelve al panel anterior en el siguiente deploy. El respaldo de T1.0 conserva el `app.py`
previo. **Nada se borra:** lo retirado vive en `docs/auditoria/respaldos/2026-09-15/`.

---

## 6. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T1.0 | Tarea Cero: anclaje, rama, respaldo y revalidación | **HECHO** | `docs/auditoria/2026-09-15-estado-de-partida-plan1.md` · rama `feat/relevancia-nacional-produccion` desde `main` `82995c3` · baseline **388 passed, 1 skipped** exit 0 · PR #42 OPEN/MERGEABLE/CLEAN CI verde · catálogo 606 · respaldo en `docs/auditoria/respaldos/2026-09-15/` | 2026-09-15 |
| T1.1 | Contexto previo y decisiones que no se reabren | PENDIENTE | | |
| T1.2 | Auditoría de cobertura del catálogo por región | PENDIENTE | | |
| T1.3 | Cerrar la brecha de cobertura (TDD) | PENDIENTE | | |
| T1.4 | Verificar orden nacional y filtro por región | PENDIENTE | | |
| T1.5 | Aterrizar el PR #42 | PENDIENTE | | |
| T1.6 | Desplegar y verificar en producción | PENDIENTE | | |
| T1.7 | Cierre: docs, PROGRESO y relevo | PENDIENTE | | |

**Avance del plan: 1 / 8 tareas (12.5 %)**

**Supuestos vivos de este plan:**
- `SUPUESTO: «todas las ciudades de la región» = todo municipio con presencia ferretera real según umbral DENUE, no los 2,469 municipios del país. — afecta Plan 1, Tarea T1.2.`
- `SUPUESTO: el gate «≥ 626» de INVARIANTES se reinterpreta como «≥ baseline de la rama base», que hoy es 388 sobre main. No se relaja el criterio: se corrige la referencia, porque el 626 se midió sobre fix/endurecimiento-panel (PR #44, 28 commits adelante, 5 suites propias). Verificado en T1.0: 0 failed, 0 errors, ningún test borrado. — afecta los 4 planes. Ver docs/auditoria/2026-09-15-estado-de-partida-plan1.md §2.`
