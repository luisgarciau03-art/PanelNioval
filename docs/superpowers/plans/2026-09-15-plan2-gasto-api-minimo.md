# PLAN 2 — Gasto y uso de la API al mínimo

**Diseñado:** 2026-09-15 · **Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**API en cuestión:** **Google Places** (la única que cuesta dinero en este proyecto)
**Orden de ejecución dentro de la tanda:** **4.º y último** (ver índice)

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

### 0.1 Lo que YA se optimizó y está en producción (PR #38, mergeado en `4e06e64`)

Este plan **no rehace nada de esto**. Son hechos mergeados, con test y medición:

| Optimización | Efecto medido | Dónde |
|---|---|---|
| `Place Details` con `fields` explícitos | Deja de facturar Basic (26 campos) y Atmosphere (18). Se pagaban **50 campos para leer 3** | ADR `2026-08-28-places-legacy-vs-new.md` |
| Deduplicar **antes** de pagar Details | Ciudad ya trabajada: **80 → 0** Place Details | T2.3 del plan viejo |
| Cortar variaciones y páginas sin aporte | Text Search **18 → 13** por categoría | T2.4 |
| Caché persistente `place_id` → detalle, TTL 30 d | 2.ª corrida de la misma ciudad: **80 → 0** Details, 80 cache hits | T2.5 |
| Medidor de costo + **dos topes** (llamadas y dinero) | 4 contadores en UI + aviso por Telegram | T2.6 |
| Verificación A/B de calidad | **80 aprobados con y sin recorte, diff vacío** — y el chequeo se probó capaz de detectar pérdida | T2.7 |

### 0.2 Qué quedó abierto — y es exactamente el alcance de este plan

**(a) La fuga residual: se paga el Details y luego se descarta por no tener teléfono.**

Leyendo `_buscar_negocios` en `app.py` (~línea 5320), el orden de filtros es:

```
                                        ¿cuesta?   ¿de dónde sale el dato?
1. ya está en la hoja        → descarta  GRATIS    clave nombre+dirección (Text Search)
2. reseñas < 5               → descarta  GRATIS    user_ratings_total   (Text Search)
3. calificación < 3.5        → descarta  GRATIS    rating               (Text Search)
4. _detalle_de_place(pid)              ← ⚠ AQUÍ SE PAGA EL PLACE DETAILS
5. sin teléfono              → descarta  YA PAGADO formatted_phone_number (Details)
```

Los tres filtros gratis ya están antes del cobro —eso lo arregló el PR #38—. Pero el
**cuarto filtro está después**: cada negocio sin teléfono cuesta un Place Details completo y
**nunca llega a la hoja**. La caché de 30 d lo amortigua en corridas repetidas, pero la
primera corrida de cada ciudad lo paga íntegro. **Nadie ha medido cuánto es.**

**(b) La puerta que el ADR dejó abierta.** El ADR `2026-08-28-places-legacy-vs-new.md` decide,
textualmente: *«Quedarse en la API legacy y optimizarla. **No migrar a Places API (New) en
este plan.**»* El «en este plan» es deliberado. Places API (New) permite pedir campos de
contacto **en el propio `searchText`** mediante *field mask*; si el teléfono viniera ahí, el
filtro 5 pasaría a ser gratis y **desaparecería la mayoría de las llamadas a Details**. Eso
no es reabrir una decisión cerrada: es la continuación que el propio ADR previó.

**(c) La mitad monetaria sigue bloqueada.** T2.0 del plan viejo quedó **🚫 BLOQUEADA (importe)**:
sin `gcloud`, con una cuenta de servicio que solo tiene Sheets y Drive, no se pudo leer el
gasto real en pesos. Se sustituyó por conteo exacto de llamadas. **Sigue igual.**

**(d) El Plan 1 multiplica el problema.** Si T1.3 amplía el catálogo de ciudades, cada ciudad
nueva es una corrida de ~80 Place Details. Optimizar el costo *por corrida* deja de ser
cosmético en cuanto hay más corridas posibles.

