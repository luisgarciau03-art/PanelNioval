# PanelNioval — Instrucciones del Proyecto

Panel web interno de NIOVAL (distribuidora mayorista de ferretería/plomería) para operar ventas, contactos/prospectos, seguimiento y un formulario de encuestas de llamadas. Complementado por un script Selenium que envía catálogos por WhatsApp Web. Stack: **Flask + gunicorn · Google Sheets (gspread + google-auth) · Google Drive · Google Maps/Places · Railway (auto-deploy desde `main`)**.

## Arquitectura (leer antes de tocar código)

- **`app.py`** (**3,133 líneas**, Flask): rutas API + integración Sheets/Drive/Places + importador de prospectos en background. **Ya no contiene HTML**: el Plan 4 (T4.3) sacó las tres superficies a `templates/*.html` + `static/css/*.css` + `static/js/*.js`, de 6,368 a 3,133 líneas. Las rutas usan `render_template`; no queda ni un `render_template_string`. ⚠️ **M2 sigue abierta a medias**: el archivo baja del 50 % pero sigue muy por encima del límite de 800 líneas de las reglas globales, y bajar de ahí exige trocear el Python en módulos, que el Plan 4 **no** hace (decisión D6). El plan medía mal las superficies —5,067 líneas, contando el Python de en medio— cuando en realidad eran 3,235; por eso CE1 (`<800`) y su supuesto de rescate (`<1,100`) eran los dos inalcanzables extrayendo solo HTML.
- **`templates/` y `static/`** (Plan 4 · T4.3): las tres superficies. Son **HTML estático puro** —cero Jinja salvo los `url_for` de los enlaces, cero contexto de Python— porque todos los datos llegan por `fetch` a `/api/*`. Al tocarlas, ojo con dos cosas: Jinja **parsea la plantilla al renderizar**, así que un `{{` suelto revienta al servir la página y no al importar (lo fija `tests/test_plan4_extraccion.py`); y `.dockerignore` no debe excluir nunca `templates/` ni `static/`, o el VPS se despliega sin interfaz.
- **`envio_catalogo.py`** (antes `22.PY`): script Selenium **standalone** que corre en la PC del owner (no en Railway). Lee pedidos del día, busca teléfonos, abre WhatsApp Web con perfil Chrome local y envía mensajes + 4 archivos, marca `ENVIADO_WA` y reporta por Telegram. Auditoría completa: `docs/auditoria/2026-08-13-auditoria-22py.md`.
- **`nucleo_catalogo.py`** (Plan 3): lógica pura de la cola de catálogo (conclusiones elegibles, estados, validación de números). Sin selenium/gspread. **`worker_catalogo.py`**: worker transport-agnostic que procesa la worksheet `ENVIOS_CATALOGO` (transporte = worker local, decisión owner). El panel encola/consulta/corrige vía `/api/catalogo/*`. Diseño: `docs/superpowers/plans/2026-08-13-plan3-diseno-cola.md`.
- **`worker_catalogo_run.py`** (Plan 5): runner del worker local (Selenium + heartbeat + lock) que el owner corre en su PC (`instalar-worker.ps1` = Tarea Programada). Operación: `docs/RUNBOOK.md`; decisión de transporte: `docs/adr/2026-08-13-transporte-catalogo.md`. Smoke test: `tools/smoke_panel.py`.
- **Catálogo de ciudades (Plan 1):** el importador ya no trae la lista escrita a mano. `datos/ciudades_mx.json` (**606 municipios**, clave INEGI, estado, macro-región, alias, potencial e indicadores) se genera con `tools/generar_catalogo_ciudades.py` desde **DENUE 05_2026 + Censo 2020**, por URL directa y **sin token**. Lo sirve `/api/importador/ciudades` ya ordenado por `prioridad = potencial_mercado × factor_nioval`. ⚠️ El `.gitignore` cubre `*.json` por credenciales y hay una **excepción por ruta exacta**: sin ella el catálogo quedaba fuera del repo en silencio y el panel arrancaría sin él en el VPS. Modelo: `docs/adr/2026-08-28-modelo-relevancia-ciudades.md`; operación: `docs/RUNBOOK.md`.
- **Importador — gasto de Places:** el costo se mide por corrida (`text_search`, `place_details`, `cache_hits`, `duplicados_evitados`) y se publica en la UI y en Telegram. Las tarifas van por entorno **sin valor por defecto** (`PLACES_COSTO_TEXT_SEARCH`, `PLACES_COSTO_DETAILS`): sin ellas no se muestra importe, porque un `0.00` afirmaría que la corrida salió gratis. Topes: `PLACES_MAX_LLAMADAS_CORRIDA` (funciona siempre) y `PLACES_PRESUPUESTO_CORRIDA` (necesita tarifas). Al tocarlos la corrida queda en `presupuesto_agotado`, que **no es un error**. Caché de detalles en `PLACES_CACHE_FILE` (30 días, lleva teléfonos: 0600 y en `.gitignore`/`.dockerignore`). Ver `docs/RUNBOOK.md`.
- **Importador — los cuatro contadores:** `encontrados` (aprobados por los filtros de Places, deduplicados por `place_id` a nivel corrida), `nuevos_en_sheet` (**filas realmente escritas** — el número grande de la UI), `duplicados` (ya estaban en `LISTA DE CONTACTOS`) y `descartados` (reseñas, calificación o sin teléfono). Se cumple `nuevos_en_sheet + duplicados == encontrados`; `descartados` es disjunto. Un fallo de escritura **no** se cuenta como duplicado: la corrida termina en `error` con la causa.
- **Estado del importador:** vive en memoria de UN solo proceso (`--workers 1 --threads 4`). Además se persiste un registro mínimo y sin datos personales en `IMPORT_ESTADO_FILE` (temp del sistema) con el único fin de poder decir "se interrumpió" tras un reinicio; **nunca veta** una corrida nueva. Ver `docs/adr/2026-08-27-estado-compartido-importador.md`.
- **Autenticación fail-closed:** la app no arranca sin `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY` (`app.py:34-44`) — revienta con `RuntimeError` en vez de publicar el panel abierto. Ya arrancada, todas las rutas exigen el token (header `X-Dashboard-Token`, `?token=`, o cookie de sesión), y `/api/catalogo/heartbeat` exige por separado `WORKER_TOKEN` o devuelve 401. Único bypass, explícito y ruidoso: `PANEL_AUTH_DESACTIVADA=1` (usado por `tests/conftest.py` y para desarrollo local). El default nunca abre.
- **`Procfile` / `nixpacks.toml`**: `gunicorn app:app --workers 1 --threads 4 --worker-class gthread --timeout 120`. **Un solo worker a proposito**: `_import_job` y `_cache` son globales de modulo y con 2 procesos son 2 memorias distintas (razon completa en `docs/adr/2026-08-27-estado-compartido-importador.md`). Artefactos de Railway; se retiran cuando ese despliegue se apague (ver `docs/superpowers/plans/2026-08-17-despliegue-vultr.md`, Task 10).
- **`Dockerfile`**: imagen del panel para el VPS Vultr (`python:3.11-slim` + gunicorn, `--bind 0.0.0.0:8000`). **`despliegue/`**: plantillas versionadas de `docker-compose.yml` y del fragmento de Caddy que se copian al servidor `155.138.200.66`; la copia viva está en `/srv/panel/` (ver `docs/RUNBOOK.md` § Operación en el VPS y `docs/superpowers/specs/2026-08-17-panelnioval-vultr-design.md`).
- **`requirements.txt`**: deps del panel Flask. **`requirements-dev.txt`**: pytest + deps runtime de `envio_catalogo.py` (selenium, etc.), no instaladas en el contenedor del panel.

