# ÍNDICE DE LA TANDA — PanelNioval

**Diseñado:** 2026-08-27 · **Validado y ampliado:** 2026-08-28
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Biblioteca de herramientas leída:** `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` —
**653 herramientas (229 agentes + 424 skills)** de **6 fuentes**: catalogo-agentes, ECC,
claude-ads, community, claude-mem y superpowers, más el built-in de Claude Code.
**Toolkit del proyecto:** no existe (`.claude/` está vacío; no hay `.claude/toolkit-*.md`).

**Baseline verificado en disco el 2026-08-28:** `python -m pytest tests/` → **357 passed,
1 skipped**, exit 0.
⚠️ **Sin `-q`.** `pytest.ini` ya trae `addopts = -q`; el segundo lo convierte en `-qq`, que
**suprime la línea del resumen**: se ven los puntos y `exit 0`, pero nunca el número.

---

## 0. QUÉ CAMBIÓ EL 2026-08-28

Esta tanda se diseñó el 2026-08-27 con `app.py` en 4,948 líneas y la suite en 230 tests.
Desde entonces se ejecutaron el **Plan 3 completo** y **7 de las 9 tareas del Plan 2**, y el
archivo creció a **6,098 líneas**. Todos los planes se **revalidaron contra el código en
disco**.

Detalle completo, hallazgo por hallazgo, en
[`2026-08-28-validacion-tanda.md`](2026-08-28-validacion-tanda.md). Resumen:

| Qué se hizo | Dónde quedó |
|---|---|
| 30 anclajes de `app.py` verificados; los obsoletos corregidos | §0 nueva en los planes 1, 2 y 4 |
| Baseline `230` → `357` en todos los gates prospectivos | Editado en los tres documentos, verificado en disco |
| Comando oficial corregido: `pytest tests/` sin `-q` | Todos los documentos |
| **Dos tareas del Plan 1 ya estaban hechas** (B9 y B11) | Plan 1 §0.2 — se verifican, no se reimplementan |
| **M13 quedó obsoleta** (el escape ya existe en el importador) | Plan 4 §0.2 |
| **CE1 del Plan 4 es inalcanzable con T4.3 sola** | Plan 4 §0.3 + decisión **D1** |
| **CE6 del Plan 2 no se puede cumplir en pesos** (gate del owner) | Plan 2 §0.3 + decisión **D2** |
| Dos planes recomendados en §4 y nunca redactados, ahora escritos | **Plan 0** (CI) y **Plan 5** (endurecimiento) |

---

## 1. LOS SEIS PLANES

| Plan | Documento | Tareas | Qué resuelve |
|---|---|---|---|
| **0** ⭐ | [`2026-08-28-plan0-integracion-continua.md`](2026-08-28-plan0-integracion-continua.md) | 4 | **Nuevo.** No hay CI: los 357 tests solo corren si alguien se acuerda. Convierte "nada se mergea en rojo" de intención en mecanismo. Origen: mejora M1. |
| **1** | [`2026-08-27-plan1-relevancia-ciudades-nacional.md`](2026-08-27-plan1-relevancia-ciudades-nacional.md) | 10 | El orden de ciudades del importador mide el historial de NIOVAL, no la relevancia del ramo ferretero en México. Catálogo canónico por macro-región. |
| **2** | [`2026-08-27-plan2-optimizacion-gasto-places.md`](2026-08-27-plan2-optimizacion-gasto-places.md) | 9 | Google Places se paga de más: Details sin `fields`, pagados antes de deduplicar, sin caché y sin medidor. **7/9 hechas.** |
| **3** ✅ | [`2026-08-27-plan3-bug-conteo-y-pantallas-carga.md`](2026-08-27-plan3-bug-conteo-y-pantallas-carga.md) | 10 | "Dice 20 y aparecen 10" + pantallas de carga rotas. **COMPLETADO**, PR #36 mergeado (`ae0e1c9`). |
| **4** | [`2026-08-27-plan4-rediseno-profesional-panel.md`](2026-08-27-plan4-rediseno-profesional-panel.md) | 12 | Rediseño profesional de las 3 superficies: movimiento, presentación y estados de carga. |
| **5** ⭐ | [`2026-08-28-plan5-endurecimiento-panel.md`](2026-08-28-plan5-endurecimiento-panel.md) | 8 | **Nuevo.** Cinco huecos sin dueño: sin rate limiting, escape de fórmulas en una sola ruta, contenedor en UTC, sin healthcheck, hilo que muere en silencio. Origen: M5, M14, M2, M9, M3. |

**Total: 53 tareas.** (Eran 41 antes de redactar los planes 0 y 5.)

---

## 2. ORDEN DE EJECUCIÓN Y DEPENDENCIAS

**El orden NO es el de numeración.** Es **0 → 2 → 1 → 4 → 5**, con el Plan 3 ya cerrado.

