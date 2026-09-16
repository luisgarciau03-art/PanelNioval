# ÍNDICE DE LA TANDA — PanelNioval · 2026-09-15

**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie afectada:** `https://panelnioval.duckdns.org` (`/`, `/formulario`, `/importador`)

**SESIÓN ACTUAL: 2** · **ÚLTIMO RELEVO: 2026-09-16, tras T1.7 ([`RELEVO-actual.md`](RELEVO-actual.md), apuntando a Plan 4 · T4.0)**

**PROGRESO GLOBAL: 1 / 4 planes completados (25 %) · 11 / 34 tareas (32.4 %)** · **Plan 4 en curso (3/12)**

> ✅ **Plan 1 CERRADO y EN PRODUCCIÓN** (2026-09-16). PR #42 mergeado (`main` `8bac782`) y desplegado a mano en el VPS. El operador ve **1,004 ciudades** donde había 606.
>
> ⚠️ **HALLAZGO QUE AFECTA A LOS OTROS TRES PLANES:** el invariante «el VPS auto-deploya `main`» **es FALSO** desde el 2026-08-19. No hay auto-deploy: el despliegue es un `ssh` manual. **«Mergeado» y «desplegado» son dos estados distintos**, y los Planes 2, 3 y 4 llevan el invariante falso escrito. Cada uno necesita su paso de despliegue explícito. Detalle: `docs/auditoria/2026-09-15-verificacion-produccion-plan1.md`.
**Plan 1: CERRADO (8/8). En curso: Plan 4 (T4.0-T4.2 hechas, dirección visual APROBADA) · Siguiente: T4.3 · Baseline vigente sobre `main`: 525 passed, 1 skipped** (el 626 sigue siendo de `fix/endurecimiento-panel`/PR #44 y vuelve a aplicar cuando aterrice en el Plan 4, T4.6 — ⚠️ ese PR pasó a **CONFLICTING** contra `main` tras el merge del #42)

**Biblioteca de herramientas leída en la sesión de diseño:**
`C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — **653 herramientas (229 agentes + 424
skills)** de **6 fuentes**: `catalogo-agentes`, `ECC`, `claude-ads`, `community`, `claude-mem`
y `superpowers`, más el built-in de Claude Code.
**Toolkit del proyecto:** no existe `.claude/toolkit-*.md` en PanelNioval. Sí existe el de
BruceWhatsapp (`.claude/toolkit-bruce.md`), que **no aplica** a este repo.

---

## 0. LO PRIMERO: DÓNDE VIVE ESTE TRABAJO

El encargo llegó con `RUTA DEL PROYECTO: C:\Users\PC 1\BruceWhatsapp`. **El `/importador` no
está ahí.** Se verificó en disco:

| Comprobación | Resultado |
|---|---|
| `grep -ril importador` en BruceWhatsapp | 8 archivos, **ninguno** es el importador de prospectos |
| `grep -ril importador` en PanelNioval | **44 archivos**, incluidos `app.py`, 5 suites de test y 4 planes previos |
| `panelnioval.duckdns.org` | Es el VPS de **PanelNioval** (RUNBOOK: *«El VPS auto-deploya `main`»*) |

Por eso los cuatro planes y este índice viven en **`C:\Users\PC 1\PanelNioval\docs\superpowers\plans\`**.
El ejecutor debe abrir **PanelNioval**, no BruceWhatsapp. (La única excepción posible es el
Plan 2 si se elige la opción B de la decisión **D2**.)

---

## 1. EL HALLAZGO QUE CAMBIA EL DISEÑO

Dos de los cuatro planes que pediste **ya están construidos, probados y esperando merge**. No
se ven en el panel porque el VPS despliega `main` y esos PR nunca se mergearon.

| PR | Contenido | Estado | Antigüedad |
|---|---|---|---|
| **#42** | **Plan 1** — relevancia de ciudades a nivel nacional. **1,004** municipios con datos DENUE 05_2026 + Censo 2020, modelo exógeno con ADR | ✅ **MERGEADO** (`main` `8bac782`) **y desplegado** | 2026-09-16 |
| **#43** | **Plan 4** — rediseño profesional de las 3 superficies, 12/12 tareas, 12 documentos de diseño con capturas a 320/768/1440. Saca el HTML de `app.py` a `templates/`+`static/` | **OPEN · MERGEABLE** · **apilado sobre #42** | desde 2026-08-31 |
| **#44** | Plan 5 — endurecimiento: rate limiting, escape de fórmulas, zona horaria, healthcheck, cierre ante `SIGTERM` | **OPEN** · **5 conflictos con #43** | desde 2026-09-05 |

Y el bug que reportas (*«dice 20 y aparecen 10»*) **ya se cerró** en el PR #36 (`ae0e1c9`),
con 9 defectos confirmados por experimento y 4 más hallados de paso. Que lo sigas viendo es
un dato de diagnóstico, no un encargo de rediseño.

**Consecuencia para el diseño:** estos cuatro planes **no construyen desde cero**. Verifican
lo construido, cierran la brecha contra lo que pediste, lo aterrizan en producción y
diagnostican el bug reincidente antes de tocarlo. Si prefieres lo contrario, está en la
decisión **D1**.

---

## 2. LOS CUATRO PLANES

La numeración es la tuya. **El orden de ejecución no lo es** (§3).

| Plan | Documento | Tareas | Qué resuelve | Punto de partida |
|---|---|---|---|---|
| **1** | [`…plan1-relevancia-ciudades-nacional-produccion.md`](2026-09-15-plan1-relevancia-ciudades-nacional-produccion.md) | 8 | El orden de ciudades mide el historial de NIOVAL, no la relevancia del ramo en México. Verifica la cobertura por región y lo pone en producción | PR #42 construido |
| **2** | [`…plan2-gasto-api-minimo.md`](2026-09-15-plan2-gasto-api-minimo.md) | 8 | Cada negocio **sin teléfono cuesta un Place Details** y nunca llega a la hoja. Mide la fuga, la cierra y pone tope duro | PR #38 mergeado; fuga sin medir |
| **3** | [`…plan3-bug-conteo-y-pantallas-carga.md`](2026-09-15-plan3-bug-conteo-y-pantallas-carga.md) | 9 | «Dice 20 y aparecen 10» + pantallas de carga. **Reincidencia:** diagnóstico diferencial antes de cualquier fix | PR #36 mergeado; síntoma vivo |
| **4** | [`…plan4-rediseno-profesional-aterrizaje.md`](2026-09-15-plan4-rediseno-profesional-aterrizaje.md) | 9 | Movimientos, display y estados de carga en las 3 superficies. Cierra la brecha, aterriza #43 y desatora #44 | PR #43 construido |

**Total: 34 tareas.**

---

## 3. ORDEN DE EJECUCIÓN Y DEPENDENCIAS

### El orden es **1 → 4 → 3 → 2**, y no es una preferencia: es dependencia medida.

```
┌──────────────────────────────────────────────────────────────────────┐
│ PLAN 1 — RELEVANCIA NACIONAL EN PRODUCCIÓN            8 tareas       │
│ Aterriza PR #42. Va primero porque **#43 está apilado sobre #42**:   │
│ cualquier otro orden descuelga el rediseño.                          │
│ Añade lo que faltaba: cobertura verificada de TODAS las ciudades     │
│ por región (T1.2/T1.3) y despliegue real (T1.6).                     │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼  entrega: #42 en main · catálogo en producción
┌──────────────────────────────────────────────────────────────────────┐
│ PLAN 4 — REDISEÑO PROFESIONAL ATERRIZADO              9 tareas       │
│ Aterriza PR #43 (saca 3,240 líneas de HTML de app.py) y **rebasa     │
│ PR #44**, resolviendo sus 5 conflictos. Va segundo porque define     │
│ la estructura de archivos que los planes 3 y 2 van a editar.         │
│ Gate humano en T4.2: tu aprobación de la dirección visual.           │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼  entrega: templates/ + static/ · los 3 PR cerrados
┌──────────────────────────────────────────────────────────────────────┐
│ PLAN 3 — BUG DE CONTEO (REINCIDENCIA)                 9 tareas       │
│ Va tercero **a propósito**: el front-end ya vive en                  │
│ static/js/importador.js, así que el fix se escribe UNA vez.          │
│ Arreglarlo antes significaría arreglarlo dos veces y perder una      │
│ en el conflicto. Ninguna línea de código antes del diagnóstico.      │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼  entrega: el número de la UI == filas de la hoja
┌──────────────────────────────────────────────────────────────────────┐
│ PLAN 2 — GASTO DE LA API AL MÍNIMO                    8 tareas       │
│ Va último porque necesita el código asentado para medir: los planes  │
│ 1, 4 y 3 mueven la ruta de Places y el medidor. Medir antes sería    │
│ medir un blanco móvil. Además, el catálogo ampliado del Plan 1       │
│ multiplica las corridas posibles: ahí el tope deja de ser adorno.    │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.1 Dependencias explícitas entre planes

| Origen | Destino | Qué se traspasa | Instrucción al ejecutor |
|---|---|---|---|
| Plan 1 · T1.5 | Plan 4 · T4.0 | PR #42 en `main` | T1.5 **obliga** a verificar que #43 sigue `MERGEABLE` inmediatamente después del merge |
| Plan 1 · T1.3 | Plan 2 · T2.5 | Catálogo de ciudades ampliado | Más ciudades = más corridas posibles. El tope por defecto se revisa contra el catálogo **real** |
| Plan 4 · T4.4 | Plan 3 · T3.4 | `static/js/importador.js` y `templates/importador.html` | El fix del conteo va **ahí**, nunca en `app.py`. Escribirlo en `app.py` es trabajo que se pierde |
| Plan 4 · T4.6 | Plan 2 · T2.4 | PR #44 aterrizado (rate limiting, escape, `SIGTERM`) | T2.4 **reutiliza** el camino de salida limpia de `presupuesto_agotado`; no crea un segundo |
| Plan 4 · T4.4 | Plan 2 · T2.5 | Los 4 contadores del medidor, ya en `static/js/importador.js` | CE5 del Plan 2 verifica que siguen leyendo los campos del backend |
| Plan 3 · T3.5 | Plan 2 · T2.5 | Los 6 estados del importador auditados | El estado `presupuesto_agotado` es uno de los seis; T2.5 no lo re-audita |
| Plan 3 · T3.2 | Plan 2 · T2.1 | Comportamiento de `saltados` / `ya_en_hoja` | El PR #38 introdujo ese contador; los dos planes miran la misma ruta desde ángulos distintos |

### 3.2 Riesgo de solapamiento

Los cuatro planes tocan `/importador` o su worker. **Se ejecutan en secuencia, una rama por
plan, rebasando sobre `main` ya actualizado.** Ejecutarlos en paralelo garantiza conflictos
sobre las mismas líneas — y este proyecto ya tiene tres PR abiertos peleándose por `app.py`,
que es precisamente el problema que la tanda viene a cerrar.

---

## 4. RESUMEN DE ASIGNACIÓN DE HERRAMIENTAS POR FUENTE

Auditoría de diversidad de un vistazo. ✅ = la fuente se usa con herramientas asignadas a
tareas concretas · ⚠️ = evaluada y descartada **por escrito**.

| Fuente | Plan 1 | Plan 2 | Plan 3 | Plan 4 |
|---|---|---|---|---|
| **catalogo-agentes** (229 agentes) | ✅ 9 | ✅ 10 | ✅ 11 | ✅ 12 |
| **ECC** (~200 skills) | ✅ 6 | ✅ 9 | ✅ 6 | ✅ 8 |
| **community** (~41 skills, incl. `blueprint`) | ✅ 3 | ✅ 3 | ✅ 4 | ✅ 6 |
| **claude-mem** (~18 skills) | ✅ 2 | ✅ 1 | ✅ 2 | ✅ 2 |
| **superpowers** (14 skills) | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 2 |
| **claude-ads** (~60 herramientas) | ✅ 1 (`ads-math`, opcional) | ✅ 1 (`ads-math`, **obligatoria**) | ⚠️ **descartada, con motivo** | ✅ 1 (`ads-dna`, uso literal) |
| **built-in** (`Explore`, `dataviz`) | ✅ 1 | ✅ 1 | ✅ 1 | ✅ 2 |
| **Fuentes canónicas usadas** | **6/6** | **6/6** | **5/6** | **6/6** |

Los cuatro planes superan el mínimo de 5. **El conjunto toca las 6.**

### 4.1 El único descarte, y por qué no es «no lo consideré»

**`claude-ads` en el Plan 3.** Se recorrió la suite completa —`ads-audit`, `ads-math`,
`ads-landing`, `ads-creative`, y los agentes `audit-*`—. El Plan 3 es un diagnóstico de un
contador que no cuadra y de estados de UI que mienten: no hay campaña, ni conversión, ni
gasto publicitario. `ads-math` es la única con encaje plausible —calcula CPA, ROAS y
break-even—, pero opera sobre gasto de anuncios, que aquí no existe; su uso útil está
asignado en el **Plan 2**, donde sí hay dinero que traducir a costo por prospecto.

### 4.2 Reviewers y build-resolver del stack

El stack es **Python/Flask + JavaScript sin framework + Google Sheets/Places**.

| Necesidad | Asignado | Nota |
|---|---|---|
| Reviewer del backend | **`python-reviewer`** | En los 4 planes, **además** de `code-reviewer`, nunca en su lugar |
| Reviewer del front | **`typescript-reviewer`** | Su descripción cubre JavaScript explícitamente. Tras el PR #43 hay 6 archivos JS en `static/js/`. Asignado en los planes 2, 3 y 4 |
| Reviewer de seguridad | `security-reviewer` | Obligatorio donde se toca Places, Sheets, escape de HTML o el token del panel |
| **Build-resolver del stack** | **`django-build-resolver` [OPCIONAL]** | **No existe build-resolver de Flask** entre las 653. El catálogo tiene los de TypeScript, Go, Rust, Java, Kotlin, Swift, C++, React, Dart, PyTorch y Django. Se asigna el de Django —marcado opcional, con condición de uso— porque es **el único especializado en errores de pip e importación de Python**; su parte de Django no se ejercita. Se prefiere al genérico `build-error-resolver`, que es de otro lenguaje. Esta línea es la constancia de que se evaluó |

### 4.3 Nota de honestidad: la etiqueta `skills-local`

El Nivel 2 de la biblioteca usa una etiqueta más fina que las 6 fuentes del encabezado:
`skills-local`, que **no es una de las 6 canónicas**. Aparece en herramientas que estos planes
sí usan (`webapp-testing`, `handoff`, `web-perf`, `review-animations`,
`web-design-guidelines`, `ui-ux-pro-max`, `motion-foundations`, `resolving-merge-conflicts`).
Mapearlas a una de las 6 sería inventar el dato: **se reportan tal cual y no cuentan** para el
mínimo de diversidad. Los cuatro planes cumplen el mínimo sin ellas.

`council` e `impeccable` figuran como `community` en la Matriz Nivel 1 y como `ECC` /
`skills-local` en el Catálogo Nivel 2. Se cita la atribución del **Nivel 1**, que es la matriz
que las reglas mandan recorrer primero.

---

## 5. BASELINE Y GATES COMUNES

**Baseline oficial, medido en disco el 2026-09-15** (rama `fix/endurecimiento-panel`, 117 s):

```
cd "C:\Users\PC 1\PanelNioval"
python -m pytest tests/        →  626 passed, 1 skipped
```

⚠️ **Sin `-q`.** `pytest.ini` ya trae `addopts = -q`; añadir otro lo convierte en `-qq`, que
**suprime la línea del resumen**: se ven los puntos y `exit 0`, pero nunca el número. Es una
trampa documentada del proyecto y ya costó una confusión en agosto.

**Smoke de producción** (tras cada merge, según `RUNBOOK.md`):

```
python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>   →  Todo OK ✅
```

**Gate de merge, idéntico en los 4 planes:** suite verde · CI verde · reviews sin CRITICAL ni
HIGH abiertos. **Nada se mergea en rojo.**

---

## 6. MEJORAS PROPUESTAS (no las pediste)

Clasificadas por impacto y esfuerzo. Las que encajan en un plan existente se marcan; las que
no, quedan como candidatas a plan propio.

| # | Mejora | Impacto | Esfuerzo | Dónde encaja |
|---|---|---|---|---|
| **M1** | **No se puede saber qué versión corre el VPS.** `/salud` es deliberadamente mudo (decisión de seguridad del Plan 5) y no hay otro camino. Diagnosticar «¿está desplegado el fix?» obliga a inferirlo por comportamiento. Propuesta: endpoint **autenticado** que devuelva el SHA desplegado — mudo para anónimos, útil para el owner | **Alto** — es exactamente lo que hace caro el Plan 3 | Bajo | Plan 3 lo sufre en T3.1; la mejora merece **tarea propia en el Plan 4** o plan corto |
| **M2** | **Deuda de integración: 3 PR abiertos sobre el mismo archivo.** #42 lleva 17 días, #43 lleva 15, #44 lleva 10, y ya hay 5 conflictos. Cada día que pasa encarece el merge. Propuesta: política de «un PR grande abierto a la vez» | **Alto** — es la causa de que nada de lo construido llegue al operador | Bajo (es política) | Esta tanda lo resuelve **una vez**; la política evita la reincidencia |
| **M3** | **`app.py` sigue siendo un monolito.** 6,610 líneas hoy; el PR #43 lo baja a ~3,370 al sacar el HTML. Sigue muy por encima del máximo de 800 líneas de las reglas del entorno. Propuesta: trocear por dominio (importador / catálogo / formulario / API de lectura) | Medio | **Alto** | **Plan nuevo.** No cabe en esta tanda sin poner en riesgo los 4 planes |
| **M4** | **La caché de Places no guarda los negativos.** Un negocio sin teléfono se paga, se descarta, y en la corrida siguiente —si la caché expiró— **se vuelve a pagar**. Cachear el resultado negativo cuesta poco | Medio | Bajo | **Plan 2, T2.2** lo contempla como alternativa a la migración |
| **M5** | **Rotar el token de Telegram.** Pendiente heredado (~14 copias según la memoria del proyecto). Retirarlo del código no lo desactiva: sigue vivo en el proveedor hasta que se rota ahí | **Alto** (seguridad) | Bajo | **Acción del owner.** Ningún plan puede automatizarla |
| **M6** | **Los tests tardan 117 s.** Aceptable hoy, molesto en cuanto el CI corra en cada PR de esta tanda. Propuesta: marcar las suites lentas y permitir un subconjunto rápido en local | Bajo | Bajo | Mejora de DX; sin plan asignado |
| **M7** | **Verificado y sano:** los tres archivos de credenciales de la raíz (`GMAPS_API_KEY.env`, `tokens-panelnioval.txt`, la cuenta de servicio `.json`) están **ignorados por git y no rastreados**. Se comprobó con `git check-ignore` y `git ls-files`. No hay nada que hacer — se deja escrito para que nadie vuelva a levantar la alarma | — | — | Ninguno |

---

## 7. AUTOEVALUACIÓN DEL DISEÑO

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | ¿Cuántas fuentes usa cada plan (mín. 5 de 6)? ¿Aparecen ECC, claude-mem, catalogo-agentes y community además de superpowers? | **Plan 1: 6/6 · Plan 2: 6/6 · Plan 3: 5/6 · Plan 4: 6/6.** Las cuatro fuentes citadas aparecen en **los cuatro planes**. El único descarte (`claude-ads` en el Plan 3) está justificado herramienta por herramienta en §4.1 |
| 2 | ¿Se asignó el reviewer/build-resolver específico del stack, no solo `code-reviewer`? | **Sí.** `python-reviewer` en los 4 planes y `typescript-reviewer` en los planes 2, 3 y 4 (6 archivos JS tras el PR #43), siempre **además** de `code-reviewer`. **No existe build-resolver de Flask** entre las 653: se asigna `django-build-resolver` marcado [OPCIONAL] con su condición de uso y la justificación escrita en §4.2 |
| 3 | ¿Toda tarea tiene etapa D (verificación)? ¿Toda tabla PROGRESO está pre-poblada? | **Sí.** Los 4 planes traen tabla «Gates de verificación por tarea» con una fila por tarea, incluidas las de investigación (su gate es la evidencia, no un test). Las 4 tablas PROGRESO están pre-pobladas con las 34 tareas en PENDIENTE |
| 4 | ¿Se diseñaron los 4 planes completos sin interrumpir con preguntas? | **Sí.** Cero preguntas durante el diseño. Las dudas se resolvieron leyendo código, ejecutando comandos (`gh pr view`, `git merge-tree`, `pytest`) y los documentos del repo; lo que quedó abierto está en §8 como decisión cerrada con default |
| 5 | ¿Las preguntas son ≤5, cerradas, ancladas, con default e impacto? ¿Cada supuesto está marcado? | **Sí.** **5 decisiones**, todas con 2-4 opciones excluyentes, ancla a tarea concreta, recomendación con motivo e impacto declarado. Hay **6 supuestos** marcados con el formato `SUPUESTO:` en su punto exacto y repetidos al pie de la tabla PROGRESO de su plan |
| 6 | ¿Los 4 documentos empiezan con el MISMO bloque INVARIANTES de ≤20 líneas? | **Sí.** Bloque idéntico, 8 viñetas, al inicio de los cuatro documentos, antes de cualquier otra sección |
| 7 | ¿Existe `RELEVO-actual.md` pre-poblado y el índice tiene `SESIÓN ACTUAL` y `ÚLTIMO RELEVO`? | **Sí.** [`RELEVO-actual.md`](RELEVO-actual.md) pre-poblado con el estado inicial (sesión 1, sin trabajo previo, siguiente paso Plan 1 · T1.0). El puntero está en el encabezado de este índice |

---

## 8. DECISIONES PENDIENTES

Cinco. Cerradas, ancladas, con default. **El diseño está completo y avanza con la opción
recomendada mientras no respondas.**

### D1 — ¿Aterrizar lo construido o rediseñar desde cero? · afecta: **los 4 planes**

- **A) Aterrizar, verificar y cerrar la brecha** *(recomendada)* — los PR #42 y #43 están al 12/12, con CI en verde y ya revisados; rediseñarlos tiraría ~40,000 líneas probadas y volvería a costar las mismas semanas.
- **B) Rediseñar desde cero** e ignorar los tres PR abiertos.
- **Impacto:** si B, los cuatro planes cambian de «verificar + aterrizar» a «construir», la tanda pasa de **34 a ~60 tareas**, y hay que cerrar los PR #42, #43 y #44 sin mergear, perdiendo el trabajo de agosto.
- *Mientras no respondas, el plan asume A.*