**(e) El rediseño movió el medidor.** El PR #43 saca el HTML y el JS de `app.py` a
`templates/` y `static/js/importador.js`. Los 4 contadores del medidor viven ahora ahí. Hay
que verificar que siguen leyendo lo mismo.

`SUPUESTO: «tokens de la API» se interpreta como el consumo facturable de Google Places, que
es la única API de pago de PanelNioval —no usa ningún LLM: los únicos "token" del código son
PANEL_DASHBOARD_TOKEN, WORKER_TOKEN y next_page_token, que son de autenticación y paginación.
— afecta Plan 2 completo. Ver decisión D2 del índice.`

---

## 1. OBJETIVO, ALCANCE Y CRITERIOS DE ÉXITO

### 1.1 Objetivo

Que una corrida del importador consuma el **mínimo verificable** de llamadas facturables de
Google Places, sin perder un solo prospecto bueno, y con un tope que el operador no pueda
rebasar por accidente.

### 1.2 Alcance

**Dentro:** medición de la fuga residual, evaluación y —si procede— migración de la ruta de
teléfono, tope duro por corrida, y verificación A/B de que no se pierde calidad.

**Fuera:** el modelo de relevancia (Plan 1), el bug de conteo (Plan 3), el rediseño (Plan 4),
y **el gasto de LLM de BruceWhatsapp** (proyecto distinto — ver D2 del índice).

### 1.3 Criterios de éxito medibles

| # | Criterio | Cómo se mide | Gate |
|---|---|---|---|
| **CE1** | La fuga residual está **cuantificada**, no estimada | Nº de Place Details pagados y descartados por `sin_telefono` en una corrida real, y su % sobre el total | T2.1 |
| **CE2** | Llamadas facturables por corrida **bajan** respecto a la medición de T2.0 | Conteo exacto antes/después con `tools/medir_llamadas_places.py` | T2.6 |
| **CE3** | **Cero pérdida de calidad**: mismos prospectos aprobados antes y después | Diff de la lista de aprobados = vacío, **y** el chequeo demostrado capaz de detectar pérdida (prueba en las dos direcciones) | T2.6 |
| **CE4** | El tope por corrida **corta de verdad** | Test que fuerza el tope y verifica salida limpia; y que sin tope la corrida habría seguido | T2.5 |
| **CE5** | El medidor sigue vivo tras el rediseño | Los 4 contadores de `static/js/importador.js` muestran los valores del backend | T2.5 |
| **CE6** | Gasto en **pesos** conocido | Lectura del billing de Google Cloud | T2.2 · **gate del owner** — ver D3 |
| **CE7** | Sin regresiones | `pytest tests/` ≥ 626 passed tras cada tarea | todas |

---

## 2. TAREAS

---

### T2.0 — Tarea Cero: rama, respaldo y medición del gasto actual

**Depende de:** el cierre del Plan 3 (es el último plan de la tanda).

**Contexto autocontenido.** PanelNioval es un panel Flask; su `/importador` busca negocios en
Google Places por categoría y ciudad, filtra por calidad y escribe los que pasan en Google
Sheets. Cada corrida cuesta llamadas facturables de dos tipos: **Text Search** (~13 por
categoría tras el recorte del PR #38) y **Place Details** (~1 por candidato que pasa los tres
filtros gratis). Ya existe `tools/medir_llamadas_places.py`, construido en agosto para contar
llamadas sin tocar la consola de Google.

**Qué hacer.**
1. Rama `perf/gasto-places-minimo` desde `main` actualizado (que ya trae los planes 1, 4 y 3).
2. Baseline: `python -m pytest tests/`. Anotar el número exacto.
3. Correr `tools/medir_llamadas_places.py` y registrar el **gasto actual en llamadas**,
   desglosado por tipo, sobre una ciudad no trabajada y otra ya trabajada.
4. Respaldar a `docs/auditoria/respaldos/2026-09-15-plan2/`.
5. **Comparar contra `docs/investigacion/2026-08-28-costo-places-despues.md`**: si los números
   cambiaron, los planes 1/4/3 tocaron la ruta de Places sin querer. Eso es un hallazgo.

