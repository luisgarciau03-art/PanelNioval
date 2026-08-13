# Auditoría integral — `22.PY` (envío de catálogo por WhatsApp Web)

**Fecha:** 2026-08-13 · **Plan:** 1 (`plan1/evaluacion-22py`) · **Alcance:** análisis, sanitización de secretos y tests de caracterización. **No** se cambia comportamiento del script (eso corresponde a Planes 3/5).

**Método:** auditoría estática multidimensión con 4 revisores independientes en paralelo (python-reviewer, security-reviewer, silent-failure-hunter, code-reviewer — todos de `catalogo-agentes`), consolidados y deduplicados por severidad. Inventario cruzado contra el código real (cada dependencia citada con línea).

---

## 1. Inventario de dependencias (T1.1)

### 1.1 Hojas de Google (Sheets)

| Rol en `22.PY` | Constante / línea | Spreadsheet ID | Worksheet | Columnas usadas (0-based) |
|---|---|---|---|---|
| Pedidos / formulario | `SPREADSHEET_ID_PEDIDOS` (L33) · `SHEET_NAME_PEDIDOS` (L34) | `1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg` | `Respuestas de formulario 1` | col 0 = fecha, col 1 = tienda, col 9 (J) = estado; se agrega/usa columna `ENVIADO_WA` al final |
| Teléfonos | `SPREADSHEET_ID_TELEFONOS` (L35) · `SHEET_NAME_TELEFONOS` (L36) | `1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk` | `BD CONTACTOS` | col 0 = nombre tienda, col 18 (S) = teléfono |
| Mensajes | `SHEET_NAME_MENSAJE` (L37) | `1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk` (mismo que teléfonos) | `Mensajes` | col A (`col_values(1)`), salta 2 primeras filas |

**Cruce con `app.py` (el panel):**
- El ID de pedidos `1U_z1KN…` es `SHEET_IDS['respuestas']` en `app.py:32`.
- El ID de teléfonos/mensajes `1oEtAiYa…` es `SHEET_IDS['mensajes']` en `app.py:33`.
- ⚠️ `22.PY` usa la worksheet **`BD CONTACTOS`** (dentro del sheet `mensajes`), mientras el panel usa **`LISTA DE CONTACTOS`** en un spreadsheet **distinto** (`SHEET_IDS['contactos'] = 1wgEentS16…`, `app.py:31`). Son fuentes de teléfono diferentes — relevante para los Planes 3 y 4.

### 1.2 Credenciales

| Aspecto | `22.PY` | `app.py` (panel) |
|---|---|---|
| Librería | `oauth2client.ServiceAccountCredentials` (L10, **deprecada**) | `google.oauth2.service_account.Credentials` (`google-auth`) |
| Archivo de credenciales | `credentials.json` (L557) | `bubbly-subject-412101-c969f4a975c5.json` **o** env `GOOGLE_CREDENTIALS_JSON` (`app.py:63-70`) |
| Scopes | `spreadsheets.google.com/feeds` + `drive` (L556) | `auth/spreadsheets` + `auth/drive` |

→ Divergencia de credenciales: `22.PY` y `app.py` esperan **archivos JSON con nombres distintos** y **librerías distintas**. En Railway solo existe `GOOGLE_CREDENTIALS_JSON` (env). Esto es un bloqueo de portabilidad (ver §3, matriz Railway).

### 1.3 Archivos locales (disco)

| Recurso | Ruta (línea) | Uso |
|---|---|---|
| Carpeta de media | `PDF_LOCAL_PATH = 'C:/Users/PC 1/Files mensajes'` (L39) | base de los 4 archivos a enviar |
| Adjuntos | `IMAGENES = ['IMG1.jpg','Video1.mp4','CATÁLOGO NIOVAL.pdf','LPNIOVAL.pdf']` (L40) | media + documentos |
| Perfil Chrome | `FALLBACK_PROFILE_DIR = 'C:/Users/PC 1/ChromeSeleniumProfile'` (L42) | sesión persistente de WhatsApp Web (QR) |
| Binario Chrome | `CHROME_BINARY = 'C:/Program Files/Google/Chrome/Application/chrome.exe'` (L43) | navegador |
| Debug (salida) | `debug_invalid_*.png/.html`, `debug_timeout_*.html` (L306-355) | screenshots/HTML con datos de clientes, **sin limpieza** |