### D2 — Qué significa «tokens de la API» · afecta: **Plan 2, completo**

- **A) Google Places de PanelNioval** *(recomendada)* — es la **única API de pago del proyecto** donde viven los otros tres planes; se verificó que PanelNioval no usa ningún LLM (los únicos «token» del código son de autenticación y paginación).
- **B) Tokens LLM de BruceWhatsapp** (`claude-sonnet-4-6` + `gpt-4.1-mini`), que es la ruta que diste como proyecto.
- **C) Ambos**, como dos planes separados.
- **Impacto:** si **B**, el Plan 2 se reescribe entero contra otro repositorio (`llm_client_wa.py`, prompts de 36 KB que **ya traen `cache_control` puesto**) y sale de esta tanda, que quedaría en 3 planes. Si **C**, la tanda pasa de 4 a 5 planes.
- *Mientras no respondas, el plan asume A.*

### D3 — Qué hacer con el PR #44 (endurecimiento) · afecta: **Plan 4, Tarea T4.6**

- **A) Rebasarlo sobre `main` tras mergear #43 y resolver sus 5 conflictos** *(recomendada)* — sus 535 líneas viven en rutas de Flask, no en el HTML que #43 mueve: rebasar el pequeño sobre el grande es más barato.
- **B) Mergear #44 primero** y rebasar #43 sobre él.
- **C) Cerrar #44** y reimplementarlo después.
- **Impacto:** si **B**, el orden de aterrizaje se invierte y el PR de 28,582 líneas carga los conflictos, que es el escenario caro. Si **C**, se pierden cinco mejoras ya construidas y revisadas: rate limiting, escape de fórmulas, zona horaria, healthcheck y cierre ordenado ante `SIGTERM`.
- *Mientras no respondas, el plan asume A.*