**Salida.** `docs/investigacion/2026-09-15-costo-places-antes-plan2.md`.

**Criterio de cierre.** Dos mediciones (ciudad virgen / ciudad trabajada) con desglose por
tipo de llamada, comparadas contra la línea de agosto.

---

### T2.1 — Cuantificar la fuga: Details pagados que nunca llegan a la hoja

**Depende de:** T2.0. **Esta tarea decide si el resto del plan vale la pena.**

**Contexto autocontenido.** Ver §0.2(a): el filtro `sin_telefono` corre **después** de pagar
el Place Details. Cada negocio sin teléfono es un Details tirado. `stats['sin_telefono']` ya
se cuenta en el código —va al contador «descartados» de la UI— pero **nunca se ha cruzado
contra el número de Details pagados**, que es lo que convierte un descarte en dinero.

**Qué hacer.**
1. Instrumentar (sin cambiar comportamiento) para obtener, en una corrida real:
   `details_pagados`, `sin_telefono`, `aprobados`, `desde_cache`.
2. Calcular la **tasa de desperdicio** = `sin_telefono / details_pagados`, en ciudad virgen y
   en ciudad trabajada.
3. Repetir sobre **3 ciudades de perfiles distintos** (metrópoli, ciudad media, municipio
   chico): la tasa puede depender de cuán bien catalogados estén los negocios locales.
4. Reportar cuánto se ahorraría si el filtro de teléfono fuera gratis.

**Salida.** `docs/investigacion/2026-09-15-fuga-details-sin-telefono.md`.

**Criterio de cierre.** **CE1.** Un porcentaje medido sobre 3 ciudades, no una estimación.
**Si la tasa es < 10 %, T2.2 y T2.3 se saltan** (anotarlo, no borrar las filas): la migración
no se paga sola y el plan se concentra en T2.5–T2.6.

---

### T2.2 — Evaluar Places API (New): ¿viene el teléfono en el `searchText`?

**Depende de:** T2.1 (solo si la fuga ≥ 10 %).

**Contexto autocontenido.** El ADR `2026-08-28-places-legacy-vs-new.md` decidió quedarse en la
API legacy **«en este plan»**, dejando la migración abierta. La razón para volver a mirarla es
concreta: Places API (New) usa *field masks*, y si `searchText` puede devolver el número
telefónico directamente, el filtro que hoy cuesta un Details pasaría a ser gratis.

**⚠ Regla del proyecto:** *ningún dato de tarifa ni de agrupación de campos sale de la memoria
del modelo.* Todo se consulta y se cita con fuente y fecha, igual que hizo el ADR de agosto.

**Qué hacer.**
1. Consultar la documentación **oficial y actual** (vía `context7-mcp` / `documentation-lookup`,
   no de memoria) de Places API (New) `places:searchText`: qué campos admite el field mask, en
   qué SKU cae cada uno, y si `nationalPhoneNumber` está disponible ahí.
2. Verificar qué soporta **el cliente instalado** (`googlemaps 4.10.0`) — el ADR de agosto
   estableció que el cliente instalado es la autoridad sobre lo que este proyecto puede pedir.
   Si no soporta la API New, evaluar el costo de llamar por HTTP directo.
3. Calcular el ahorro esperado con los números reales de T2.1, y el costo de la migración
   (superficie de código tocada, tests a reescribir, riesgo de cambio de comportamiento).
4. Evaluar **al menos una alternativa más barata**: p. ej. no migrar y en su lugar ordenar los
   candidatos para que los sin-teléfono caigan fuera del tope, o cachear también los negativos.

**Salida.** `docs/investigacion/2026-09-15-places-new-field-mask.md`, con cada afirmación de
tarifa citada y fechada.

**Criterio de cierre.** Dos o tres opciones con **ahorro estimado y costo de implementación**,
cada una con su fuente. Nada sin citar.

---

### T2.3 — Decidir y dejarlo escrito (ADR)

**Depende de:** T2.2.