```
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 3 — BUG DE CONTEO Y PANTALLAS DE CARGA      ✅ 10/10 CERRADO  │
│ PR #36 mergeado (ae0e1c9). Baseline 230 → 314.                     │
│ Entregó: dedup por corrida (T3.3), progreso con denominador        │
│ ajustable (T3.6), escapado del nombre de ciudad (T3.7).            │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 0 — INTEGRACIÓN CONTINUA                     4 tareas  ⭐NUEVO│
│ No toca app.py. 4 tareas, riesgo mínimo. A partir de aquí, los PR  │
│ de los planes 2, 1, 4 y 5 llevan check automático — incluido el    │
│ PR #38 del Plan 2, que sigue en borrador.                          │
│ Ver decisión D4: si el owner lo pospone, el orden arranca en 2.    │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: el gate deja de ser manual
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 2 — OPTIMIZACIÓN DEL GASTO DE PLACES        7/9 EN CURSO      │
│ Rama perf/gasto-places-importador · PR #38 en BORRADOR.            │
│ Queda T2.7 (verificación A/B + diff CE7) y T2.8 (cierre).          │
│ Bloqueo real: el consumo por SKU es gate del owner. Ver D2.        │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: medidor de costo + tope por corrida
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 1 — RELEVANCIA DE CIUDADES A NIVEL NACIONAL  10 tareas        │
│ Independiente en backend; su UI aterriza en el importador.         │
│ Va antes de 4 para que el rediseño sepa cuántos chips acomodar.    │
│ Ojo: T1.7·5 (B9) y B11 YA ESTÁN HECHOS — verificar, no duplicar.   │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: catálogo canónico + filtro por región
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 4 — REDISEÑO PROFESIONAL DEL PANEL           12 tareas        │
│ Consume los 4 contadores del Plan 3, el medidor del Plan 2 y el    │
│ filtro por región del Plan 1. Rediseñar antes sería rediseñar      │
│ sobre un blanco móvil.                                             │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: templates/ y static/ separados
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 5 — ENDURECIMIENTO DEL PANEL                 8 tareas  ⭐NUEVO│
│ Va al final porque T5.5 toca el worker del importador, que los     │
│ planes 2 y 4 están moviendo. Ver D5 sobre memoria vs Redis.        │
│ NO cierra los dos gates del owner (rotar Telegram, apagar Railway),│
│ que siguen siendo el riesgo más grande del proyecto.               │
└────────────────────────────────────────────────────────────────────┘
```

### 2.1 Dependencias explícitas entre planes

| Origen | Destino | Qué se traspasa | Instrucción al ejecutor |
|---|---|---|---|
| Plan 3 · T3.3 | Plan 2 · T2.3 | Set de `place_id` a nivel corrida | ✅ **YA REUTILIZADO**. Son **dos** conjuntos a propósito: `vistos` y `con_detalle`. Para reportar ahorro usar `incidencias['detalles_evitados']`, **no** `ya_vistos_otra_cat` |
| Plan 3 · T3.6 | Plan 2 · T2.4 | Denominador de progreso ajustable | ✅ **YA REUTILIZADO**. Recortar variaciones solo pide bajar `BASE_POR_CATEGORIA` |
| Plan 3 · T3.7 | Plan 1 · T1.7 | Escapado del nombre de ciudad (B9) | ✅ **YA HECHO** (`app.py:5810`). T1.7 **verifica con un test y no duplica** |
| Plan 3 · T3.2 | Plan 4 · T4.9 | Los 4 contadores separados | El rediseño les da jerarquía; `nuevos_en_sheet` es el número grande. La rejilla ya es de 4 columnas (`app.py:5566`) |
| Plan 2 · T2.6 | Plan 4 · T4.9 | Medidor de costo y estado `presupuesto_agotado` | ✅ Ya existe en la UI como estado terminal. El rediseño le da forma; **no es un error** |
| Plan 1 · T1.7 | Plan 4 · T4.9 | Filtro por macro-región | El rediseño le da forma; no rehace la lógica |
| Plan 4 · T4.3 | — | Extracción del HTML de `app.py` | **Bloquea** T4.4–T4.9; commit aislado |
| Plan 0 · T0.1 | Planes 2, 1, 4, 5 | Check de tests en cada PR | Todos los PR posteriores lo llevan; ninguno lo reimplementa |
| Plan 2 · T2.6 | Plan 5 · T5.5 | Patrón de salida limpia (`presupuesto_agotado`) | T5.5 **reutiliza** ese camino para `SIGTERM`; no crea un segundo |

### 2.2 Riesgo de solapamiento

Los planes 1, 2, 4 y 5 tocan `/importador` o su worker. Ejecutarlos en paralelo garantiza
conflictos sobre las mismas líneas de `app.py`. **Se ejecutan en secuencia**, una rama por
plan, rebasando sobre `main` ya actualizado con el plan anterior. El Plan 0 es la única
excepción: no toca `app.py` y puede correr en paralelo con cualquiera.

---

## 3. RESUMEN DE ASIGNACIÓN DE HERRAMIENTAS POR FUENTE

