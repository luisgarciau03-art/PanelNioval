# ÍNDICE — TANDA DE PLANES DEL 2026-08-27 (PanelNioval)

**Fecha de diseño:** 2026-08-27
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Biblioteca de herramientas leída:** `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` —
**653 herramientas (229 agentes + 424 skills)** de **6 fuentes**: catalogo-agentes, ECC,
claude-ads, community, claude-mem y superpowers, más el built-in de Claude Code.
**Toolkit del proyecto:** no existe (`.claude/` está vacío; no hay `.claude/toolkit-*.md`).
**Baseline verificado en disco el 2026-08-27:** `python -m pytest tests/ -q` → **230 passed**,
exit 0. Coincide con lo declarado en `CLAUDE.md`.

---

## 1. LOS CUATRO PLANES

| Plan | Documento | Tareas | Qué resuelve |
|---|---|---|---|
| **1** | [`2026-08-27-plan1-relevancia-ciudades-nacional.md`](2026-08-27-plan1-relevancia-ciudades-nacional.md) | 10 | El orden de ciudades del importador mide el historial de NIOVAL, no la relevancia del ramo ferretero en México. Catálogo canónico por macro-región. |
| **2** | [`2026-08-27-plan2-optimizacion-gasto-places.md`](2026-08-27-plan2-optimizacion-gasto-places.md) | 9 | Google Places se paga de más: Details sin `fields`, pagados antes de deduplicar, sin caché y sin medidor. |
| **3** | [`2026-08-27-plan3-bug-conteo-y-pantallas-carga.md`](2026-08-27-plan3-bug-conteo-y-pantallas-carga.md) | 10 | "Dice 20 y aparecen 10" + pantallas de carga rotas. **Nueve defectos** con causa raíz identificada. |
| **4** | [`2026-08-27-plan4-rediseno-profesional-panel.md`](2026-08-27-plan4-rediseno-profesional-panel.md) | 12 | Rediseño profesional de las 3 superficies: movimiento, presentación y estados de carga. |

**Total: 41 tareas.**

---

## 2. ORDEN DE EJECUCIÓN Y DEPENDENCIAS

**El orden de ejecución NO es el de numeración.** Es **3 → 2 → 1 → 4**, y hay razones
técnicas para cada paso.

```
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 3 — BUG DE CONTEO Y PANTALLAS DE CARGA          10 tareas     │
│ 9 defectos. Causa raíz de las pantallas: _import_job es global de  │
│ proceso y gunicorn corre --workers 2 → la mitad de los sondeos     │
│ interroga a un worker que no sabe nada del trabajo.                │
│ BLOQUEANTE: mientras esto siga, ningún trabajo de UI es verificable│
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: dedup por corrida (T3.3),
                                  progreso con denominador ajustable (T3.6)
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 2 — OPTIMIZACIÓN DEL GASTO DE PLACES             9 tareas     │
│ Reutiliza el set de place_id del Plan 3 para no pagar Details de   │
│ duplicados. Corta variaciones sobre el progreso ya ajustable.      │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: medidor de costo por corrida
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 1 — RELEVANCIA DE CIUDADES A NIVEL NACIONAL     10 tareas     │
│ Independiente en backend, pero su UI aterriza en el importador.    │
│ Va después de 3 para no construir sobre estado roto; antes de 4    │
│ para que el rediseño sepa cuántos chips tiene que acomodar.        │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼  entrega: cientos de ciudades + filtro por región
┌────────────────────────────────────────────────────────────────────┐
│ PLAN 4 — REDISEÑO PROFESIONAL DEL PANEL              12 tareas     │
│ Va al final: consume los 4 contadores del Plan 3, el medidor del   │
│ Plan 2 y el filtro por región del Plan 1. Rediseñar antes sería    │
│ rediseñar sobre un blanco móvil.                                   │
└────────────────────────────────────────────────────────────────────┘
```

### 2.1 Dependencias explícitas entre planes