### 1.4 Binarios y red

| Dependencia | Detalle |
|---|---|
| Chrome + ChromeDriver | `ChromeDriverManager().install()` (L144) descarga el driver en runtime |
| `web.whatsapp.com` | URL `send?phone=…` (L284) — requiere sesión iniciada (QR) |
| `api.telegram.org` | reporte por bot (L66) |

### 1.5 Dependencias Python (imports vs `requirements.txt`)

`22.PY` importa: `gspread`, `oauth2client`, `requests`, `selenium`, `webdriver_manager`, `pyperclip` (opcional).
`requirements.txt` **NO** lista: `selenium`, `webdriver-manager`, `pyperclip`, `oauth2client`, `requests`. Solo comparte `gspread`. → Instalación reproducible imposible sin `requirements-dev`/actualización (ver hallazgos).

---

## 2. Hallazgos (T1.2)

> Consolidación deduplicada de los 4 revisores independientes. Severidad: CRITICAL (bloquea) · HIGH (corregir antes de operar) · MEDIUM (mantenibilidad/fiabilidad) · LOW (estilo/menor). **Total: 34 hallazgos (5 CRITICAL · 10 HIGH · 11 MEDIUM · 8 LOW).**

### CRITICAL

| ID | Línea(s) | Hallazgo | Remediación | Estado |
|---|---|---|---|---|
| C1 | 62-63 | **Token Telegram + chat_id hardcodeados** en texto plano. El token `8404009072:…` ya vive en ~14 copias del historial (pendiente conocido de rotación). | Mover a `os.environ.get`; rotar el token (owner). | **RESUELTO en T1.3** (movido a env) · rotación = gate owner T5.3 |
| C2 | 419-461, 463-501, 525-552, 665-685 | **Falso positivo de idempotencia:** `enviar_mensaje`/`enviar_archivo`/`click_*` fallan con `print`+`return` **sin señal de error**; `main` marca `ENVIADO_WA` con timestamp igual. Un cambio de selector de WhatsApp Web → el cliente no recibe nada pero la fila queda "enviada" para siempre (la propia idempotencia bloquea el reintento). | Que esas funciones devuelvan `bool` en toda rama y `main` fije `error_envio` con ese valor. | Corrección = **Plan 3** (no se toca aquí; documentado con `# BUG conocido:` en tests) |
| C3 | 9-19, 26 vs `requirements.txt` | **Dependencias no declaradas:** importa `selenium`, `webdriver-manager`, `pyperclip`, `oauth2client`, `requests`; ninguno en `requirements.txt`. Cualquier despliegue limpio falla con `ImportError`. | `requirements-dev.txt` con las deps del script (T1.4). | **RESUELTO en T1.4** (requirements-dev.txt) |
| C4 | 248-268 | **`ensure_sent_column` corrompe la hoja:** si `row_values(1)` falla (rate-limit), `headers=[]` → `col=1` (= columna `fecha`). Entonces `sent_val` lee la fecha (siempre truthy) → **todas las filas parecen ya enviadas** y no se envía nada; peor: un `update_cell` posterior sobrescribe la fecha con un timestamp. | No hacer fallback a `[]`; abortar/reintentar; verificar que el header se escribió antes de confiar en `col`. | Corrección = **Plan 3** (documentado en tests) |
| C5 | 715-716 | **`except Exception: print(e)` de nivel superior** traga todo el flujo, no envía alerta a Telegram (justo para los fallos que importan), pierde el traceback y sale con código 0 (un scheduler no detecta el fallo). | `logging.exception`; alerta Telegram del fallo; `sys.exit(1)`. | Corrección = **Plan 3/5** |

### HIGH