Auditoría de diversidad de un vistazo. ✅ = la fuente se usa con herramientas asignadas a
tareas concretas; ⚠️ = evaluada y descartada con justificación por escrito.

| Fuente | Plan 0 | Plan 1 | Plan 2 | Plan 3 | Plan 4 | Plan 5 |
|---|---|---|---|---|---|---|
| **catalogo-agentes** (229 agentes) | ✅ 9 | ✅ 12 | ✅ 8 | ✅ 10 | ✅ 12 | ✅ 11 |
| **ECC** (~200 skills) | ✅ 7 | ✅ 9 | ✅ 9 | ✅ 9 | ✅ 10 | ✅ 9 |
| **community** (~41 skills, incl. blueprint) | ✅ 2 | ✅ 2 | ✅ 4 | ✅ 3 | ✅ 5 | ✅ 2 |
| **claude-mem** (~18 skills) | ✅ 2 | ✅ 3 | ✅ 1 | ✅ 2 | ✅ 2 | ✅ 1 |
| **superpowers** (14 skills) | ✅ 3 | ✅ 4 | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 4 |
| **claude-ads** (~60 herramientas) | ⚠️ N/A justificado | ✅ 1 (opcional) | ✅ 1 | ⚠️ N/A justificado | ✅ 1 | ⚠️ N/A justificado |
| **built-in** (Explore, dataviz…) | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 2 | ✅ 1 |
| **Fuentes canónicas usadas** | **5/6** | **6/6** | **6/6** | **5/6** | **6/6** | **5/6** |

Los seis planes superan el mínimo de 5 fuentes. Los tres descartes de `claude-ads` están
justificados herramienta por herramienta —incluido `ads-math`, que es la única con encaje
plausible— y no con un "no aplica" genérico.

### 3.1 Herramientas más usadas, por fuente

- **catalogo-agentes** — `code-reviewer`, `python-reviewer`, `security-reviewer`,
  `silent-failure-hunter`, `tdd-guide`, `python-pro`, `debugger`, `performance-optimizer`,
  `refactoring-specialist`, `deployment-engineer`, `devops-engineer`, `docker-expert`,
  `security-engineer`, `security-auditor`, `ui-designer`, `ux-researcher`, `a11y-architect`,
  `accessibility-tester`, `market-researcher`, `data-researcher`, `api-designer`,
  `code-architect`, `pr-test-analyzer`, `doc-updater`, `technical-writer`,
  `django-build-resolver` (ver §3.3).
- **ECC** — `python-testing`, `verification-loop`, `github-ops`, `git-workflow`,
  `backend-patterns`, `frontend-patterns`, `architecture-decision-records`, `benchmark`,
  `benchmark-optimization-loop`, `content-hash-cache-pattern`, `documentation-lookup`,
  `deployment-patterns`, `docker-patterns`, `error-handling`, `security-review`,
  `orch-fix-defect`, `orch-refine-code`, `design-system`, `motion-ui`, `ui-ux-pro-max`,
  `accessibility`, `browser-qa`, `canary-watch`, `market-research`, `deep-research`.
- **community** — `blueprint` (los seis planes), `council` (3 decisiones con tradeoff real),
  `click-path-audit`, `frontend-design-direction`, `impeccable`,
  `make-interfaces-feel-better`, `frontend-a11y`, `production-audit`, `cost-tracking`.
- **claude-mem** — `mem-search` (los seis planes, etapa A), `timeline-report`, `babysit`,
  `design-is`.
- **superpowers** — `test-driven-development`, `systematic-debugging`, `brainstorming`,
  `verification-before-completion`, `finishing-a-development-branch`.
- **claude-ads** — `ads-math` (Plan 2, uso obligatorio: traduce el ahorro a costo por
  prospecto), `ads-dna` (Plan 4, uso literal: formaliza el ADN de marca ya existente).
- **built-in** — `Explore` (barridos sin quemar contexto), `dataviz` (gráficas del dashboard).

### 3.2 Nota de honestidad: la etiqueta `skills-local`

El **Nivel 2** de la biblioteca usa una etiqueta de fuente más fina que la tabla de Fuentes
del encabezado: `skills-local`, que **no es una de las 6 fuentes canónicas**. Aparece en
herramientas que los planes sí usan (`webapp-testing`, `handoff`, `web-perf`,
`review-animations`, `web-design-guidelines`, `xlsx`). Mapearlas a una de las 6 sería
inventar el dato, así que **se reportan tal cual y no cuentan** para el mínimo de diversidad.
Los seis planes cumplen el mínimo sin ellas.

Hay además **dos entradas con fuente discrepante entre niveles**: `council` e `impeccable`
figuran como `community` en la Matriz Nivel 1 y como `ECC` / `skills-local` en el Catálogo
Nivel 2. Se cita la atribución del **Nivel 1**, que es la matriz que las reglas mandan usar
primero.