| Origen | Destino | Qué se traspasa | Instrucción al ejecutor |
|---|---|---|---|
| Plan 3 · T3.3 | Plan 2 · T2.3 | Set de `place_id` a nivel corrida | **Reutilizar**, no crear una segunda estructura |
| Plan 3 · T3.6 | Plan 2 · T2.4 | Denominador de progreso ajustable | T3.6 lo implementa ajustable desde el principio para que T2.4 no lo rehaga |
| Plan 3 · T3.7 | Plan 1 · T1.7 | Escapado del nombre de ciudad (defecto B9) | Quien llegue primero lo arregla; el otro **verifica y no duplica** |
| Plan 3 · T3.2 | Plan 4 · T4.9 | Los 4 contadores separados | El rediseño les da jerarquía; `nuevos_en_sheet` es el número grande |
| Plan 2 · T2.6 | Plan 4 · T4.9 | Medidor de costo y estado `presupuesto_agotado` | Se presenta como estado de primera clase, no como error |
| Plan 1 · T1.7 | Plan 4 · T4.9 | Filtro por macro-región | El rediseño le da forma; no rehace la lógica |
| Plan 4 · T4.3 | — | Extracción del HTML de `app.py` | **Bloquea** T4.4–T4.9; commit aislado |

### 2.2 Riesgo de solapamiento

Los cuatro planes tocan `/importador`. Ejecutarlos en paralelo garantiza conflictos de
merge sobre las mismas líneas de `app.py`. **Se ejecutan en secuencia**, una rama por plan,
rebasando sobre `main` ya actualizado con el plan anterior.

---

## 3. RESUMEN DE ASIGNACIÓN DE HERRAMIENTAS POR FUENTE

Auditoría de diversidad de un vistazo. ✅ = la fuente se usa con herramientas asignadas a
tareas concretas; ⚠️ = evaluada y descartada con justificación por escrito.

| Fuente | Plan 1 | Plan 2 | Plan 3 | Plan 4 |
|---|---|---|---|---|
| **catalogo-agentes** (229 agentes) | ✅ 12 | ✅ 8 | ✅ 10 | ✅ 12 |
| **ECC** (~200 skills) | ✅ 9 | ✅ 9 | ✅ 9 | ✅ 10 |
| **community** (~41 skills, incl. blueprint) | ✅ 2 | ✅ 4 | ✅ 3 | ✅ 5 |
| **claude-mem** (~18 skills) | ✅ 3 | ✅ 1 | ✅ 2 | ✅ 2 |
| **superpowers** (14 skills) | ✅ 4 | ✅ 3 | ✅ 3 | ✅ 3 |
| **claude-ads** (~60 herramientas) | ✅ 1 (opcional) | ✅ 1 | ⚠️ N/A justificado | ✅ 1 |
| **built-in** (Explore, dataviz…) | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 2 |
| **Fuentes canónicas usadas** | **6/6** | **6/6** | **5/6** | **6/6** |

### 3.1 Herramientas más usadas, por fuente

- **catalogo-agentes** — `code-reviewer`, `python-reviewer`, `security-reviewer`,
  `silent-failure-hunter`, `tdd-guide`, `python-pro`, `debugger`, `performance-optimizer`,
  `refactoring-specialist`, `ui-designer`, `ux-researcher`, `a11y-architect`,
  `accessibility-tester`, `market-researcher`, `data-researcher`, `api-designer`,
  `code-architect`, `pr-test-analyzer`, `doc-updater`, `technical-writer`.
- **ECC** — `python-testing`, `verification-loop`, `github-ops`, `backend-patterns`,
  `frontend-patterns`, `architecture-decision-records`, `benchmark`,
  `benchmark-optimization-loop`, `content-hash-cache-pattern`, `documentation-lookup`,
  `orch-fix-defect`, `orch-refine-code`, `design-system`, `motion-ui`, `ui-ux-pro-max`,
  `accessibility`, `browser-qa`, `docker-patterns`, `deployment-patterns`, `error-handling`,
  `market-research`, `deep-research`.
- **community** — `blueprint` (los 4 planes), `council` (3 decisiones con tradeoff real),
  `click-path-audit`, `frontend-design-direction`, `impeccable`,
  `make-interfaces-feel-better`, `frontend-a11y`, `production-audit`, `cost-tracking`.
- **claude-mem** — `mem-search` (los 4 planes, etapa A), `timeline-report`, `babysit`,
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
Los cuatro planes cumplen el mínimo sin ellas.

Hay además **dos entradas con fuente discrepante entre niveles**: `council` e `impeccable`
figuran como `community` en la Matriz Nivel 1 y como `ECC` / `skills-local` en el Catálogo
Nivel 2. Se cita la atribución del **Nivel 1**, que es la matriz que las reglas mandan usar
primero. Se deja constancia para que la auditoría no lo lea como error.

---

## 4. MEJORAS PROPUESTAS (no pedidas)

Detectadas al leer el código para diseñar los cuatro planes. Ninguna estaba en el encargo.
Clasificadas por impacto y esfuerzo.