### D4 — Umbral de cobertura del catálogo de ciudades · afecta: **Plan 1, Tareas T1.2 y T1.3**

> ✅ **RESUELTA el 2026-09-15 por T1.2, ejerciendo la opción A (decidir con datos).**
> **Veredicto: umbral ≥10 ferreterías** (~995 municipios), ni la B (`≥5`) ni la C (`≥20`).
> El dato que decide: los primeros 7.3 puntos de cobertura de masa ferretera cuestan 406
> ciudades y los siguientes 4.0 cuestan 445 — ahí muere la utilidad marginal. Brecha medida
> con el umbral vigente: **13.7 % de la masa ferretera nacional fuera; el Sureste al 65.6 %**.
> Decidido con `council` (4 voces); el Arquitecto **cambió** su posición inicial de ≥5 a ≥10.
> Evidencia: [`docs/investigacion/2026-09-15-cobertura-catalogo-ciudades.md`](../../investigacion/2026-09-15-cobertura-catalogo-ciudades.md).
> **Revocable por el owner:** es un parámetro de una línea.

- **A) Que T1.2 lo decida con datos** *(recomendada)* — la tarea mide la cobertura real por región y recomienda el umbral; decidirlo ahora sería elegir sin el número delante.
- **B) Fijar `≥5 ferreterías` ya**, por máxima cobertura.
- **C) Dejar el `≥20` actual** y no ampliar el catálogo.
- **Impacto:** si **B**, T1.2 se reduce a verificación, T1.3 se ejecuta siempre, el catálogo crece de 606 a del orden de 1,500 municipios y **sube el gasto potencial de Places** que el Plan 2 tiene que acotar. Si **C**, **T1.3 se elimina** y tu requisito de «todas las ciudades de la región» queda cubierto solo hasta donde llega el umbral actual.
- *Mientras no respondas, el plan asume A.*

### D5 — El gasto en pesos (CE6 del Plan 2) · afecta: **Plan 2, Tarea T2.2**

- **A) Conteo exacto de llamadas como métrica oficial** *(recomendada)* — ya funciona, es exacto, y no depende de que nadie habilite un acceso.
- **B) Habilitar acceso al billing de Google Cloud** para leer el importe real (quedó bloqueado en agosto: sin `gcloud`, la cuenta de servicio solo tiene Sheets y Drive).
- **Impacto:** si **B**, T2.2 gana una subtarea de lectura de facturación y **CE6 pasa de «documentado como gate del owner» a verificado**, lo que permite además calibrar los topes en dinero y no solo en llamadas.
- *Mientras no respondas, el plan asume A.*