### 3.3 El stack no tiene build-resolver propio, y se dice

La regla de la biblioteca exige asignar el build-resolver específico del stack donde exista.
**Para Flask puro no existe.** El catálogo tiene `django-build-resolver` (pip, Poetry,
`ImportError`, configuración), `build-error-resolver` (TypeScript), y los de Go, Rust, Java,
Kotlin, Swift, C++, React, Dart y PyTorch. Ninguno es de Flask.

Se asigna **`django-build-resolver` marcado [OPCIONAL]**, con su condición de uso, en los
planes 0 y 5 —los dos que instalan dependencias nuevas (`Flask-Limiter`, `tzdata`)— porque
es el único especializado en errores de pip e importación en Python; su parte de Django
simplemente no se ejercita. Se prefiere al genérico `build-error-resolver`, que es de otro
lenguaje. Esta es la constancia de que se evaluó y no se omitió en silencio.

---

## 4. MEJORAS PROPUESTAS (no pedidas)

Detectadas al leer el código. Estado **reverificado en disco el 2026-08-28**.

### 4.1 Alto impacto · Bajo esfuerzo

| # | Mejora | Estado al 2026-08-28 | Dónde encaja |
|---|---|---|---|
| **M1** | **No hay CI.** `ls -d .github` sigue fallando. Los 357 tests solo corren si alguien se acuerda. | 🔴 **ABIERTA** | ✅ **Redactada como Plan 0** (4 tareas) |
| **M2** | **Zona horaria del contenedor.** 6 `datetime.now()` sin `tzinfo` (`app.py:3092`, `3202`, `3521`, `3594`, `5079`, `5080`), `Dockerfile` sin `ENV TZ`. Todo lo capturado tras las 18:00 se guarda con la fecha del día siguiente, y la semana ISO de la gráfica del dashboard puede caer mal. | 🔴 **ABIERTA** | ✅ **Plan 5 · T5.3** |
| **M3** | **El hilo del importador es `daemon=True`** (`app.py:5473`). | 🟡 **PARCIAL** — el Plan 3 añadió el registro persistido (`app.py:4644`) que ya permite decir "se interrumpió". Falta que el reinicio no parta una escritura | ✅ **Plan 5 · T5.5** |
| **M4** | **Telegram solo avisaba en el camino feliz.** | ✅ **RESUELTA** en el Plan 3 · T3.4 | — |

### 4.2 Alto impacto · Esfuerzo medio

| # | Mejora | Estado al 2026-08-28 | Dónde encaja |
|---|---|---|---|
| **M5** | **Cero rate limiting.** `grep -c "limiter\|Limiter" app.py` → **0**. Un token filtrado da barra libre, incluida la capacidad de disparar corridas de Places que cuestan dinero. | 🔴 **ABIERTA** | ✅ **Plan 5 · T5.1** |
| **M6** | **La exposición de Railway sigue viva** sin `PANEL_DASHBOARD_TOKEN`. | 🔴 **GATE DEL OWNER** desde el 2026-08-17 | Ningún plan lo cierra: hace falta apagar el despliegue |
| **M7** | **Rotar el token de Telegram** (expuesto en el historial, ~14 copias). Quitarlo del código no lo rota. | 🔴 **GATE DEL OWNER** | 2 minutos en BotFather. Es el riesgo de seguridad más grande abierto |
| **M8** | **Un solo trabajo de importación a la vez, global.** | 🟡 Sin cambio, pero el Plan 3 dejó la puerta abierta | Fuera de alcance del Plan 5: es feature, no hueco de seguridad |

### 4.3 Impacto medio

| # | Mejora | Estado al 2026-08-28 | Dónde encaja |
|---|---|---|---|
| **M9** | **No hay healthcheck.** `grep -c HEALTHCHECK Dockerfile` → **0**, ni en `despliegue/docker-compose.yml`. | 🔴 **ABIERTA** | ✅ **Plan 5 · T5.4** |
| **M10** | **La corrida es estrictamente serial**: `time.sleep` por Details y por página. | 🟡 Menos relevante tras el Plan 2: en una ciudad ya trabajada los Details bajaron de 80 a 0 | Solo si tras medir el tiempo sigue siendo el problema |
| **M11** | **Archivos de otro proyecto en `docs/`.** | ✅ **RESUELTA** en `e6f25fc` (apartados a `docs/auditoria/respaldos/2026-08-28/otros-proyectos/`). Queda `Nuevo documento de texto.txt` sin versionar en la raíz | Limpieza menor |
| **M12** | **`app.py` viola el límite de 800 líneas** — ahora con **6,098**, de las cuales **5,067 son HTML** y **1,031 Python**. | 🔴 **ABIERTA y peor que en agosto** | **Plan 4 · T4.3** la resuelve en su mayor parte. Ver decisión **D1** |

### 4.4 Deuda técnica menor