**Contexto autocontenido.** Migrar de API es una decisión con defensores legítimos en los dos
lados: ahorro real contra riesgo de tocar la ruta que produce todo el valor del importador.
El proyecto ya usa `council` para este tipo de disyuntiva —lo hizo en T3.5 del Plan 3, donde
el consejo eligió la opción A contra la B del plan porque la premisa de B era falsa—.

**Qué hacer.**
1. Convocar `council` con las opciones de T2.2, sus números y sus riesgos.
2. Escribir el ADR: `docs/adr/2026-09-15-ruta-de-telefono-places.md`, que **anexa** al ADR de
   agosto (no lo contradice: aquel dijo «no migrar *en este plan*»).
3. Si la decisión es **no migrar**, decirlo con el número que lo justifica y cerrar el plan en
   T2.5–T2.6. Un «no» medido es un resultado válido.

**Salida.** ADR con decisión, alternativas descartadas y el motivo de cada descarte.

**Criterio de cierre.** El ADR nombra la opción elegida, su ahorro esperado y **qué evidencia
la haría reversible**.

---

### T2.4 — Implementar el ahorro elegido

**Depende de:** T2.3. **Se salta si el ADR decide no cambiar nada.**

**Contexto autocontenido.** La ruta a tocar es `_buscar_negocios` y `_detalle_de_place` en
`app.py`. Es el camino que produce **todo** el valor del importador: un error aquí no cuesta
dinero, cuesta prospectos. Por eso se hace con TDD y con verificación A/B obligatoria en T2.6.

**Qué hacer.** TDD estricto:
1. **RED:** test que afirme el comportamiento nuevo (p. ej. *«un negocio sin teléfono se
   descarta sin haber pagado Details»*), con el cliente de Places simulado y el medidor como
   testigo. Debe fallar.
2. **GREEN:** implementar el cambio mínimo.
3. **REFACTOR:** con la suite verde.
4. **Interruptor de reversa:** el cambio se desactiva con **una constante**, igual que los
   recortes de T2.4 del plan de agosto. Si en producción resulta que se pierden prospectos, se
   revierte sin desplegar código nuevo.
5. Verificar que la caché sigue funcionando y que el medidor sigue contando bien.

**Salida.** Código + tests + constante de reversa documentada en `RUNBOOK.md`.

**Criterio de cierre.** Suite ≥ baseline + nuevos; gates de review sin CRITICAL/HIGH.

---

### T2.5 — Tope duro por corrida y medidor vivo tras el rediseño

**Depende de:** T2.4 (o de T2.3 si se saltó T2.4).

**Contexto autocontenido.** El PR #38 dejó **dos topes**: por llamadas (funciona sin conocer
tarifas) y por dinero (requiere tarifas por entorno, **sin valor por defecto**: sin tarifa no
se publica importe). Ninguno se ha ejercitado en producción. Y el PR #43 movió los 4
contadores del medidor de `app.py` a `static/js/importador.js`: hay que comprobar que siguen
leyendo los mismos campos del backend. Además, el Plan 1 pudo ampliar el catálogo de ciudades,
lo que **multiplica el número de corridas posibles** y vuelve el tope algo más que un adorno.

**Qué hacer.**
1. Test que **fuerza** el tope de llamadas y verifica: la corrida termina en estado
   `presupuesto_agotado`, lo ya escrito en la hoja **se conserva**, y el operador ve por qué
   se detuvo. Verificarlo **en las dos direcciones**: sin el tope, la misma corrida sigue.
2. Verificar CE5 en el navegador: los 4 contadores muestran valores reales tras el rediseño.
3. Revisar que el tope por defecto sea **razonable para el catálogo ampliado** del Plan 1 y
   documentar cómo se ajusta.

**Salida.** Tests de tope + captura del medidor en vivo.

**Criterio de cierre.** **CE4 y CE5 verdes.**

---

### T2.6 — Verificación A/B: menos llamadas, mismos prospectos

**Depende de:** T2.5.