## Hojas de Google (IDs — fuente de verdad en `app.py:28-45` `SHEET_IDS`/`SHEET_GIDS`)

| Clave | Spreadsheet ID | Worksheet(s) | Uso |
|---|---|---|---|
| `ventas` | `1Dlpm6swrNSPnt9L5tQhoi2OMln0bb8bqqgeLACNos98` | Ventas | dashboard de ventas, comprobantes de pago (Drive) |
| `contactos` / `frecuentes` | `1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4` | `LISTA DE CONTACTOS`, FRECUENTES | prospectos, clientes frecuentes, importador |
| `respuestas` | `1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg` | `Respuestas de formulario 1` | encuestas de llamadas; **misma hoja de pedidos que `envio_catalogo.py`** |
| `mensajes` | `1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk` | `BD CONTACTOS`, `Mensajes` | teléfonos y plantillas que consume `envio_catalogo.py` |
| `seguimiento` / `bruce` | `1i0bWYQG7d5GVvOjuklZRpsg1bQfsScdY0bg7lytMXKM` | Seguimiento, PROSPECTOS BRUCE | seguimiento y prospectos de Bruce |

⚠️ `envio_catalogo.py` usa `BD CONTACTOS` (hoja `mensajes`) para teléfonos, mientras el panel usa `LISTA DE CONTACTOS` (hoja `contactos`): **son fuentes distintas**.

## Superficies del panel (rutas principales en `app.py`)