| ID | Línea(s) | Hallazgo | Remediación |
|---|---|---|---|
| H1 | 601-608, 680-685 | Idempotencia **no atómica** ante fallo transitorio de Sheets: la lectura de `sent_val` cae a `""` (=“no enviado”) → riesgo de **reenvío duplicado** completo (mensajes + 4 archivos, irreversible). El `update_cell` de marca también solo hace `print` si falla. | No tratar error de lectura como "no enviado"; reintento con backoff en la escritura; alertar si no se pudo persistir la marca. |
| H2 | 672-677 | **Reporte falso:** `tienda` se añade a `enviados_pedidos/catalogo` **antes** de revisar `error_envio`, así que un envío fallido aparece a la vez como éxito y como error en el resumen de Telegram. | Añadir a los buckets de éxito solo en la rama `error_envio is False`. |
| H3 | 601-604 | **N+1 en Sheets API:** `sheet_pedidos.cell()` por fila dentro del loop → agota cuota de lecturas/min. | Leer `col_values(sent_col)` una vez antes del loop y consultar en memoria. |
| H4 | 73 | `requests.post` a Telegram **sin `timeout`** → puede colgar el script indefinidamente. | `timeout=10`. |
| H5 | 555-755 | `main()` ~200 líneas mezcla auth, lectura de 3 hojas, loop de envío, reporte y cierre. | Extraer `autenticar_sheets`, `procesar_pedidos`, `construir_reporte`, `cerrar_driver`. |
| H6 | 85, 187, 256, 300-328, 368, 456, 618, 715 | ~30 `except Exception` amplios sin log/traceback (control de flujo silencioso). | Excepciones específicas + `logging.exception`. |
| H7 | 10, 557 | `oauth2client` **deprecado** (sin parches desde 2017) y `credentials.json` distinto del que usa `app.py` (`bubbly-subject-…json` / `GOOGLE_CREDENTIALS_JSON`). | Migrar a `google-auth` (ya en `requirements.txt`), unificar credencial con el panel. |
| H8 | 466, 482, 494, 506-515 | Selectores XPath **frágiles** por `data-icon="plus-rounded"` etc. (detalles internos de Meta). Una actualización de UI rompe adjuntos de toda la corrida (y por C2, sin error visible). | Selectores de respaldo por `aria-label`/texto; que el fallo aborte con alerta temprana. |
| H9 | 65, 127, 419, 463-525, 555 | Falta de type hints en funciones públicas (inconsistente con las que sí usan `Optional`). | Anotar `str`, `webdriver.Chrome`, `Optional[str]`, `-> None`. |
| H10 | 425 | `focus_and_place_caret_at_end` devuelve `False` en fallo, pero el llamador lo ignora y hace `send_keys` igual → log de "enviado" con el texto en un elemento sin foco. | Comprobar el retorno; reintentar/tratar como fallo (liga con C2). |

### MEDIUM

| ID | Línea(s) | Hallazgo | Remediación |
|---|---|---|---|
| M1 | 304-357 | **PII en debug files:** `debug_invalid_{telefono}_{ts}.png/html` y `debug_timeout_*` guardan teléfono en el nombre y el `page_source` completo (nombre de contacto, mensajes) sin purga y **no** están en `.gitignore`. | (a) `.gitignore` de los patrones [**RESUELTO en T1.3**]; (b) hashear el teléfono; (c) subcarpeta `debug/` con purga >7 días. |
| M2 | 66-79, 704-713 | Reportes Telegram con `parse_mode:Markdown` **sin escapar** `tienda`/`telefono` → un nombre con `_ * [` rompe el mensaje (Telegram lo rechaza) y el fallo solo se imprime. | Escapar Markdown o usar `parse_mode=None`. |
| M3 | 39, 42-43, 557 | Rutas absolutas Windows y `credentials.json` relativo al CWD (rompe con otro directorio/scheduler). | `os.path.join(os.path.dirname(__file__), …)` + env vars. |
| M4 | 46-51, 547 | Constantes `PREVIEW_TIMEOUT_VIDEO=120`, `EXTRA_WAIT_VIDEO_SECS` etc. **definidas pero nunca usadas**; el video usa el mismo `sleep(2)` que una imagen → `ENTER` antes de terminar de procesar el video. | Usar los timeouts de video según extensión o eliminar las constantes muertas. |
| M5 | 88-96 | `buscar_telefono` con índice fijo col 18 (S); mover una columna rompe silenciosamente; nombres de tienda duplicados → usa el primero sin aviso. O(n·m). | Ubicar columna por encabezado; alertar duplicados. |
| M6 | 290 | `globals().get('T_CHAT_LOAD', 10)` — indirección innecesaria. | Acceso directo a `T_CHAT_LOAD`. |
| M7 | 590, 650, 671, 620 | Magic numbers (`sleep(10)`, `sleep(60)`) y estados repetidos como literales. | Constantes nombradas / `Enum` de estados. |
| M8 | todo el archivo | Solo `print()`, sin `logging` con niveles ni persistencia → difícil diagnóstico desatendido. | Migrar a `logging`. |
| M9 | mayoría de funciones | Faltan docstrings (solo 4 los tienen). | Docstrings breves consistentes. |
| M10 | 434-435 | Selección de fallback por substring del mensaje de excepción de Selenium (frágil ante versiones). | Excepciones específicas o comentario + test de regresión. |
| M11 | 691-716 | Los fallos que escapan del loop no envían resumen a Telegram (el envío está dentro del `try`). | Enviar alerta Telegram desde el `except` externo. |