| # | Mejora | Estado al 2026-08-28 | Dónde encaja |
|---|---|---|---|
| **M13** | El escape de HTML faltaba en el importador. | ✅ **OBSOLETA** — el Plan 3 lo introdujo (`app.py:5810`). T4.3 solo elimina la duplicación | Plan 4 |
| **M14** | `_escapar_formula` (`app.py:5037`) se usa **solo** en `app.py:5115`. Las demás rutas que escriben a Sheets no lo pasan. | 🔴 **ABIERTA y confirmada hoy** | ✅ **Plan 5 · T5.2** |
| **M15** | El logo de Cloudinary sin `width`/`height` → salto de layout. **Tres** sitios: `app.py:1172`, `3736`, `5594`. | 🔴 ABIERTA | **Plan 4 · T4.10** |
| **M16** ⭐ | **Nueva.** `Nuevo documento de texto.txt` vacío en la raíz, sin versionar, sobreviviente de la limpieza M11. | 🟡 Cruft | Se **aparta** al respaldo fechado (regla 4), no se borra |

### 4.5 Secuencia recomendada, con las mejoras dentro

```
PLAN 0   CI con pytest en cada PR                    ← M1                    ⭐NUEVO
        ▼
PLAN 3   Bug de conteo y pantallas de carga  ✅ CERRADO  (resolvió M4, M13)
        ▼
PLAN 2   Optimización del gasto de Places    7/9      (mitigó M10)
        ▼
PLAN 1   Relevancia de ciudades nacional
        ▼
PLAN 4   Rediseño profesional                          ← M12 parcial, M15
        ▼
PLAN 5   Endurecimiento del panel            ← M5, M14, M2, M9, M3          ⭐NUEVO

GATES DEL OWNER, en paralelo y sin depender de nada:  M6 (Railway), M7 (rotar Telegram)
```

---

## 5. AUTOEVALUACIÓN (PASO 4)

Respondida con los seis documentos delante y los `grep` en disco.

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | ¿Cuántas fuentes usa cada plan (mín. 5 de 6)? | Plan 0: **5/6** · Plan 1: **6/6** · Plan 2: **6/6** · Plan 3: **5/6** · Plan 4: **6/6** · Plan 5: **5/6**. Los tres descartes son de `claude-ads`, justificados herramienta por herramienta |
| 1b | ¿Aparecen ECC, claude-mem, catalogo-agentes y community además de superpowers? | **Sí, en los seis.** `blueprint` (community) es el formato de los seis; `mem-search` (claude-mem) abre la etapa A de los seis; superpowers aporta 3-4 skills de proceso por plan y **nunca sustituye** al especialista: `superpowers:test-driven-development` va siempre con `tdd-guide` (catalogo-agentes) y `python-testing` (ECC) |
| 2 | ¿Se asignó el reviewer/build-resolver específico del stack? | **Reviewer sí**: `python-reviewer` en toda tarea que toca código, **sumado** a `code-reviewer`. **Build-resolver: no existe para Flask puro** — ver §3.3, donde se asigna `django-build-resolver` [OPCIONAL] con su condición y se explica por qué no `build-error-resolver` |
| 3 | ¿Toda tarea tiene etapa D? ¿Toda tabla PROGRESO está pre-poblada? | Etapa D en **las 39 tareas que producen código**. Las 14 restantes son de investigación, diseño, tarea cero o cierre y llevan criterio de cierre explícito y comprobable (documento con N fuentes citadas, respaldo listado con tamaño > 0, ADR con alternativas descartadas). Cada plan tiene además una tarea de verificación integral dedicada: T0.3, T1.8, T2.7, T3.8, T4.10, T5.6. Las **seis** tablas PROGRESO están pre-pobladas |
| 4 | ¿Se diseñaron los planes COMPLETOS sin interrumpir con preguntas? | **Sí.** Seis documentos completos. Cinco supuestos marcados `SUPUESTO:` en su punto exacto (Plan 1 §0.4 ×2, Plan 2 §0.3 y §0.4, Plan 4 §0.3, Plan 5 §2.1 ×2) y todas las dudas acumuladas en **un solo bloque al final** |
| 5 | ¿Las decisiones pendientes son ≤5, cerradas, ancladas, con default e impacto? | **Sí: exactamente 5.** Cada una cita `Plan N, Tarea M`, tiene 2-3 opciones excluyentes sin campo libre, una marcada `(recomendada)` con motivo en una línea, y el impacto declarado sobre tareas concretas |

**¿Se corrigió algo antes de entregar?** Cuatro cosas. (1) Los planes citaban `pytest -q`,
que con el `addopts` del proyecto oculta el número: corregido en los tres documentos.
(2) Se descubrió que **dos entregables del Plan 1 ya estaban hechos** (B9 y B11) y se
convirtieron de "implementar" a "verificar", que era el riesgo de trabajo duplicado más
caro de la tanda. (3) CE1 del Plan 4 se declaró inalcanzable con la tarea que lo debía
cumplir, en vez de dejarlo como criterio que se incumpliría en silencio. (4) Se comprobó que
`.env.example` **existe y está versionado**, así que el gate 5 del owner no es "crear el
archivo" sino "añadirle cinco nombres"; el bloque exacto está en §7.