- `/` (dashboard), `/formulario` (encuesta de llamadas), `/importador` (scraping de prospectos con Places).
- API: `/api/prospectos/*`, `/api/ventas/*`, `/api/seguimiento*`, `/api/mensajes/update`, `/api/bruce/*`, `/api/formulario/{siguiente,guardar}`, `/api/importador/*`.

## Reglas del proyecto

- **Integración continua (desde 2026-08-28):** `.github/workflows/tests.yml` corre la suite en cada PR contra `main` y en cada push a `main`, y barre secretos y teléfonos sobre el diff del PR con `tools/barrer_secretos.py`. El workflow **no recibe ningún secreto**: `tests/conftest.py` ya aísla los clientes externos. El barrido **avisa, no bloquea** en su primera versión; una línea se exceptúa con `barrido-ok: <motivo>`, que exige motivo escrito a propósito. Qué hacer cuando el check sale rojo: `docs/RUNBOOK.md` § Cuando el check de CI sale en rojo. ⚠️ **Falta el gate del owner**: sin la protección de rama en `main` (Settings → Branches), el check informa pero **no impide** el merge.
- **Baseline de verificación:** `python -m pytest tests/` → **504 passed, 1 skipped** (al 2026-08-31, en `feat/rediseno-panel`, tras los 22 tests de la T4.3 del Plan 4). Antes: **482 passed, 1 skipped** en `feat/relevancia-ciudades-nacional` (2026-08-29, tras los 94 del Plan 1), y **388 passed, 1 skipped** en `main`. ⚠️ **El baseline es por rama**, y `feat/rediseno-panel` sale de la rama del Plan 1, no de `main`: su base son los 482, no los 388. En `main` eran **314**; la rama `perf/gasto-places-importador` del Plan 2 da **357 passed, 1 skipped** porque añade 43 tests suyos. Un gate escrito como «≥ 357» es inalcanzable desde una rama basada en `main` hasta que el Plan 2 mergee: comparar siempre contra el baseline de la rama base, no contra un número absoluto. (Al 2026-08-27, tras los 84 tests del Plan 3: 26 de frontend, 13 de progreso, 23 de estado compartido y 22 de conteo. **Ojo con el comando**: `pytest.ini` ya trae `addopts = -q`, así que añadir `-q` lo convierte en `-qq` y **suprime la línea del resumen** — se ven los puntos y `exit 0`, pero nunca el número. Por eso el comando oficial va sin `-q`. Antes: 230 al 2026-08-24, tras los 9 tests de rutas portables y archivos en Files/; 227 tras los 6 primeros; 221 tras los 2 del estado real en ya_encolado; 219 tras los 4 del cierre de Chrome huerfano; 215 tras los 10 del lock huerfano del worker; 205 tras los 5 de la lada de pais para WhatsApp; 200 tras los 13 de la columna CONTACTO y el formato de telefono; 187 tras los 16 del escape de formulas del importador; 171 tras los 6 del heartbeat compartido; 165 al 2026-08-17 tras la ronda final de correcciones de `feat/despliegue-vultr`; 164 justo antes; 155 al cierre del 2026-08-13; el 144 anterior era stale: PRs #6-#9 agregaron 11 tests a archivos existentes sin actualizar la documentación). Es el ÚNICO baseline oficial. Nada se mergea con la suite en rojo. Nota: importar `app.py` en frío tarda ~100s (`googleapiclient` + Defender); en caliente ~8s. **No es pandas**: medido con `sys.modules`, ni pandas ni numpy llegan a cargarse — pandas estaba en `requirements.txt` sin que nadie lo importara y se retiró. `pytest.ini` ancla el rootdir al proyecto.
- **Saltos de línea (desde 2026-08-31):** `.gitattributes` declara `* text=auto`. En **disco, en Windows**, los archivos están en **CRLF** —incluidos los `.py`—, así que un reemplazo por patrón escrito con `\n` **no casa y devuelve el texto igual, sin error**: normaliza antes de sustituir y verifica con `grep` **sobre el archivo**. Pero en **git los blobs son LF**, que es lo que reciben el runner de CI y el VPS; antes eso dependía de `core.autocrlf` de cada máquina y ahora es explícito. No confundir las dos cosas: la trampa del reemplazo es real y la afirmación "el repo está en CRLF" es falsa.
- **Datos personales:** teléfonos/nombres/correos de clientes **no** se commitean ni se vuelcan completos en logs; enmascarar (`+52...XXXX`). Desde el 2026-08-31 lo vigila `tests/test_pii_repositorio.py`: el proyecto usaba el teléfono de un **cliente real** como "número canónico de ejemplo" en 21 sitios, uno de ellos visible en la interfaz. ⚠️ El barrido de secretos del CI **no lo habría atrapado**: su patrón exige **10 dígitos contiguos**, así que ve la forma pegada pero **no** la separada por espacios, guiones o paréntesis — y el formato con espacios es justo el que usa la hoja, o sea el que acaba copiado a mano. Endurecer ese patrón es trabajo pendiente del Plan 0. `.gitignore` cubre `*.json` (credenciales) y `debug_invalid_*`/`debug_timeout_*` (screenshots con PII de `envio_catalogo.py`).
- **Secretos:** nada hardcodeado. `GOOGLE_CREDENTIALS_JSON`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` van por variables de entorno en Railway. **Pendiente owner:** rotar el token Telegram `8404009072` (expuesto en el historial git; ~14 copias).
- **Ramas:** **nunca** trabajar directo en `main` (Railway auto-deploya). Una rama por plan; PRs con `gh pr create --base main`; merge `--squash` solo con baseline verde y reviews sin CRITICAL/HIGH abiertos.
- **Idioma:** código con nombres en español (`guardar_respuesta_formulario`, `buscar_telefono`); docs y commits en español con prefijos convencionales (`fix:`, `feat:`, `test:`).

## Planes activos

**Tanda 2026-08-27, validada y ampliada el 2026-08-28** (6 planes, 53 tareas, **33 hechas**).
Índice: `docs/superpowers/plans/2026-08-27-indice-tanda.md`.
⚠️ **Empieza por** `docs/superpowers/plans/2026-08-28-validacion-tanda.md`: los anclajes
`archivo:línea` de los planes originales quedaron desplazados hasta 1,000 líneas cuando
`app.py` creció de 4,948 a 6,098, y ese documento trae los corregidos, dice qué trabajo ya
está hecho (B9 y B11 del Plan 1) y qué criterios cambiaron (CE1 del Plan 4, CE6 del Plan 2).
Cada plan abre además con una §0 de validación que **manda** sobre el resto del documento.

Orden de ejecución **0 → 2 → 1 → 4 → 5** (el Plan 3 está cerrado, PR #36 `ae0e1c9`):

| Plan | Estado | Qué resuelve |
|---|---|---|
| 0 — Integración continua | **4/4 ✅** | CI en cada PR: suite + barrido de secretos. PR #40 `c10d063` |
| 2 — Gasto de Google Places | **9/9 ✅** | Places optimizado, medidor y tope. PR #38 `4e06e64` |
| 1 — Relevancia de ciudades | **10/10 ✅** | Catálogo nacional del INEGI y modelo de dos factores. Rama `feat/relevancia-ciudades-nacional` |
| 4 — Rediseño del panel | 0/12 | **SIGUIENTE** — movimiento, presentación y estados de carga en las 3 superficies |
| 5 — Endurecimiento | 0/8 | Rate limiting, escape de fórmulas, zona horaria, healthcheck |

Las decisiones abiertas al owner están en el índice §8; los nueve gates del owner, en §7.1.

**Tanda anterior 2026-08-13** (5 planes, histórica). Índice:
`docs/superpowers/plans/2026-08-13-indice-tanda.md`.
1. Evaluación `envio_catalogo.py` + baseline de tests + sanitización de secretos (**este plan**).
2. Evaluación del formulario de llamadas + matriz de flujo.
3. Integración catálogo + estados + corrección de número.
4. Captura de correo → columna T.
5. Operación 100% Railway (decisión de transporte WhatsApp = gate owner).

## Pendientes conocidos (gates del owner)

- Rotar `TELEGRAM_TOKEN` y cargar secretos en Railway (Plan 5 T5.3).
- Elegir transporte de WhatsApp para Railway: A=WhatsApp Business API (recomendado) / B=worker local / C=Selenium headless (Plan 5 T5.1).
- **Validar el top-20 de ciudades del Plan 1** y decidir si el ranking premia el mercado o lo que queda por cosechar (`docs/investigacion/2026-08-29-verificacion-plan1.md` §2.3 y §7).
- Corridas reales de WhatsApp (Plan 3 T3.6 / Plan 5 T5.5) y confirmación de la columna T de `LISTA DE CONTACTOS` (Plan 4 T4.1).
- ~~Autenticación del panel (M1)~~ — **RESUELTO** en `feat/despliegue-vultr`: el gate es fail-closed (`app.py:34-82`). Pendiente real: la exposición sigue **viva en Railway** — `https://web-production-1d453.up.railway.app/` corre sin `PANEL_DASHBOARD_TOKEN` definida ahí — hasta que ese despliegue se elimine (gate del owner, Task 10 de `docs/superpowers/plans/2026-08-17-despliegue-vultr.md`).
