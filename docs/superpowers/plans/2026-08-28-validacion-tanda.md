# VALIDACIÓN DE LA TANDA 2026-08-27 CONTRA EL CÓDIGO EN DISCO

**Fecha:** 2026-08-28 · **Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Método:** cada afirmación de los cuatro planes se contrastó con un comando ejecutado en
esta sesión. **Ninguna línea de este documento sale de memoria.**
**Índice de la tanda:** [`2026-08-27-indice-tanda.md`](2026-08-27-indice-tanda.md)

---

## 1. POR QUÉ HACÍA FALTA

La tanda se diseñó el 2026-08-27 con `app.py` en **4,948 líneas** y la suite en **230
tests**. Desde entonces se ejecutó el **Plan 3 completo (10/10)** y **7 de las 9 tareas del
Plan 2**. Hoy `app.py` tiene **6,098 líneas** y la suite **357 passed, 1 skipped**.

**Todos los anclajes de línea de los tres planes vivos estaban desplazados**, algunos por
más de mil líneas. Un plan cuyos `archivo:línea` no casan manda al ejecutor al sitio
equivocado, y un ejecutor en sesión fría no tiene cómo saberlo.

---

## 2. LOS 30 HALLAZGOS

Cada fila lleva el comando con el que se comprobó. ✅ = el plan acertaba y sigue vigente ·
🔧 = corregido en el documento · ⚠️ = el plan pedía algo que ya está hecho · 🆕 = hallazgo
nuevo.

### 2.1 Baseline y tamaño

| # | Afirmación del plan | Realidad medida hoy | |
|---|---|---|---|
| V1 | Baseline `230 passed` (citado ~14 veces en los 4 planes) | `python -m pytest tests/` → **357 passed, 1 skipped**, exit 0, 9.69 s | 🔧 |
| V2 | El comando es `pytest tests/ -q` | **`pytest tests/` sin `-q`**: `pytest.ini` ya trae `addopts = -q` y el segundo lo vuelve `-qq`, que suprime el resumen | 🔧 |
| V3 | `app.py` tiene 4,948 líneas | **6,098** | 🔧 |
| V4 | Las tres superficies son "~3,000 líneas" | **5,067**: dashboard 2,651 · formulario 1,852 · importador 564. Python real: **1,031** | 🔧 |

### 2.2 Anclajes de `app.py`

| # | Dónde decía el plan | Dónde está hoy | |
|---|---|---|---|
| V5 | `HTML` en `app.py:968` | **`app.py:1031`** | 🔧 |
| V6 | `FORMULARIO_HTML` en `app.py:3618` | **`app.py:3682`** | 🔧 |
| V7 | `IMPORTADOR_HTML` en `app.py:4595` | **`app.py:5534`** | 🔧 |
| V8 | `const CIUDADES_MX` en `app.py:4727` | **`app.py:5679`** | 🔧 |
| V9 | Cálculo de `relevancia` en `app.py:848-855` | **`app.py:913-919`** | 🔧 |
| V10 | `_buscar_negocios` en `app.py:4324` | **`app.py:4760`** | 🔧 |
| V11 | `_worker_importador` | **`app.py:5183`** | 🔧 |
| V12 | `_exportar_a_sheets` en `app.py:4423` | **`app.py:5056`** | 🔧 |
| V13 | `gmaps_client.place(pid)` en `app.py:4366` | encapsulado en **`_detalle_de_place` (`app.py:4557`)**, ya con `fields` | 🔧 |
| V14 | Fusión JS de ciudades en `app.py:4795-4816` | **`app.py:5750-5779`** | 🔧 |
| V15 | Chips de ciudad en `app.py:4830-4843` | **`app.py:5795-5812`** | 🔧 |
| V16 | `getSortedCiudades()` en `app.py:2150-2157` | **`app.py:2213`** | 🔧 |
| V17 | Logo de Cloudinary sin dimensiones en `app.py:4651` | **tres** sitios: `1172`, `3736`, `5594` | 🔧 |
| V18 | Rejilla `1fr 1fr 1fr` del importador en `app.py:4627` | **`1fr 1fr 1fr 1fr`** en `app.py:5566` — son los **cuatro** contadores del Plan 3 | 🔧 |

### 2.3 Trabajo que el plan pedía y ya estaba hecho