### LOW

| ID | Línea(s) | Hallazgo | Remediación |
|---|---|---|---|
| L1 | 93-95 vs 623-625 | Duplicación de la normalización de prefijo `+` (DRY). | Eliminar el bloque de `main`. |
| L2 | 81-86 vs 616 | `fecha_es_hoy` definida pero **no usada**; `main` reimplementa el chequeo inline (riesgo de divergencia). | Usar `fecha_es_hoy` o borrar la función. |
| L3 | 57 | `.quicktime` no es extensión real (el MIME es `video/quicktime`; la extensión es `.mov`). | Quitar `.quicktime`. |
| L4 | 40 | `IMAGENES` mezcla imagen, video y PDFs bajo un nombre engañoso. | Renombrar a `ARCHIVOS_A_ENVIAR`. |
| L5 | 284 | Teléfono no validado antes de construir la URL `send?phone=` (un `&`/`#` en la hoja altera los query params). | Validar `^\d{7,15}$` / `urllib.parse.quote`. |
| L6 | 606-688 | PII (teléfono/nombre) en `print()` de consola sin enmascarar. | Enmascarar (últimos 4 dígitos), como `enmascarar()` en BruceWhatsapp. |
| L7 | 25-28 | `pyperclip=None` silencioso alimenta el fallback roto de C2. | Log explícito si falta. |
| L8 | 556 | Scope `drive` completo (más amplio de lo necesario para 2 hojas). | Reducir a `drive.file`/`drive.readonly`. |

**Nota de verificación:** `22.PY` estaba **untracked** (no commiteado) al iniciar el plan; el token de las líneas 62-63 ya existe en el historial de otros archivos del repo → C1 confirma el pendiente de rotación del owner. `.gitignore` cubre `*.json` global (protege `credentials.json`) pero **no** protegía el token embebido en `.py` ni los debug files.

---

## 3. Matriz de portabilidad a Railway (T1.5)

> **Insumo del Plan 5** (no decide nada; la decisión de transporte es gate del owner T5.1). Railway ejecuta contenedores Linux headless (nixpacks + gunicorn), sin GUI, sin sesión de navegador persistente y con FS efímero.

