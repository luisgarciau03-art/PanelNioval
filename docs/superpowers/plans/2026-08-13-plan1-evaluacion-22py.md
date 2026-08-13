# Plan 1 — Evaluación integral del script `22.PY` (envío de catálogo por WhatsApp Web)

**Fecha:** 2026-08-13 · **Proyecto:** `C:\Users\PC 1\PanelNioval` · **Rama:** `plan1/evaluacion-22py`

## 1. Objetivo, alcance y criterios de éxito

**Objetivo:** auditar `22.PY` en 4 dimensiones (funcional, seguridad, robustez, portabilidad a Railway), dejarlo versionado de forma segura (hoy está SIN commitear y con un token de Telegram hardcodeado), y crear la primera suite de tests del proyecto (tests de caracterización), que se convierte en el baseline oficial.

**Alcance:** solo análisis, sanitización de secretos y tests de caracterización. NO se cambia comportamiento del script (eso es Plan 3/5).

**Contexto para sesión fría — qué es `22.PY`:** script Selenium que:
1. Lee `Respuestas de formulario 1` (spreadsheet `1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg`) y filtra filas con fecha de HOY y col J (índice 9) ∈ {`pedido`, `revisara el catalogo`}.
2. Busca el teléfono de la tienda en worksheet `BD CONTACTOS` (spreadsheet `1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk`), columna índice 18 (S).
3. Abre WhatsApp Web con perfil Chrome local (`C:/Users/PC 1/ChromeSeleniumProfile`), envía mensajes de la worksheet `Mensajes` + 4 archivos locales (`C:/Users/PC 1/Files mensajes`: IMG1.jpg, Video1.mp4, CATÁLOGO NIOVAL.pdf, LPNIOVAL.pdf).
4. Detecta popup "número no válido", marca `ENVIADO_WA` con timestamp en la hoja de pedidos, y reporta por Telegram (token hardcodeado `8404009072:...`, chat `5838212022`).

**Criterios de éxito medibles:**
- [ ] Informe `docs/auditoria/2026-08-13-auditoria-22py.md` con ≥15 hallazgos clasificados CRITICAL/HIGH/MEDIUM/LOW, cada uno con línea exacta y remediación propuesta.
- [ ] 0 secretos hardcodeados en el archivo versionado (token Telegram y chat_id movidos a variables de entorno; verificado por security-reviewer).
- [ ] `22.PY` renombrado a `envio_catalogo.py` (importable; `22.PY` no es un nombre de módulo válido) y commiteado.
- [ ] Suite `tests/` con ≥12 tests de caracterización verdes (`python -m pytest tests/ -q`) cubriendo las funciones puras: `fecha_es_hoy`, `buscar_telefono`, `obtener_mensajes`, `resolve_media_path`, `tipo_archivo`, `ensure_sent_column` (con mocks de gspread).
- [ ] Matriz de compatibilidad Railway (qué corre / qué no y por qué) entregada como insumo del Plan 5.

## 2. Tareas (formato blueprint — cada una ejecutable en frío)

### T1.1 — Contexto e inventario (sin dependencias)
**Brief autocontenido:** en `C:\Users\PC 1\PanelNioval`, recuperar contexto previo con claude-mem (buscar "PanelNioval", "22.py", "llamadas", "Telegram 8404009072"). Leer completo `22.PY` y las secciones de `app.py` que comparten hojas (SHEET_IDS líneas 28-45, `guardar_respuesta_formulario` líneas 2815-2875). Producir tabla de dependencias externas: hojas de Google (ID + worksheet + columnas usadas), archivos locales, binarios (Chrome), red (web.whatsapp.com, api.telegram.org).
**Salida:** sección "Inventario de dependencias" del informe.