| # | Lo que pedía | Estado real | |
|---|---|---|---|
| V19 | **Plan 1 · T1.7 punto 5**: escapar el nombre de ciudad, hoy interpolado en `onclick="seleccionarCiudad('${c.ciudad}')"` | **HECHO.** `app.py:5810` usa `escaparHtml(c.ciudad)`, el nombre viaja en `data-ciudad` y hay un **listener delegado** (`app.py:5818-5823`). `seleccionarCiudad` ya no existe en el archivo | ⚠️ |
| V20 | **B11**: el filtro renumeraba el ranking y la ciudad 47 salía con medalla de oro | **HECHO.** `app.py:5767` fija `c.rank` una vez sobre el catálogo completo; `app.py:5802` lo lee con `(c.rank != null) ? c.rank : 0`. El comentario del código documenta el síntoma | ⚠️ |
| V21 | **M13**: el escape de HTML falta en el importador | **OBSOLETA.** Ya existe. T4.3 sigue siendo válida para centralizarlo en `js/comun.js`, pero **ya no cierra una brecha de seguridad** | ⚠️ |
| V22 | **Plan 2 · R5**: el archivo de caché podría commitearse con teléfonos dentro | **MITIGADO.** `.gitignore` y `.dockerignore` cubren `places_detalles.json`, `places_detalles.json.*.tmp`, `importador_estado.json` y su temporal, cada uno con su comentario | ✅ |
| V23 | **M11**: ocho archivos de otro proyecto en `docs/` | **RESUELTA** en `e6f25fc`. Queda `Nuevo documento de texto.txt` vacío en la raíz | ⚠️ |
| V24 | **M4**: Telegram solo avisa en el camino feliz | **RESUELTA** en el Plan 3 · T3.4 | ✅ |

### 2.4 Supuestos del plan que dejaron de ser ciertos

| # | Lo que suponía | Realidad | |
|---|---|---|---|
| V25 | gunicorn corre `--workers 2` (Plan 2 §D5, Plan 3) | **`--workers 1 --threads 4`** en **tres** sitios: `Dockerfile:23`, `nixpacks.toml:8`, `Procfile:1`. El handoff situaba el del Dockerfile en la línea 17: es la **23** (17 es el comentario) | 🔧 |
| V26 | `if lugares: break` corta las **variaciones** (Plan 2 §D3) | Corta **reintentos**. Las tres variaciones corrían siempre, así que el gasto era mayor de lo estimado. Ya resuelto por T2.4 con `MAX_VARIACIONES_SIN_APORTE` (`app.py:4395`) y `CORTAR_PAGINAS_SIN_APORTE` (`app.py:4396`) | 🔧 |
| V27 | El array de ciudades tiene "~250 entradas" | **293 entradas · 238 únicas · 50 duplicados exactos** (medido con `Counter`). El `[...new Set()]` de `app.py:5759` colapsa por cadena exacta; las variantes con y sin acento sobreviven y generan **dos consultas a Places** | 🔧 |
| V28 | **Plan 4 · CE1**: `wc -l app.py` < 800 tras T4.3 | **Inalcanzable con T4.3 sola.** Sacadas las tres superficies quedan **1,031 líneas de Python**. Convertido en decisión **D1** | 🆕 |
| V29 | **Plan 2 · CE6**: reducción de costo ≥ 60 % contra la consola de facturación | **No se puede evaluar en pesos**: el consumo por SKU es gate del owner, abierto. Convertido en decisión **D2** | 🆕 |
| V30 | **Gate 5 del owner**: "añadir las variables a `.env.example`" leído como crear el archivo | El archivo **existe y está versionado** (21 líneas, contiene `PANEL_DASHBOARD_TOKEN`), pero **ninguna** de las 5 variables de Places está. El bloqueo es de la herramienta de Claude (no puede escribir `.env*`), no del proyecto. Bloque exacto para pegar: índice §7.1 | 🆕 |

### 2.5 Mejoras reverificadas: siguen abiertas

Cada una con el comando que lo demuestra.

| # | Mejora | Comando | Salida |
|---|---|---|---|
| M1 | Sin CI | `ls -d .github` | *No such file or directory* |
| M2 | Zona horaria | `grep -c "datetime.now()" app.py` · `grep -rn TZ Dockerfile despliegue/` | **6** · *(vacío)* |
| M5 | Sin rate limiting | `grep -c "limiter\|Limiter\|ratelimit" app.py` | **0** |
| M9 | Sin healthcheck | `grep -c HEALTHCHECK Dockerfile` | **0** |
| M12 | `app.py` > 800 líneas | `wc -l app.py` | **6,098** |
| M14 | Escape de fórmulas en una sola ruta | `grep -n "_escapar_formula" app.py` | definido en **5037**, usado **solo** en **5115** |
| M15 | Logo sin dimensiones | `grep -n cloudinary app.py` | **1172**, **3736**, **5594** |
| M3 | Hilo daemon | `grep -n "daemon=True" app.py` | **5473** — 🟡 parcialmente mitigado por el registro persistido del Plan 3 (`app.py:4644`) |