---

## 6. MARCADOR DE PROGRESO GLOBAL

| Plan | Tareas | Estado | Avance |
|---|---|---|---|
| Plan 3 — Bug de conteo y pantallas de carga | 10 | ✅ **COMPLETADO** | **10 / 10** |
| Plan 0 — Integración continua ⭐ | 4 | ✅ **COMPLETADO** | **4 / 4** |
| Plan 2 — Optimización del gasto de Places | 9 | ✅ **COMPLETADO** | **9 / 9** |
| Plan 1 — Relevancia de ciudades nacional | 10 | ✅ **COMPLETADO** | **10 / 10** |
| Plan 4 — Rediseño profesional del panel | 12 | EN CURSO | **10 / 12** |
| Plan 5 — Endurecimiento del panel ⭐ | 8 | PENDIENTE | 0 / 8 |

**PROGRESO GLOBAL: 43 / 53 tareas (81 %) · 4 de 6 planes completados**

> Sobre el alcance original de 4 planes (41 tareas), el avance es **21 / 41 (51 %)**. El
> denominador subió porque se redactaron dos planes que el §4 recomendaba y nadie había
> escrito, no porque se haya perdido trabajo.

> El ejecutor actualiza esta tabla al cerrar cada tarea, y la tabla PROGRESO del documento
> del plan correspondiente, con evidencia (commit / test / PR) y fecha.

---

## 7. REGLAS QUE APLICAN A LOS SEIS PLANES

Salen de `CLAUDE.md` del proyecto y de las reglas globales del entorno. No son opcionales.

1. **Nunca trabajar en `main`.** Railway y Vultr despliegan desde ahí. Una rama por plan.
2. **Baseline oficial, y es POR RAMA.** `python -m pytest tests/`, **sin `-q`**. Medido el
   2026-08-28: `main` → **314 passed**; `perf/gasto-places-importador` (Plan 2) → **357
   passed, 1 skipped**, porque añade 43 tests suyos; tras el Plan 0, `main` → **345
   passed**. El «357» que este índice daba como número absoluto era el de la rama del
   Plan 2, y un gate escrito «≥ 357» resultaba **inalcanzable** desde cualquier rama
   basada en `main` hasta que el Plan 2 mergeara. **Comparar contra el baseline de la
   rama base del PR, nunca contra un número fijo.** Nada se mergea con la suite en rojo.
   Desde el 2026-08-28 esto ya no depende de que alguien se acuerde: lo comprueba
   `.github/workflows/tests.yml` en cada PR.
3. **Respaldo antes del cambio, no después.** `python tools/respaldar_hojas.py docs/auditoria/respaldos/<fecha>`,
   y se confirma que el archivo existe **en disco, con tamaño > 0**, antes de seguir.
4. **Nada se borra: se aparta** al respaldo fechado. Vale para archivos, configuración y cruft.
5. **Datos personales:** teléfonos, nombres y correos de clientes no se commitean ni se
   vuelcan completos en logs. Enmascarar `+52…XXXX`.
6. **Credenciales:** nunca por valor. Se identifican por nombre de variable y `archivo:línea`,
   o por prefijo+sufijo enmascarado.
7. **Commits convencionales en español:** `fix:`, `feat:`, `test:`, `docs:`, `chore:`,
   `refactor:`. Mensajes en ASCII.
8. **Un barrido que no encuentra nada no demuestra que no hay nada.** Verificar en las dos
   direcciones: que encuentra un positivo conocido **y** que no marca un negativo conocido.
9. **Una operación que no encuentra nada tampoco se queja.** Un reemplazo por patrón que no
   casa devuelve el texto igual sin error. Verificar que el cambio está **en el archivo**.
10. **Los scripts de análisis no llaman a APIs de pago.** La única API facturable es Google
    Places; su gasto se mide y se acota en el Plan 2.
11. **`git add docs/` arrastra archivos de otro proyecto.** Añadir siempre por ruta explícita.
12. **Un `\n` escrito a mano en un heredoc no llega literal a Python.** Los reemplazos con
    `\\n` no casan y devuelven el texto igual, sin error. Usar coincidencia por línea o
    `chr(92) + "n"`, y verificar con `grep` sobre el archivo.

### 7.1 Gates del owner, abiertos

Ninguno se puede cerrar desde una sesión de Claude. Se **reportan**, no se intentan.