**Contexto autocontenido.** El riesgo de toda optimización de costo es ahorrar tirando
prospectos buenos. El plan de agosto resolvió esto bien y **hay que copiar su método, no
inventar otro**: comparó la lista de aprobados con y sin el recorte, obtuvo diff vacío, y
—esto es lo importante— **demostró que el chequeo era capaz de detectar pérdida** forzando
`MAX_VARIACIONES_SIN_APORTE=0`, que marcó 80 perdidos. Un cero solo vale si el método puede
dar distinto de cero.

**Qué hacer.**
1. Correr la misma ciudad con la configuración antigua y la nueva.
2. Diff de la lista de aprobados → debe ser **vacío** (CE3).
3. **Probar el chequeo en la dirección contraria**: forzar una configuración que sí pierda
   prospectos y comprobar que el diff los marca. Sin esto, el cero no es un resultado.
4. Conteo de llamadas antes/después (CE2).
5. Segunda corrida de la misma ciudad para confirmar que la caché sigue dando cache hits.

**Salida.** `docs/investigacion/2026-09-15-costo-places-despues-plan2.md`.

**Criterio de cierre.** **CE2 y CE3 verdes**, con la prueba de detección incluida.

---

### T2.7 — Cierre: PR, despliegue, documentación y relevo final de la tanda

**Depende de:** T2.6.

**Qué hacer.**
1. PR con `gh pr create --base main`; mergear **solo** con suite verde, CI verde y 0
   CRITICAL/HIGH.
2. Desplegar y correr el smoke. Verificar el medidor en el panel real.
3. `RUNBOOK.md`: cómo revertir el cambio con la constante, qué significa cada contador, cómo
   ajustar el tope. `CLAUDE.md`: baseline nuevo.
4. **CE6 (gate del owner):** dejar escrito, en un solo lugar, qué hace falta para leer el
   gasto en pesos (acceso a Google Cloud billing) y qué número se espera ver.
5. Cerrar PROGRESO, marcar el índice **4/4** y sobrescribir `RELEVO-actual.md` con el cierre
   de la tanda.

**Criterio de cierre.** Índice en 4/4 y relevo de cierre escrito.

---