Sin cambio, verificados hoy: **16** `class="loading"`, **12** `transition:all`, **4**
`render_template_string`.

---

## 3. QUÉ SE CAMBIÓ EN LOS DOCUMENTOS

| Documento | Cambio | Verificación |
|---|---|---|
| `2026-08-27-plan1-...md` | §0 nueva con anclajes, los dos entregables ya hechos y 2 `SUPUESTO:`. Gates de baseline `≥230` → `≥357` | `grep -c "## 0. VALIDACIÓN AL 2026-08-28"` → 1 · `grep -c "357 passed"` → 3 |
| `2026-08-27-plan2-...md` | §0 nueva con anclajes, R5 mitigado, CE6 replanteado y 2 `SUPUESTO:`. Tabla de ahorro medido | `grep -c` → 1 · `grep -c "357 passed"` → 4 |
| `2026-08-27-plan4-...md` | §0 nueva con anclajes, M13 obsoleta, CE1 inalcanzable con 1 `SUPUESTO:`, y qué hereda de los planes 2 y 3 | `grep -c` → 1 · `grep -c "357 passed"` → 2 |
| `2026-08-27-indice-tanda.md` | Reescrito: 6 planes, orden nuevo, diversidad por fuente, mejoras reverificadas, autoevaluación, marcador 17/53 y bloque DECISIONES PENDIENTES | — |
| `2026-08-28-plan0-...md` | **Nuevo.** 4 tareas. Origen: M1 | — |
| `2026-08-28-plan5-...md` | **Nuevo.** 8 tareas. Origen: M5, M14, M2, M9, M3 | — |

Los tres planes existentes se editaron **en su sitio**, no se duplicaron: llevan las tablas
PROGRESO con la evidencia real de lo ya ejecutado (commits, números de tests, gates de
review), y crear documentos paralelos con la fecha de hoy habría partido ese rastro en dos.
Lo nuevo —los planes 0 y 5 y esta validación— sí lleva la fecha de hoy.

**Las líneas históricas no se falsificaron.** El `**Baseline verificado el 2026-08-27:**
230 passed` del encabezado de cada plan se dejó intacto porque era cierto ese día; lo que se
actualizó son los **gates prospectivos** (`≥ 230 passed` → `≥ 357 passed`), que son los que
el ejecutor va a aplicar.

---

## 4. LO QUE NO SE VALIDÓ, Y POR QUÉ

Honestidad sobre el alcance de este barrido:

- **No se verificó nada que exija correr el panel contra Google.** Sheets y Places necesitan
  credenciales vivas y facturarían. Todo lo de arriba sale de lectura de código, `grep` y la
  suite de tests, que corre con los clientes sustituidos.
- **No se verificó el comportamiento en el VPS.** gunicorn no corre en Windows (necesita
  `fcntl`); es el gate 3 del owner.
- **No se validó el Plan 3** más allá de confirmar que sus entregables están en el código.
  Está cerrado y mergeado; revalidarlo entero sería trabajo sin destino.
- **Un barrido que no encuentra nada no demuestra que no hay nada.** Los `grep` de §2.5 se
  comprobaron en las dos direcciones donde tenía sentido: el de `_escapar_formula` encuentra
  el uso que **sí** existe (5115) y no inventa otros; el de rate limiting da 0 sobre un
  patrón que **sí** casaría si estuviera (`limiter`, `Limiter`, `ratelimit`).

---

## 5. MENSAJE DE ARRANQUE PARA LA SIGUIENTE SESIÓN

Para pegar tal cual en un chat nuevo.