| # | Gate | Bloquea |
|---|---|---|
| 1 | **Consumo por SKU de Places** en la consola de Google Cloud (proyecto `bubbly-subject-412101`). Los conteos ya están; falta el multiplicador | CE6 del Plan 2 **en pesos**. Ver decisión **D2** |
| 2 | **Corrida real de la ciudad de referencia.** Factura la API y escribe en `LISTA DE CONTACTOS` de producción | CE7 del Plan 2 y CE1 del Plan 3 |
| 3 | **Verificación con gunicorn real en el VPS** (no corre en Windows: necesita `fcntl`) | CE5 del Plan 3 |
| 4 | **Recargar `/importador` a media corrida** en un navegador | CE7 del Plan 3 |
| 5 | **Añadir a `.env.example` los nombres de las 5 variables de Places.** El archivo **existe y está versionado** (21 líneas), pero ninguna de las cinco está. El entorno de Claude bloquea escribir archivos `.env*` | Documentación del Plan 2 · T2.8 |
| 6 | **Validación humana del top-20 de ciudades** | Plan 1 · T1.8 |
| 7 | **Rotar `TELEGRAM_TOKEN`** (expuesto en el historial git, ~14 copias) | Nada técnico, pero es el riesgo abierto más grande |
| 8 | **Apagar el despliegue de Railway** (sigue vivo sin `PANEL_DASHBOARD_TOKEN`) | Cierre de M6 |
| 9 | **Activar la protección de rama en `main`** (permisos de administrador del repo) | Que el check del Plan 0 impida el merge, no solo lo informe |

**Bloque exacto para el gate 5**, para pegar al final de `.env.example` (solo nombres, sin
valores):

```
# --- Google Places: medidor de gasto y topes (Plan 2) ---
# Tarifas por llamada. SIN valor por defecto a proposito: sin tarifa no se
# publica importe, porque un 0.00 afirmaria que la corrida salio gratis.
PLACES_COSTO_TEXT_SEARCH=
PLACES_COSTO_DETAILS=
# Topes por corrida. El de llamadas funciona siempre; el de dinero necesita
# las dos tarifas de arriba.
PLACES_MAX_LLAMADAS_CORRIDA=
PLACES_PRESUPUESTO_CORRIDA=
# Cache de detalles de Places. Lleva TELEFONOS de negocios (dato personal):
# 0600, en .gitignore y en .dockerignore. Por defecto va al temp del sistema.
PLACES_CACHE_FILE=
```

---

## 7.2 DECISIONES RESUELTAS POR EL OWNER (2026-08-28)

Surgieron al ejecutar los planes 0 y 2. Todas contestadas el 2026-08-28.

| # | Anclada a | Decisión | Qué implica |
|---|---|---|---|
| **E1** | Plan 0 · T0.2 | **A) El barrido pasa a `--estricto` tras 2-3 semanas sin falsos positivos**, no antes | Hoy **avisa y no bloquea**. Revisar el **2026-09-18**: si el ruido acumulado sigue siendo el de fixtures y commits de teléfonos, añadir `--estricto` al paso `Barrer las lineas anadidas` de `tests.yml`. **Antes de activarlo hay que endurecer `barrido-ok`**: con el job bloqueando, esa marca pasa de silenciar un aviso a saltarse un gate (señalado por `security-reviewer`, MEDIUM). Ya exige motivo escrito; faltaría restringirla a `tests/` o pedir segunda aprobación |
| **E2** | Plan 0 · T0.3 | **A) La cobertura se reporta y no bloquea** | Medida: **69 %** global, `app.py` **52 %**, `tools/barrer_secretos.py` 98 %. Se descartó B (gate duro al 69 % con trinquete) porque congelaría `app.py` justo cuando el **Plan 4 · T4.3** va a mover 5,067 líneas de HTML fuera: el porcentaje va a saltar por reestructuración, no por tests nuevos, y un trinquete lo interpretaría como mérito. Reconsiderar **después** del Plan 4 |
| **E3** | Plan 2 · T2.7 | **A) El Plan 2 cierra con el −5 % de ciudad nueva** | No se abre plan para atacar los 80 Details de una ciudad nueva: **ese gasto compra prospectos**, y recortarlo sería recortar producto. El importe en pesos se calcula aplicando la tarifa sobre los conteos ya medidos cuando el owner traiga el gate 1 |
| **E4** | Plan 1 | **A) El Plan 1 arranca en sesión nueva** | Son 10 tareas. Mensaje de arranque listo en [`2026-08-28-handoff-plan1.md`](2026-08-28-handoff-plan1.md) |

Las cinco decisiones **D1–D5** del §8 siguen abiertas y los planes siguen asumiendo su
opción A, salvo **D2** y **D4**, que quedaron resueltas por los hechos: el Plan 0 se ejecutó
primero (D4·A) y el Plan 2 cerró evaluando CE6 en llamadas (D2·A).

---


## 8. DECISIONES PENDIENTES

Cinco. Todas cerradas, ancladas a una tarea, con opción recomendada e impacto declarado.
**Mientras no haya respuesta, los planes asumen la opción A y avanzan.**

### D1 — Alcance del troceo de `app.py` · afecta: **Plan 4, Tarea T4.3 y criterio CE1**