## 3. TABLA DE ASIGNACIÓN DE HERRAMIENTAS, POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| **A** | T2.0 | `claude-mem:mem-search` | skill | claude-mem | El plan de agosto dejó trampas de medición (la caché falsea la 2.ª corrida) registradas en memoria. Repetirlas cuesta una tarea entera. |
| **A** | T2.0, T2.1 | `Explore` | agente | built-in | Recorrer `_buscar_negocios`, `_detalle_de_place` y `medir_llamadas_places.py` sin cargar `app.py` entero al contexto. |
| **A** | T2.1 | `performance-optimizer` | agente | catalogo-agentes | La fuga es un cuello de botella de recurso caro: instrumentar y medir antes de tocar es su método, no el de un reviewer. |
| **A** | T2.2 | `context7-mcp` | skill | ECC | **Obligatorio.** La regla del proyecto prohíbe tarifas de memoria; esto trae la documentación oficial vigente de Places API (New). |
| **A** | T2.2 | `documentation-lookup` | skill | ECC | Complemento: resuelve qué soporta `googlemaps 4.10.0`, que es la autoridad sobre lo que este proyecto puede pedir. |
| **A** | T2.1 | `cost-tracking` **[OPCIONAL]** | skill | community | **Condición de uso:** solo si el owner quiere una serie temporal del gasto, no una foto. |
| **B** | T2.2 | `data-analyst` | agente | catalogo-agentes | La tasa de desperdicio se mide sobre 3 ciudades de perfiles distintos: hay que leer dispersión, no promediar. |
| **B** | T2.3 | `council` | skill | community | Migrar de API es el tradeoff más caro de la tanda. El proyecto ya usó `council` en T3.5 y **cambió de opción** por una premisa falsa: el método se ha ganado su sitio aquí. |
| **B** | T2.3 | `architecture-decision-records` | skill | ECC | El ADR nuevo **anexa** al de agosto. El formato deja claro que no lo contradice. |
| **B** | T2.2 | `api-designer` **[OPCIONAL]** | agente | catalogo-agentes | **Condición de uso:** solo si se migra y hay que diseñar el field mask y el contrato del adaptador. |
| **C** | T2.4 | `superpowers:test-driven-development` | skill | superpowers | «No se paga Details para un negocio sin teléfono» es una afirmación verificable: el test va primero. |
| **C** | T2.4 | `tdd-guide` | agente | catalogo-agentes | Vigila que el test simulado del cliente de Places falle de verdad antes del fix. |
| **C** | T2.4 | `python-pro` | agente | catalogo-agentes | La ruta es Python con cliente HTTP y caché en disco: implementación idiomática. |
| **C** | T2.4 | `content-hash-cache-pattern` | skill | ECC | La caché de `place_id` → detalle se toca en T2.4; este patrón cubre invalidación y separación de capas. |
| **C** | T2.4 | `error-handling` | skill | ECC | El tope (`PresupuestoAgotado`) **no es un tropiezo de la API**: la distinción entre excepción de control y error de red ya existe en el código y hay que no romperla. |
| **C** | T2.4 | `django-build-resolver` **[OPCIONAL]** | agente | catalogo-agentes | **Condición de uso:** solo si migrar exige una dependencia nueva de pip. Único especializado en errores de pip/import de Python; **no hay build-resolver de Flask** en las 653. |
| **D** | T2.4, T2.5 | `python-reviewer` | agente | catalogo-agentes | **Reviewer del stack**, además de `code-reviewer`. |
| **D** | T2.4, T2.5, T2.7 | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio. |
| **D** | T2.4 | `security-reviewer` | agente | catalogo-agentes | **Obligatorio:** se toca una API externa con llave, la caché en disco (permisos 0600, `O_EXCL`) y datos de negocios. |
| **D** | T2.4, T2.5 | `silent-failure-hunter` | agente | catalogo-agentes | **Obligatorio.** El PR #38 encontró aquí **2 CRITICAL y 1 HIGH** de fallos tragados. Es la zona del repo con más antecedentes. |
| **D** | T2.5 | `python-testing` | skill | ECC | El test del tope necesita simular el cliente y el medidor: fixtures bien construidas. |
| **D** | T2.5 | `typescript-reviewer` | agente | catalogo-agentes | **Reviewer del stack para el front:** los 4 contadores viven ahora en `static/js/importador.js` (JavaScript) tras el PR #43. |
| **D** | T2.6 | `benchmark` | skill | ECC | Medición antes/después con método reproducible, no con dos corridas sueltas. |
| **D** | T2.6 | `superpowers:verification-before-completion` | skill | superpowers | Impide declarar CE2/CE3 sin la salida a la vista — y CE3 exige además la prueba en dirección contraria. |
| **D** | T2.5 | `webapp-testing` | skill | skills-local | Comprobación en navegador de CE5. (Fuente `skills-local`: no cuenta para diversidad.) |
| **E** | T2.7 | `github-ops` | skill | ECC | PR y merge con verificación de checks. |
| **E** | T2.7 | `canary-watch` | skill | ECC | Verificación del URL desplegado tras el merge. |
| **E** | T2.7 | `doc-updater` | agente | catalogo-agentes | `RUNBOOK.md` y `CLAUDE.md` al día. |
| **E** | T2.7 | `superpowers:finishing-a-development-branch` | skill | superpowers | Cierre ordenado de la última rama de la tanda. |
| **E** | T2.7 | `handoff` | skill | skills-local | Relevo de cierre de la tanda completa. |
| **Transversal** | todo | `blueprint` | skill | community | Formato de tareas autocontenidas. |
| **Transversal** | T2.1, T2.7 | **`ads-math`** | skill | claude-ads | **Uso obligatorio, no decorativo.** Traduce llamadas ahorradas a **costo por prospecto adquirido** — la única cifra que le dice al owner si ampliar el catálogo del Plan 1 es rentable. Es el puente entre el gasto técnico y la decisión de negocio. |

**Fuentes usadas en el Plan 2: 6 de 6 canónicas** + built-in.

---