| Componente de `envio_catalogo.py` | ¿Corre en Railway? | Bloqueo | Alternativa |
|---|---|---|---|
| Perfil Chrome local con sesión de WhatsApp Web (`FALLBACK_PROFILE_DIR`, L42) | ❌ **NO** | Requiere escaneo de QR interactivo y estado persistente; el FS de Railway es efímero (se pierde en cada deploy) → habría que re-escanear QR en cada arranque, imposible sin pantalla | **WhatsApp Business API** (transporte A, recomendado) · worker local que conserva el perfil (B) · Selenium headless + volumen persistente + QR remoto (C, frágil) |
| Binario Chrome fijo `C:/Program Files/...chrome.exe` (L43) | ❌ NO | Ruta Windows inexistente en Linux | Instalar `chromium` vía nixpacks y detectar binario, **solo** si se elige transporte C |
| `ChromeDriverManager().install()` (L144) | ⚠️ Parcial | Descarga driver en runtime (lento, puede fallar sin red saliente permitida) | Fijar versión de driver en la imagen |
| Archivos locales de media `C:/Users/PC 1/Files mensajes` (L39-40) | ❌ NO | Rutas Windows; FS efímero | Subir los 4 archivos al repo (`assets/`) o a Drive y resolver por env `MEDIA_DIR` |
| Credenciales Google (`credentials.json`, `oauth2client`, L10/557) | ⚠️ Parcial | Railway usa `GOOGLE_CREDENTIALS_JSON` (env) + `google-auth`; el script usa archivo + `oauth2client` | Unificar con `app.py`: `google-auth` + `GOOGLE_CREDENTIALS_JSON` (ver H7) |
| Lectura/escritura de Google Sheets (gspread) | ✅ SÍ | — | Ya funciona en el panel; reusar `get_gs_client()` de `app.py` |
| Reporte por Telegram (`requests` → api.telegram.org) | ✅ SÍ (tras T1.3) | Token ya en env | Añadir `timeout` (H4) |
| Rutas absolutas Windows en general | ❌ NO | No portables | Externalizar a env vars con default (M3) |

**Conclusión para el Plan 5:** el núcleo de datos (Sheets + Telegram) es 100% portable; el **transporte de WhatsApp Web vía Selenium+perfil Chrome NO es portable a Railway**. La operación 100% Railway exige cambiar de transporte (gate T5.1: A/B/C). El resto del script (filtros, resolución de media, marcado ENVIADO_WA) es lógica pura ya cubierta por el baseline de tests.

---

## 4. Sanitización aplicada (T1.3)

| Acción | Detalle | Verificación |
|---|---|---|
| Token/chat Telegram → env | `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` = `os.environ.get(...)`; `enviar_reporte_telegram` omite el envío con mensaje explícito si faltan (no crashea la corrida de WhatsApp) | `grep AAGZC4Lb…[REDACTADO]` en el working tree = **0 resultados** |
| Token fallback en `app.py:3560` | Se eliminó el default hardcodeado `os.environ.get('TELEGRAM_TOKEN', '<token>')` → ahora `os.environ.get('TELEGRAM_TOKEN')` con guard temprano | mismo grep = 0 |
| Rename | `22.PY` → `envio_catalogo.py` (importable; `22.PY` empieza con dígito) | `git status`: `envio_catalogo.py` untracked, `22.PY` desaparecido |
| `.gitignore` | Añadidos `debug_invalid_*`, `debug_timeout_*`, `adjuntar_fail.png` (PII de clientes en disco, hallazgo M1) | — |
| Dependencias runtime | `requirements-dev.txt` nuevo con pytest + selenium/webdriver-manager/pyperclip/oauth2client (hallazgo C3) | — |

**Pendiente del owner (no automatizable):** rotar el token `8404009072` en BotFather (existe en ~14 copias del historial git de varios proyectos) y cargar `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` en Railway. → **Gate Plan 5 T5.3.**

---

## 5. Baseline de tests (T1.4)

- Suite: `tests/test_envio_catalogo.py` + `tests/conftest.py` (stubs de Selenium/webdriver_manager/pyperclip/oauth2client en `sys.modules`).
- **`python -m pytest tests/ -q` → 33 passed.** Es el **baseline oficial** del proyecto desde este plan; ningún plan mergea con la suite en rojo.
- Cubre las 6 funciones puras: `fecha_es_hoy`, `buscar_telefono`, `obtener_mensajes`, `resolve_media_path`, `tipo_archivo`, `ensure_sent_column`.
- Bugs de la auditoría caracterizados (no corregidos): C4 (`ensure_sent_column` cae a col=1) y el salto de la primera fila en `buscar_telefono` — marcados con `# BUG conocido:` y ligados a este informe.