- **A)** Extraer solo el HTML; CE1 se reescribe a *"`app.py` < 1,100 líneas **y** ningún
  archivo nuevo supera 800"*. **(recomendada)** — T4.3 ya es la tarea de mayor riesgo del
  plan: mueve 5,067 líneas de las tres pantallas operativas. Añadirle el troceo del Python
  duplica la superficie de fallo sobre el formulario que NIOVAL usa horas al día.
- **B)** Extraer el HTML **y** trocear las 1,031 líneas de Python restantes en módulos
  (`rutas_*.py`, `sheets.py`, `importador.py`), con CE1 tal como está (< 800).
- **Impacto:** si B, T4.3 se parte en T4.3a (HTML) y T4.3b (módulos), el Plan 4 pasa de 12 a
  13 tareas, su riesgo R1 sube de Media a **Alta**, y el total global pasa de 53 a 54.
- Mientras no respondas, el plan asume **A**.

### D2 — Cómo cierra el Plan 2 sin la consola de facturación · afecta: **Plan 2, Tareas T2.7 y T2.8**

- **A)** CE6 se evalúa en **reducción de llamadas**, el Plan 2 cierra y se mergea, y el
  importe en pesos se calcula después aplicando la tarifa. **(recomendada)** — los conteos
  ya están medidos y son más exactos que un recibo mensual; falta solo el multiplicador, que
  no cambia ni una línea de código.
- **B)** T2.7 queda **BLOQUEADA** hasta que el owner entregue el consumo por SKU; PR #38
  sigue en borrador.
- **Impacto:** si B, el Plan 2 no cierra, su rama sigue abierta indefinidamente y los Planes
  1, 4 y 5 rebasan sobre un `main` **sin** las optimizaciones de Places ya escritas y
  probadas. Si A, PR #38 se mergea y CE6 queda anotado como *"medido en llamadas, pendiente
  de conversión a pesos"*.
- Mientras no respondas, el plan asume **A**.

### D3 — Tamaño del catálogo de ciudades · afecta: **Plan 1, Tareas T1.4 y T1.7**

- **A)** **400-600 ciudades**: los municipios con presencia ferretera relevante según DENUE,
  cubriendo las 32 entidades. **(recomendada)** — es ~2× el catálogo actual (293 entradas),
  suficiente para cobertura nacional y manejable para el render de chips.
- **B)** **Exhaustivo**: todo municipio con ≥1 unidad económica del SCIAN ferretero (miles).
- **C)** **Conservador**: ~300, el tamaño actual pero deduplicado y con potencial real.
- **Impacto:** si B, T1.7 necesita paginación o render virtualizado **además** del filtro por
  región, y el Plan 4 · T4.9 hereda ese requisito. Si C, CE4 (*"≥1 ciudad de cada una de las
  32 entidades"*) puede no cumplirse sin forzar la lista.
- **RESUELTA POR LOS DATOS (2026-08-29).** Se ejecutó **A**, y el corte dejó de ser una
  estimación: DENUE da **589 municipios con ≥20 ferreterías** y **443 con ≥30**. El catálogo
  final tiene **606** porque además conserva las plazas del array viejo que no llegan al
  corte —quitarle al operador una ciudad que ya podía elegir es irreversible para él— y
  rescata las entidades que se quedarían sin ninguna. Seis por encima del rango, y se dice.

### D4 — Dónde entra el Plan 0 (CI) · afecta: **Índice §2 y Plan 0 completo**

- **A)** **Primero**, antes de cerrar el Plan 2. **(recomendada)** — son 4 tareas que no
  tocan `app.py`; a partir de ahí los PR de los planes 2, 1, 4 y 5 llevan check automático,
  incluido el PR #38 que sigue en borrador.
- **B)** **Después del Plan 2**, para no interrumpir una rama en vuelo.
- **C)** **No se ejecuta**: el gate sigue siendo manual.
- **Impacto:** si A, el orden es 0 → 2 → 1 → 4 → 5, con ~1 sesión de desvío antes de cerrar
  el Plan 2. Si C, el Plan 0 sale del marcador global y el total vuelve de 53 a **49** tareas.
- Mientras no respondas, el índice asume **A**.

### D5 — Rate limiting en memoria o con Redis · afecta: **Plan 5, Tarea T5.1**

- **A)** **En memoria del proceso.** **(recomendada)** — gunicorn corre `--workers 1
  --threads 4`, así que un contador en memoria es exacto; Redis añadiría una dependencia de
  infraestructura al VPS para resolver un problema que hoy no existe.
- **B)** **Redis**, para que el límite sobreviva a un reinicio y a un futuro `--workers 2`.
- **Impacto:** si B, T5.1 gana una dependencia de despliegue (contenedor Redis en
  `despliegue/docker-compose.yml`) y el Plan 5 pasa de 8 a 9 tareas. Si A, subir a
  `--workers 2` en el futuro invalidaría el límite en silencio, y eso queda anotado en
  `docs/adr/2026-08-27-estado-compartido-importador.md` como consecuencia del `--workers 1`.
- Mientras no respondas, el plan asume **A**.