### 4.1 Alto impacto · Bajo esfuerzo

| # | Mejora | Evidencia | Dónde encaja |
|---|---|---|---|
| **M1** | **No hay CI.** No existe `.github/`. Los 230 tests son el único gate del proyecto y **solo corren si alguien se acuerda de correrlos a mano**. Un workflow que ejecute `pytest` en cada PR convierte "nada se mergea en rojo" de intención en mecanismo. | `ls -d .github` → no existe | **Plan nuevo, corto (3 tareas).** Debería ir **antes** que los cuatro, porque protege a los cuatro |
| **M2** | **Zona horaria del contenedor.** El `Dockerfile` no fija `TZ` (`python:3.11-slim` corre en UTC) y `datetime.now()` se usa en **6 sitios que escriben a Sheets** (`app.py:3029`, `3138`, `3457`, `3530`, `4434`, `4435`). México es UTC-6: todo lo capturado después de las 18:00 hora local se guarda con **la fecha del día siguiente**, y `isocalendar()[1]` puede caer en la semana equivocada. La gráfica "Contactos por Semana" del dashboard agrupa justamente por ese campo. | 6 llamadas a `datetime.now()` sin `tzinfo`; `Dockerfile` sin `ENV TZ` | **Plan 3** como tarea T3.10, o plan propio de 1 tarea. Es un bug de datos, no cosmético |
| **M3** | **El hilo del importador es `daemon=True`** (`app.py:4574`). Al reiniciar el contenedor, el hilo muere a mitad de corrida sin dejar rastro: filas a medias en la hoja y estado colgado. | `threading.Thread(..., daemon=True)` | **Plan 3**, junto a T3.5 (estado compartido), que es donde se detecta un trabajo huérfano |
| **M4** | **Telegram solo avisa en el camino feliz** (`app.py:4533`). Si la corrida falla, el owner no se entera por ningún canal. | `_enviar_telegram_importador` solo se llama tras el bucle exitoso | **Plan 3 · T3.4**, ya incluido ahí |

### 4.2 Alto impacto · Esfuerzo medio

| # | Mejora | Evidencia | Dónde encaja |
|---|---|---|---|
| **M5** | **Cero rate limiting.** Ninguna ruta lo tiene (0 coincidencias de `limiter`/`Limiter` en `app.py`). Las reglas globales de seguridad del entorno lo exigen en todos los endpoints. El panel está publicado en internet tras un token; un token filtrado da barra libre, incluida la capacidad de disparar corridas de Places que cuestan dinero. | `grep -c "limiter\|Limiter" app.py` → 0 | **Plan nuevo de seguridad**, junto con M6. Se relaciona con el tope de presupuesto del **Plan 2 · T2.6** |
| **M6** | **La exposición de Railway sigue viva.** `CLAUDE.md` ya lo registra: `https://web-production-1d453.up.railway.app/` corre **sin `PANEL_DASHBOARD_TOKEN`**. El gate es fail-closed en el código, pero ese despliegue no tiene la variable definida. Es un gate del owner desde el 2026-08-17. | Registrado en `CLAUDE.md` §Pendientes y en la memoria del proyecto | **Gate del owner.** No lo resuelve ningún plan de esta tanda: hace falta la decisión de apagar Railway |
| **M7** | **Rotar el token de Telegram.** `CLAUDE.md` lo registra como pendiente: expuesto en el historial de git, ~14 copias. Quitarlo del código no lo rota; sigue vivo en el proveedor. | Registrado en `CLAUDE.md` §Secretos | **Gate del owner.** Acción de 2 minutos en BotFather que cierra el riesgo de verdad |
| **M8** | **Un solo trabajo de importación a la vez, global** (`app.py:4564-4566`). Dos operadores no pueden importar dos ciudades en paralelo; el segundo recibe "Ya hay una búsqueda en curso" sin saber quién la lanzó ni cuándo. | `if _import_job['status'] == 'running': return error` | **Plan 3 · T3.5** deja la puerta abierta: con estado compartido, pasar a una cola de trabajos es incremental |

### 4.3 Impacto medio