### T1.2 — Auditoría estática multidimensión (depende de T1.1)
**Brief:** lanzar en paralelo 4 revisores sobre `22.PY`: python-reviewer (idiomática/PEP8/manejo de errores), security-reviewer (secretos, inyección, datos personales de clientes en logs/screenshots de debug), silent-failure-hunter (los ~30 `except Exception: pass` del script), code-reviewer (calidad general, funciones >50 líneas como `main()` de ~200 líneas). Consolidar hallazgos deduplicados con severidad. Hallazgos mínimos a confirmar: token Telegram hardcodeado (líneas 62-63); `oauth2client` deprecado (app.py ya usa `google-auth`); `selenium`/`webdriver-manager`/`pyperclip`/`oauth2client` NO están en `requirements.txt`; lecturas celda-a-celda `sheet_pedidos.cell()` dentro del loop (cuota API de Sheets); `sleep(60)` fijo por contacto; screenshots de debug con datos de clientes quedan en disco sin limpieza.
**Salida:** informe con tabla de hallazgos.

### T1.3 — Sanitización de secretos y versionado seguro (depende de T1.2) — GATE DE SEGURIDAD
**Brief:** ANTES de cualquier commit: mover `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` a variables de entorno (`os.environ.get('TELEGRAM_TOKEN')`, fallo explícito si falta), renombrar `22.PY` → `envio_catalogo.py` (git mv no aplica: el archivo está untracked; simplemente renombrar), verificar que `.gitignore` sigue cubriendo `*.json` (credentials). NUNCA commitear el token: si ya se pegó en algún archivo versionado, limpiarlo antes. Nota para el owner (ya registrada en memoria): el token `8404009072` existe en ~14 copias en otros proyectos y DEBE rotarse — este plan no puede rotarlo, solo dejar de propagarlo.
**Gate:** security-reviewer confirma 0 secretos en el diff antes del commit.

### T1.4 — Tests de caracterización = baseline del proyecto (depende de T1.3, TDD invertido: caracterizar, no diseñar)
**Brief:** crear `tests/test_envio_catalogo.py` + `tests/conftest.py`. El proyecto HOY no tiene tests: esta suite es el primer baseline. Caracterizar comportamiento actual (incluidos bugs: documentarlos con `# BUG conocido:` sin corregirlos): `fecha_es_hoy` (formatos dd/mm/YYYY, vacío, basura), `buscar_telefono` (match case-insensitive, fila corta, prefijo '+'), `resolve_media_path` (absoluto/relativo/sin extensión, tmp_path), `tipo_archivo` (media/doc/desconocido), `obtener_mensajes` (salta 2 primeras filas, filtra vacíos), `ensure_sent_column` (existente/creación, con MagicMock de gspread). Selenium NO se testea (se mockea el import si hace falta). Agregar `pytest` a un `requirements-dev.txt` nuevo.
**Gate:** `python -m pytest tests/ -q` verde; pr-test-analyzer valida que los tests ejercen comportamiento real y no triviales.

### T1.5 — Matriz de portabilidad Railway + cierre (depende de T1.2)
**Brief:** producir tabla: componente → ¿corre en Railway? → bloqueo → alternativa (p.ej. "perfil Chrome con sesión WhatsApp Web → NO → requiere QR y estado persistente → WhatsApp Business API o worker local"). Es EL insumo de la decisión del Plan 5, no decide nada. Cerrar: PR `plan1/evaluacion-22py` → main con informe + tests + script sanitizado; actualizar tabla PROGRESO; guardar contexto con claude-mem.