```
Vas a ejecutar los planes de trabajo del proyecto PanelNioval.

PROYECTO: C:\Users\PC 1\PanelNioval
RAMA DE TRABAJO: depende del plan (ver abajo). NUNCA main: Railway y Vultr
auto-despliegan desde ahi.

ANTES DE TOCAR CODIGO, lee en este orden:
1. C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md  <- biblioteca de 653
   herramientas. Confirma que la leiste citando el total y las 6 fuentes.
2. C:\Users\PC 1\PanelNioval\CLAUDE.md  <- reglas del proyecto (respetalas todas)
3. docs/superpowers/plans/2026-08-28-validacion-tanda.md  <- EMPIEZA AQUI.
   Los anclajes de linea de los planes viejos estaban desplazados hasta 1000
   lineas; este documento trae los corregidos y dice que trabajo YA esta hecho.
4. docs/superpowers/plans/2026-08-27-indice-tanda.md  <- orden, dependencias,
   marcador global (§6), gates del owner (§7.1) y DECISIONES PENDIENTES (§8)
5. Documentos de planes (cada uno abre con una §0 de validacion que MANDA sobre
   los numeros de linea del resto del documento):
   - Plan 0: docs/superpowers/plans/2026-08-28-plan0-integracion-continua.md
   - Plan 1: docs/superpowers/plans/2026-08-27-plan1-relevancia-ciudades-nacional.md
   - Plan 2: docs/superpowers/plans/2026-08-27-plan2-optimizacion-gasto-places.md
   - Plan 3: docs/superpowers/plans/2026-08-27-plan3-bug-conteo-y-pantallas-carga.md  (CERRADO)
   - Plan 4: docs/superpowers/plans/2026-08-27-plan4-rediseno-profesional-panel.md
   - Plan 5: docs/superpowers/plans/2026-08-28-plan5-endurecimiento-panel.md
6. ADRs de decisiones ya tomadas (no las reabras sin motivo):
   - docs/adr/2026-08-27-estado-compartido-importador.md
   - docs/adr/2026-08-28-places-legacy-vs-new.md
   - docs/investigacion/2026-08-28-costo-places-antes.md
7. Toolkit del proyecto: no aplica (.claude/ esta vacio)
8. Memoria: usa claude-mem (mem-search) para recuperar contexto previo.

ESTADO: 17/53 tareas (32%). Plan 3 COMPLETADO y mergeado. Plan 2 va 7/9.
BASELINE: python -m pytest tests/  ->  357 passed, 1 skipped
  OJO: SIN -q. pytest.ini ya trae addopts=-q y el segundo lo vuelve -qq, que
  suprime la linea del resumen: se ven los puntos y exit 0, nunca el numero.

EMPIEZA POR: Plan 0 completo (4 tareas, no toca app.py, deja CI corriendo para
todos los PR siguientes). Luego Plan 2 T2.7 y T2.8 para cerrar y mergear el
PR #38. Despues Plan 1, Plan 4 y Plan 5. Orden: 0 -> 2 -> 1 -> 4 -> 5.

RAMAS (una por plan, desde main actualizado):
  - Plan 0: ci/pytest-en-cada-pr           (crear)
  - Plan 2: perf/gasto-places-importador   (YA EXISTE, PR #38 en BORRADOR)
  - Plan 1: feat/relevancia-ciudades-nacional  (crear)
  - Plan 4: feat/rediseno-panel                (crear)
  - Plan 5: fix/endurecimiento-panel           (crear)
  NO borres la rama fix/conteo-importador-y-estados-carga de origin: el merge
  fue squash y sus 10 commits (uno por defecto) son la unica via de revertir un
  arreglo sin perder los otros.

REGLAS DE EJECUCION:
- Cada tarea usa las herramientas de su tabla de asignacion (Herramienta+Fuente).
  NO las sustituyas por Superpowers por comodidad: son 14 de las 653 y son la
  capa de PROCESO, no el catalogo. Si una no esta disponible, reportalo y usa la
  alternativa de su misma categoria en la biblioteca, diciendo cual y por que.
- Usa el reviewer del stack (python-reviewer) ADEMAS de code-reviewer, nunca en
  su lugar. Para Flask no hay build-resolver propio: si falla una instalacion o
  un import, usa django-build-resolver (indice §3.3 explica por que ese).
- TDD donde el plan lo marque. Gates antes de cerrar cada tarea: python-reviewer
  + code-reviewer, security-reviewer y silent-failure-hunter cuando aplique.
- Respaldo ANTES del cambio: python tools/respaldar_hojas.py docs/auditoria/respaldos/<fecha>
  y confirma que los archivos existen en disco, con tamano > 0, antes de seguir.
- Nada se borra: lo retirado va al respaldo fechado.
- Datos personales de clientes: no se commitean ni se vuelcan completos en logs.
- Credenciales: nunca por valor, solo por nombre de variable y archivo:linea.
- Verifica que cada reemplazo por patron quedo EN el archivo, no que la
  herramienta dijo "aplicado": un replace que no casa devuelve el texto igual.

PROGRESO (obligatorio):
- Al cerrar cada tarea actualiza la tabla PROGRESO del plan (estado + evidencia:
  commit/test/PR + fecha) y el marcador global del indice (§6).
- En cada reporte: % del plan actual, % global (sobre 53) y bloqueos.

MERGE (automatico con gates):
- Al TERMINAR cada plan: gh pr create --base main y, SI Y SOLO SI los gates
  estan verdes (baseline sin regresiones, reviews sin CRITICAL/HIGH abiertos),
  mergealo con gh pr merge --squash.
- Si algun gate falla: NO mergees. Deja el PR abierto, documenta que falta en
  PROGRESO y notificame.
- Commits convencionales en espanol (feat:/fix:/test:/docs:/chore:/refactor:),
  mensajes en ASCII y terminando con:
  Co-authored-by: LUIS V <luisht3g@gmail.com>

DUDAS DURANTE LA EJECUCION (no te detengas):
- Resuelvelas leyendo el codigo, CLAUDE.md o claude-mem. Si sigue ambiguo, elige
  la opcion mas razonable, registrala como SUPUESTO: en la tabla PROGRESO de esa
  tarea y CONTINUA.
- Las dudas se acumulan y se presentan JUNTAS al cerrar cada plan: cerradas
  (2-4 opciones), ancladas a su tarea, con recomendacion e impacto. Maximo 5.
- Solo parate a preguntar si avanzar seria destructivo o inseguro (borrar datos,
  tocar produccion, rotar credenciales) o si un gate falla.

DECISIONES PENDIENTES YA PLANTEADAS AL OWNER (indice §8): D1 alcance del troceo
de app.py, D2 como cierra el Plan 2 sin la consola de facturacion, D3 tamano del
catalogo de ciudades, D4 donde entra el Plan 0, D5 rate limiting en memoria o
Redis. Mientras no haya respuesta, cada plan asume su opcion A y avanza.

GATES DEL OWNER (reportalos, NO los intentes) - indice §7.1, nueve abiertos:
consumo por SKU de Places, corrida real de la ciudad de referencia, verificacion
con gunicorn en el VPS, recargar /importador a media corrida, anadir 5 nombres a
.env.example (el bloque exacto esta en el indice §7.1), validacion humana del
top-20 de ciudades, rotar TELEGRAM_TOKEN, apagar Railway, y activar la
proteccion de rama en main.

DECISIONES YA TOMADAS QUE NO DEBES REHACER:
- gunicorn corre --workers 1 --threads 4 --worker-class gthread, en TRES sitios:
  Dockerfile:23, nixpacks.toml:8 y Procfile:1. Hay 3 tests que fallan si alguien
  vuelve a subirlo. Razon en el ADR del estado compartido.
- El dedup por corrida ya existe: _buscar_negocios recibe `vistos` y
  `con_detalle`. Son DOS conjuntos distintos a proposito. Para reportar ahorro
  usa incidencias['detalles_evitados'], NO 'ya_vistos_otra_cat'.
- El denominador de progreso ya es ajustable (_avanzar_progreso). Si recortas
  variaciones, baja BASE_POR_CATEGORIA; la barra se ajusta sola y no retrocede.
- El escapado del nombre de ciudad (B9) y el rank fijo al filtrar (B11) YA estan
  hechos (app.py:5767, 5802, 5810). Plan 1 T1.7 los VERIFICA, no los reimplementa.
- El medidor de gasto y el estado presupuesto_agotado ya existen en la UI.

TRAMPAS DE ESTE ENTORNO:
- NUNCA uses `git add docs/` ni `git add -A docs/`: arrastra archivos de otro
  proyecto. Anade siempre por ruta explicita.
- Un \n escrito a mano en un heredoc NO llega literal a Python: los reemplazos
  por patron con \\n no casan y devuelven el texto igual, sin error. Usa
  coincidencia por linea o chr(92)+"n", y verifica con grep en el archivo.
- Los heredocs largos con backticks y comillas rompen el parser de bash de este
  entorno. Escribe el script a un archivo y ejecutalo.
- Los archivos de docs/ estan en CRLF. Al editarlos con Python usa newline="".
- Importar app.py en frio tarda ~100 s tras modificarlo (Defender). No es un
  cuelgue: usa timeouts largos o corre en background.
- No edites app.py mientras un reviewer lo esta leyendo.
- Un test que afirma la FORMA del arreglo y no su efecto se rompe solo. Y un test
  que pasa con y sin el arreglo no vale nada: comprueba en las dos direcciones.
- La fixture `entorno` sustituye _enviar_telegram_importador por un no-op. Para
  ejercitar el notificador de verdad usa monkeypatch pelado.

NOTIFICACION: al terminar cada plan y al terminar el proyecto, notificame
(PushNotification si esta disponible) con: que se mergeo (PR y SHA), estado de
gates, % global y pendientes.

AL CERRAR: guarda contexto para la siguiente sesion (claude-mem / handoff).
```