| # | Mejora | Evidencia | Dónde encaja |
|---|---|---|---|
| **M9** | **No hay healthcheck** en `Dockerfile` ni en `despliegue/docker-compose.yml`. Un panel que arranca pero no responde se ve igual que uno sano. | `Dockerfile` sin `HEALTHCHECK` | Plan nuevo de operación, o al desplegar el Plan 3 |
| **M10** | **La corrida del importador es estrictamente serial**: `time.sleep(0.3)` por cada Place Details (`app.py:4388`) y `time.sleep(2)` por página (`app.py:4345`). Una ciudad grande tarda minutos. Tras el Plan 2 habrá menos llamadas; paralelizar con cuidado de cuota podría reducir más el tiempo. | Dos `sleep` fijos en el bucle | **Plan 2**, como continuación de T2.4, solo si tras medir el tiempo sigue siendo el problema |
| **M11** | **Archivos de otro proyecto en `docs/`.** Ocho archivos sin versionar de la tanda `2026-08-15-*` (migración del entorno Claude) están en `docs/superpowers/plans/` de este repo. El índice de esa tanda dice que su copia canónica vive en `C:\Users\PC 1\migracion-claude-code` y que estas son de solo lectura. También hay un `Nuevo documento de texto.txt` vacío en la raíz. | `git status` al inicio de la sesión | Limpieza de cruft. **Regla 4 del entorno: nada se borra, se aparta** al respaldo fechado |
| **M12** | **`app.py` viola el límite de 800 líneas** con 4,948. Registrado como M2 en `CLAUDE.md`. | `wc -l app.py` → 4948 | **Plan 4 · T4.3** lo resuelve parcialmente: saca ~3,000 líneas de HTML. Lo que quede (rutas, Sheets, importador) merece su propio troceo |

### 4.4 Deuda técnica menor

| # | Mejora | Dónde encaja |
|---|---|---|
| **M13** | El escape de HTML existe en el dashboard (`app.py:2064`) y falta en el importador. **Plan 4 · T4.3** lo centraliza en `js/comun.js`, cerrando la brecha de raíz. | Plan 4 |
| **M14** | `_escapar_formula` (`app.py:4403`) protege las escrituras del importador contra inyección de fórmulas de Sheets. Convendría auditar si las **otras** rutas que escriben a Sheets (`/api/seguimiento/update`, `/api/mensajes/update`, el formulario) tienen la misma protección. | Plan nuevo de seguridad, junto con M5 |
| **M15** | El logo se carga desde Cloudinary sin `width`/`height` (`app.py:4655`) → salto de layout. | **Plan 4 · T4.10**, ya incluido |

### 4.5 Recomendación de secuencia con las mejoras dentro

```
PLAN 0 (nuevo, 3 tareas)  CI con pytest en cada PR                 ← M1
        ▼
PLAN 3   Bug de conteo y pantallas de carga  (+ M2, M3, M4)
        ▼
PLAN 2   Optimización del gasto de Places    (+ M10 si aplica)
        ▼
PLAN 1   Relevancia de ciudades nacional
        ▼
PLAN 4   Rediseño profesional                (+ M12 parcial, M13, M15)
        ▼
PLAN 5 (nuevo, opcional)  Seguridad: rate limiting + auditoría de escrituras  ← M5, M14

GATES DEL OWNER, en paralelo y sin depender de nada:  M6 (Railway), M7 (rotar Telegram)
```

**M1 (CI) es la única mejora que se recomienda hacer antes que todo lo demás**, porque
convierte el gate de "nada se mergea en rojo" en algo que la máquina hace sola, y los cuatro
planes lo invocan 41 veces.

---

## 5. AUTOEVALUACIÓN (PASO 4)

Respondida antes de entregar, con el documento delante.

**¿Cuántas fuentes distintas usa cada plan?**

| Plan | Fuentes canónicas | Detalle |
|---|---|---|
| Plan 1 | **6 de 6** | catalogo-agentes, ECC, community, claude-mem, superpowers, claude-ads (opcional, justificado) |
| Plan 2 | **6 de 6** | las mismas, con claude-ads en uso obligatorio (`ads-math`) |
| Plan 3 | **5 de 6** | claude-ads evaluada y descartada con constancia por escrito en su §7 |
| Plan 4 | **6 de 6** | claude-ads en uso literal (`ads-dna`) |

Los cuatro superan el mínimo de 5 fuentes. El único descarte, en el Plan 3, está justificado
herramienta por herramienta y no con un "no aplica" genérico.

**¿Aparecen ECC, claude-mem, catalogo-agentes y community además de superpowers?**
Sí, **en los cuatro planes**. Superpowers aporta 3-4 herramientas por plan (sus skills de
proceso: TDD, depuración sistemática, brainstorming, verificación) y **nunca sustituye** al
especialista de la otra fuente: `superpowers:test-driven-development` va siempre acompañada
de `tdd-guide` (catalogo-agentes) y `python-testing` (ECC), tal como pide la regla 4 de la
biblioteca. `blueprint` (community) es el formato de los cuatro planes; `mem-search`
(claude-mem) abre la etapa A de los cuatro.