## 4. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewers | Baseline | Gate extra |
|---|---|---|---|---|
| T2.0 | — | — | **≥ 626** | Medición comparada contra la línea de agosto |
| T2.1 | — | `performance-optimizer` | — | **CE1: un %, sobre 3 ciudades** |
| T2.2 | — | — | — | Toda tarifa **citada y fechada**; nada de memoria |
| T2.3 | — | `council` | — | ADR con alternativas y motivo de descarte |
| T2.4 | TDD: RED antes que GREEN | `python-reviewer` + `code-reviewer` + `security-reviewer` + `silent-failure-hunter` | ≥ 626 + nuevos | Constante de reversa documentada |
| T2.5 | Tope forzado en las **dos** direcciones | `python-reviewer` + `typescript-reviewer` + `code-reviewer` | ≥ 626 + nuevos | **CE4 y CE5** |
| T2.6 | A/B + prueba de detección de pérdida | — | ≥ 626 | **CE2 y CE3** |
| T2.7 | CI del PR en verde | `code-reviewer` | ≥ 626 sobre `main` | Smoke verde · índice 4/4 · CE6 escrito |

---

## 5. RIESGOS Y PLAN DE ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | La optimización **tira prospectos buenos** y nadie lo nota hasta que el owner reclama | Media | **Crítico** — el importador existe para traer prospectos | CE3 con diff de aprobados **y** prueba de que el chequeo detecta pérdida | Constante de reversa de T2.4: se apaga sin desplegar |
| R2 | Migrar a Places API (New) rompe la ruta que produce todo el valor | Media | Crítico | T2.3 decide con `council` y números; T2.4 exige TDD e interruptor | `git revert` del PR + la constante deja el camino legacy vivo |
| R3 | Se toman tarifas de memoria y el ahorro calculado es ficción | **Alta** (es el error natural del modelo) | Alto — decisión basada en un número inventado | Regla explícita en T2.2 + `context7-mcp` obligatorio + cita con fecha por afirmación | El ADR se corrige; no hay código que revertir si se detecta en T2.2 |
| R4 | La caché falsea la medición (2.ª corrida da 0 y parece un ahorro que no es) | **Alta** — ya pasó en agosto | Medio | Está documentado en `RUNBOOK.md` como trampa conocida; T2.0 mide ciudad virgen **y** trabajada por separado | Repetir la medición limpiando la caché |
| R5 | CE6 sigue bloqueado: nunca se sabe el gasto en pesos | **Alta** | Medio — se optimiza a ciegas en importe, no en llamadas | El conteo de llamadas es el sustituto y **es exacto**; CE6 se documenta como gate del owner, no se finge | Ninguno: es un gate externo |
| R6 | El tope por defecto se queda corto con el catálogo ampliado del Plan 1 y corta corridas legítimas | Media | Medio | T2.5 revisa el valor contra el catálogo real y documenta cómo ajustarlo | Variable de entorno: se sube sin desplegar |

**Rollback del plan completo:** `git revert` del merge + la constante de reversa de T2.4, que
devuelve la ruta de Places al comportamiento de `main` sin desplegar código nuevo.

---