## 3. Tabla de asignación de herramientas (por etapa)

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T1.1 | claude-mem:mem-search | skill | claude-mem | Proyecto con historial (14 commits + memoria de tandas previas); obligatorio en etapa A |
| A | T1.1 | Explore | agente | built-in | Barrido de app.py (3,5k líneas) sin quemar contexto |
| A | T1.1 | code-explorer | agente | catalogo-agentes | Trazar dependencias 22.PY ↔ hojas ↔ app.py |
| B | T1.2 | superpowers:writing-plans | skill | superpowers | Descomponer la auditoría en pasos verificables |
| C | T1.3 | python-pro | agente | catalogo-agentes | Sanitización idiomática (env vars con fallo explícito) |
| C | T1.4 | tdd-guide + superpowers:test-driven-development | agente+skill | catalogo-agentes + superpowers | Suite de caracterización disciplinada |
| C | T1.4 | python-testing | skill | ECC | Patrones pytest: fixtures, mocks de gspread, tmp_path |
| D | T1.2 | python-reviewer, security-reviewer, silent-failure-hunter, code-reviewer (en paralelo) | agentes | catalogo-agentes | 4 lentes independientes = auditoría multidimensión |
| D | T1.4 | pr-test-analyzer | agente | catalogo-agentes | Valida cobertura conductual de la nueva suite |
| D | T1.5 | superpowers:verification-before-completion | skill | superpowers | Gate final: nada se declara hecho sin correr pytest |
| D | T1.5 | production-audit | skill | community | Matriz "¿qué se rompe en prod/Railway?" con evidencia local |
| E | T1.5 | pr / github-ops | skill | ECC | PR convencional a main |
| E | T1.5 | claude-mem:standup / handoff | skill | claude-mem | Contexto persistente para Plan 2 |
| E | T1.5 | doc-updater | agente | catalogo-agentes | Informe de auditoría bien estructurado |

**Fuentes usadas: 6** (claude-mem, built-in, catalogo-agentes, superpowers, ECC, community). **claude-ads: no aplica** — este plan es auditoría de código sin trabajo de campañas, copy ni creatividades; ninguna herramienta ads-* audita scripts Python.

## 4. Gates de verificación por tarea

| Tarea | Gate |
|---|---|
| T1.1 | Inventario cruzado contra el código real (cada ID de hoja citado con línea) |
| T1.2 | 4 reviewers ejecutados; hallazgos con severidad; 0 CRITICAL sin remediación propuesta |
| T1.3 | security-reviewer en verde sobre el diff; grep de token en el árbol versionado = 0 resultados |
| T1.4 | `python -m pytest tests/ -q` verde (≥12 tests); pr-test-analyzer sin hallazgos HIGH |
| T1.5 | superpowers:verification-before-completion + PR con CI/checks locales en verde |

## 5. Tabla PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T1.1 | Contexto e inventario | HECHO | Inventario §1 en `docs/auditoria/2026-08-13-auditoria-22py.md` (hojas/creds/archivos/deps cruzados con `app.py`) | 2026-08-13 |
| T1.2 | Auditoría estática multidimensión | HECHO | 4 reviewers (python/security/silent-failure/code) → 34 hallazgos (5C·10H·11M·8L), §2; 0 CRITICAL sin remediación | 2026-08-13 |
| T1.3 | Sanitización secretos + versionado | HECHO | Token→env en `envio_catalogo.py` + fix fallback en `app.py:3560`; rename `22.PY`→`envio_catalogo.py`; `.gitignore` de debug; `grep` token en árbol = 0 | 2026-08-13 |
| T1.4 | Tests caracterización (baseline) | HECHO | `tests/test_envio_catalogo.py` + `conftest.py` → **33 passed**; pr-test-analyzer sin HIGH | 2026-08-13 |
| T1.5 | Matriz Railway + PR + cierre | HECHO | Matriz §3 + `requirements-dev.txt` + `CLAUDE.md` (M5); PR a main | 2026-08-13 |

## 6. Riesgos y rollback

| Riesgo | Mitigación | Rollback |
|---|---|---|
| Commitear el token Telegram por accidente | Gate T1.3 obligatorio antes de cualquier `git add` | Si se pushea: rotar token YA (owner) + reescribir historia antes de que nadie clone |
| Tests de caracterización "congelan" bugs | Marcar cada bug con `# BUG conocido:` y listarlo en el informe | Los tests se ajustan en el plan que corrija el bug |
| Renombrar 22.PY rompe flujos manuales del owner | Documentar el rename en el informe y en el PR; dejar nota en README | `git revert` del commit de rename |
| El script está en uso productivo diario | Este plan NO cambia comportamiento (solo secretos→env; el owner define las vars antes de la próxima corrida) | Restaurar valores en un `.env` local (no versionado) |