**¿Toda tarea tiene etapa D (verificación)?**
Toda tarea de implementación, sí — 27 de 41. Las 14 restantes son de investigación (etapa A),
diseño (etapa B), tarea cero o cierre, y **no producen código que verificar**; cada una tiene
en su lugar un criterio de cierre explícito y comprobable (documento con N fuentes citadas,
ADR con las alternativas descartadas, respaldo listado en disco con tamaño > 0). Ninguna
tarea que toca código carece de gate. Cada plan tiene además una tarea de verificación
integral dedicada (T1.8, T2.7, T3.8, T4.10) antes de su cierre.

**¿Toda tabla PROGRESO está pre-poblada?**
Sí. Las cuatro tienen una fila por tarea, con estado `PENDIENTE`, columnas de evidencia y
fecha vacías, y el marcador de avance del plan al pie. El marcador global está en §6.

**¿Se corrigió algo antes de entregar?**
Sí, tres cosas. (1) El orden de ejecución inicial era 1→2→3→4 por numeración; al encontrar
que `_import_job` es global de proceso con `--workers 2`, se cambió a **3→2→1→4** y se
documentó la razón. (2) Se detectó solapamiento real entre el dedup del Plan 3 y el del
Plan 2, y entre el escapado del Plan 3 y el del Plan 1: ambos quedan marcados con la
instrucción de reutilizar y no duplicar. (3) Se añadió la nota de §3.2 al descubrir que el
Nivel 2 de la biblioteca usa una etiqueta de fuente (`skills-local`) que no está en la tabla
de Fuentes, en vez de mapearla por conveniencia a una de las 6.

---

## 6. MARCADOR DE PROGRESO GLOBAL

| Plan | Tareas | Estado | Avance |
|---|---|---|---|
| Plan 3 — Bug de conteo y pantallas de carga | 10 | **COMPLETADO** | **10 / 10** |
| Plan 2 — Optimización del gasto de Places | 9 | EN CURSO | 6 / 9 |
| Plan 1 — Relevancia de ciudades nacional | 10 | PENDIENTE | 0 / 10 |
| Plan 4 — Rediseño profesional del panel | 12 | PENDIENTE | 0 / 12 |

**PROGRESO GLOBAL DEL PROYECTO: 16 / 41 tareas (39 %) · 1 de 4 planes completados**

> El ejecutor actualiza esta tabla al cerrar cada tarea, y la tabla PROGRESO del documento
> del plan correspondiente, con evidencia (commit / test / PR) y fecha.

---

## 7. REGLAS QUE APLICAN A LOS CUATRO PLANES

Salen de `CLAUDE.md` del proyecto y de las reglas globales del entorno. No son opcionales.

1. **Nunca trabajar en `main`.** Railway y Vultr despliegan desde ahí. Una rama por plan.
2. **Baseline oficial:** `python -m pytest tests/ -q` → **230 passed** (verificado el
   2026-08-27). Nada se mergea con la suite en rojo.
3. **Respaldo antes del cambio, no después.** `python tools/respaldar_hojas.py`, y se
   confirma que el archivo existe antes de seguir.
4. **Nada se borra: se aparta** al respaldo fechado. Vale para archivos, configuración y
   cruft.
5. **Datos personales:** teléfonos, nombres y correos de clientes no se commitean ni se
   vuelcan completos en logs. Enmascarar `+52…XXXX`.
6. **Credenciales:** nunca por valor. Se identifican por nombre de variable y `archivo:línea`,
   o por prefijo+sufijo enmascarado.
7. **Commits convencionales en español:** `fix:`, `feat:`, `test:`, `docs:`, `chore:`,
   `refactor:`.
8. **Un barrido que no encuentra nada no demuestra que no hay nada.** Verificar en las dos
   direcciones: que encuentra un positivo conocido **y** que no marca un negativo conocido.
9. **Una operación que no encuentra nada tampoco se queja.** Un reemplazo por patrón que no
   casa devuelve el texto igual sin error. Verificar que el cambio está **en el archivo**, no
   que la herramienta dijo "aplicado".
10. **Los scripts de análisis no llaman a APIs de pago.** En este proyecto la única API
    facturable es Google Places; su gasto se mide y se acota en el Plan 2.