## 6. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T2.0 | Tarea Cero: rama, respaldo y medición del gasto actual | **HECHO** | `docs/investigacion/2026-09-15-costo-places-antes-plan2.md` — 4 escenarios, **idénticos a la línea de agosto**: ningún plan de la tanda tocó la ruta de Places. Baseline **1,208 passed, 2 skipped**. Respaldo en `docs/auditoria/respaldos/2026-09-15-plan2/` | 🔍 **Hallazgo:** `MAX_VARIACIONES_SIN_APORTE` **no ahorra nada** — ponerlo en 99 no cambia una llamada. Todo el ahorro de Text Search (18→13) lo hace el corte **por página**. Y el doble de prueba **aprueba a todos**, así que T2.1 mediría **cero** desperdicio si no se amplía el fixture |
| T2.1 | Cuantificar la fuga de Details | 🟡 **PARCIAL — CE1 no cerrado** | `docs/investigacion/2026-09-15-fuga-details-sin-telefono.md` + `tools/medir_fuga_details.py`. **Mecanismo medido y es 1:1**: los Details pagados son **80 siempre**, la tasa de descartes no ahorra una sola llamada. **Fuga cero en ciudad ya trabajada.** Y el **DENUE (75,726 ferreterías, SCIAN 467111): 58.6 % sin teléfono**, plano entre metrópoli/media/chica (58.8 / 59.1 / 58.0) | 🔴 **Falta la tasa REAL de Google** — sólo sale de una corrida real (gate del owner). El DENUE es **otra fuente**, no Google. 🪤 El fixture de T2.0 aprobaba a todos: habría dado **cero fuga** y cancelado el plan por un defecto del instrumento |
| T2.2 | Evaluar Places API (New): ¿viene el teléfono en el `searchText`? | **HECHO** | `docs/investigacion/2026-09-15-places-new-field-mask.md` — **SÍ**: `places.nationalPhoneNumber` está en el field mask de `searchText`, **en el mismo SKU (Text Search Enterprise) que `rating` y `userRatingCount`**, que el importador ya necesita. **El teléfono sale gratis.** Tres opciones con ahorro y coste, cada tarifa citada (pricing «Last updated 2026-09-16 UTC») | **13 TS Enterprise + 0 Details = $0.455/ciudad** contra **$2.016** migrando «tal cual»: **−77 %**, ≈ **$1,567** en el barrido de 1,004 ciudades. El coste real **no es la llamada: son los dobles** — `googlemaps 4.10.0` **no habla la API New** (0 coincidencias de `searchText`/`X-Goog-FieldMask`), así que hay que ir por HTTP directo y reescribir el andamiaje de medición. ⚠️ El crédito de $200/mes **caducó el 2025-02-28** |
| T2.3 | Decidir y dejarlo escrito (ADR) | **HECHO** | `docs/adr/2026-09-15-ruta-de-telefono-places.md` — `council` de 2 voces (riesgo operativo · negocio). **Decisión: NO migrar todavía; antes una Fase 0 de 13 llamadas que no escribe nada** (≈ $0.46) y que mide la coincidencia de `_clave_contacto` **y cierra CE1** | **Las dos voces llegaron a «migrar después» por caminos distintos y coincidieron en la condición: medir antes de decidir.** El modo de fallo que decide: `_clave_contacto` (`app.py:3104`) es una concatenación cruda calculada en **3 sitios que deben coincidir carácter a carácter** y **sin guarda** — un cambio de formateo llenaría la hoja de duplicados **sin una sola excepción**. Fuente citada: legacy **sin fecha de retiro** y **12 meses de aviso** |
| T2.4 | Implementar el ahorro elegido | **HECHO (como Fase 0)** | `tools/comparar_places_new.py` + `tests/test_comparar_places_new.py` (**13 tests**, TDD: RED `ModuleNotFoundError` → GREEN). Suite **1,208 → 1,221**. Sección nueva del RUNBOOK con los tres códigos de salida | **El ADR decidió no migrar**, así que T2.4 se reduce a la Fase 0: la herramienta que **mide sin escribir**. 🪤 La mutación destapó **un test mío débil**: probaba el campo *ausente* creyendo probar el campo *vacío*, y daba verde con la implementación rota. Corregido; 5 de 5 guardas detectan su defecto |
| T2.5 | Tope duro y medidor vivo tras el rediseño | PENDIENTE | | |
| T2.6 | Verificación A/B sin pérdida de calidad | PENDIENTE | | |
| T2.7 | Cierre: PR, despliegue, docs y relevo final | PENDIENTE | | |

**Avance del plan: 0 / 8 tareas (0 %)**

**Supuestos vivos de este plan:**
- `SUPUESTO: «tokens de la API» = consumo facturable de Google Places (única API de pago del proyecto; PanelNioval no usa ningún LLM). — afecta Plan 2 completo. Ver D2 del índice.`
- `SUPUESTO: si la fuga medida en T2.1 es < 10 %, la migración no se paga sola y T2.2–T2.4 se saltan. — afecta Plan 2, Tareas T2.2 a T2.4.`
