# Plan 2 — Evaluación del formulario de llamadas (únicamente ese módulo)

**Fecha:** 2026-08-13 · **Proyecto:** `C:\Users\PC 1\PanelNioval` · **Rama:** `plan2/evaluacion-formulario` · **Depende de:** Plan 1 (usa la suite `tests/` como baseline)

## 1. Objetivo, alcance y criterios de éxito

**Objetivo:** ubicar, mapear y auditar exclusivamente el formulario de llamadas del panel: flujo de preguntas, endpoints, escritura en Google Sheets y su HTML/JS embebido. Producir la matriz de flujo completa (es el contrato sobre el que se integran Plan 3 y Plan 4) y tests de caracterización del guardado.

**Alcance:** SOLO el formulario. Fuera de alcance: dashboard, importador, Prospectos Bruce, seguimiento.

**Contexto para sesión fría — dónde vive el formulario (todo en `app.py`):**
- Ruta UI: `/formulario` (≈línea 4011) → sirve `FORMULARIO_HTML` (bloque r-string ≈líneas 2990-3404: HTML+CSS+JS embebido).
- API: `GET /api/formulario/siguiente` (≈2971) → `get_contacto_pendiente(skip)` (≈2761): primer contacto de `LISTA DE CONTACTOS` (spreadsheet `1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4`, gid 823047163) con columna `RESPUESTA` (fallback col F) vacía.
- `POST /api/formulario/guardar` (≈2980) → `guardar_respuesta_formulario(datos)` (≈2815): append a `Respuestas de formulario 1` — A=fecha, B=tienda, C-E=r1-r3, G-I=r4-r6, J=conclusión derivada (mapa Colgo/Enc No Disponible/BUZON/TELEFONO INCORRECTO/No apto/No compatible/Marca Unica/r7), S=resultado, T=r0.
- Flujo JS: `decidir(APROBADO|NEGADO|NO COMPATIBLE|MARCA UNICA)` → `resp0..resp6` → `resp7(Pedido|Revisara el Catalogo|Correo|Avance|Continuacion|Nulo)` + atajos `colgo()`/`encNoDisp()` → `guardar()`.
- `marcar_contacto_procesado` (≈2794): posible código muerto — commit `e84c1a0` eliminó la escritura de "Llamado" al guardar; verificar si algo lo llama aún.

**Criterios de éxito medibles:**
- [ ] Matriz de flujo publicada en `docs/analisis/2026-08-13-matriz-formulario.md`: TODAS las rutas botón→estado→columnas escritas (≥14 rutas: 4 decisiones × atajos × 6 conclusiones), verificada contra el código línea a línea.
- [ ] Informe de auditoría con ≥10 hallazgos clasificados; como mínimo debe pronunciarse (confirmar o descartar con evidencia) sobre: (a) condición de carrera en `ultima_fila = len(col_b)+1` con 2 operadores simultáneos; (b) XSS en `renderContacto` (datos de hoja inyectados vía innerHTML sin escape); (c) endpoints sin autenticación escribiendo en hojas de negocio; (d) validación server-side inexistente del payload de `guardar`; (e) `marcar_contacto_procesado` muerto; (f) contactos saltados con `skip` que reaparecen tras guardar (skip se resetea); (g) manejo de errores que devuelve `{'ok': False}` con detalle al cliente.
- [ ] ≥10 tests de caracterización nuevos verdes (mapa col J completo + `get_contacto_pendiente` con mocks) sin romper el baseline del Plan 1.
- [ ] Veredicto E2E: recorrido manual/automatizado del formulario en local con captura de cada paso.

## 2. Tareas (formato blueprint)

### T2.1 — Recuperar contexto y mapear el módulo (sin dependencias)
**Brief autocontenido:** con claude-mem buscar decisiones previas sobre el formulario (commits `a3ff193`, `f6bd264`, `f208a3f`, `e84c1a0`, `14b47c5` tocan el formulario — leer sus diffs con `git show`). Trazar con el agente code-explorer el ciclo completo request→sheet. Entregar diagrama de secuencia (mermaid) UI→API→gspread.

### T2.2 — Matriz de flujo exhaustiva (depende de T2.1)
**Brief:** construir tabla: `decisión inicial × respuesta r0 × conclusión r7 → celdas escritas (A..T) + valor col J + qué NO se escribe`. Incluir atajos colgo/encNoDisp en cada pregunta. Validar cada fila contra `guardar_respuesta_formulario` (≈2838-2864). Esta matriz es el contrato de integración para Plan 3 (botón "Revisará el Catálogo") y Plan 4 (botón "Correo").

### T2.3 — Auditoría de calidad y seguridad del módulo (depende de T2.2)
**Brief:** en paralelo: code-reviewer + python-reviewer sobre las funciones backend; security-reviewer sobre endpoints (sin auth, sin validación, XSS del HTML embebido, datos personales de tiendas/teléfonos en logs `print`); silent-failure-hunter sobre los `except Exception` que devuelven None/False y ocultan fallos de cuota de Google. Clasificar CRITICAL/HIGH/MEDIUM/LOW según docs/code-review estándar.

### T2.4 — Tests de caracterización del guardado (depende de T2.2)
**Brief:** `tests/test_formulario.py`: parametrizar el mapa col J completo (Colgo, Enc No Disponible por r7 y por resultado, Buzon, Telefono Incorrecto, NEGADO→No apto, NO COMPATIBLE→No compatible, MARCA UNICA→Marca Unica, r7 passthrough, vacío); `get_contacto_pendiente` (RESPUESTA por nombre, fallback col F, skip, sin pendientes → None); `guardar_respuesta_formulario` verifica batch_update con rangos exactos (S y T incluidos) usando MagicMock de gspread. NO corregir bugs: caracterizar y anotar `# BUG conocido:`.
**Gate:** `python -m pytest tests/ -q` verde (baseline Plan 1 + nuevos).

### T2.5 — Verificación E2E ligera + cierre (depende de T2.3, T2.4)
**Brief:** levantar `python app.py` local (requiere `GOOGLE_CREDENTIALS_JSON` o el .json local — si no hay credenciales, mockear `get_gs_client` con una fixture de servidor de prueba) y recorrer con Playwright el flujo feliz APROBADO→…→Pedido y 2 rutas cortas (NEGADO directo, Colgó en p2), capturando screenshots. Cerrar con PR, tabla PROGRESO, informe final y handoff de memoria.

## 3. Tabla de asignación de herramientas (por etapa)

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T2.1 | claude-mem:mem-search | skill | claude-mem | Historial del formulario en 5+ commits y memoria de sesiones previas |
| A | T2.1 | code-explorer | agente | catalogo-agentes | Trazar ejecución UI→API→gspread de una feature existente |
| A | T2.1 | Explore | agente | built-in | Localizar todos los usos de `formulario` en app.py sin quemar contexto |
| B | T2.2 | superpowers:writing-plans | skill | superpowers | Formalizar la matriz como contrato verificable |
| B | T2.2 | api-designer | agente | catalogo-agentes | Evaluar el contrato actual de los 2 endpoints (insumo Plan 3/4) |
| C | T2.4 | tdd-guide + superpowers:test-driven-development | agente+skill | catalogo-agentes + superpowers | Caracterización disciplinada del mapa col J |
| C | T2.4 | python-testing | skill | ECC | Parametrización pytest + mocks gspread |
| D | T2.3 | code-reviewer, python-reviewer, security-reviewer, silent-failure-hunter | agentes | catalogo-agentes | 4 lentes paralelos sobre el módulo |
| D | T2.5 | webapp-testing / browser-qa | skill | skills-local (Anthropic) / ECC | Recorrido Playwright real del formulario local |
| D | T2.5 | superpowers:verification-before-completion | skill | superpowers | Gate final con evidencia de pytest + screenshots |
| E | T2.5 | pr / github-ops | skill | ECC | PR convencional |
| E | T2.5 | claude-mem:handoff | skill | claude-mem | La matriz de flujo queda disponible para Plan 3/4 |
| E | T2.5 | doc-updater | agente | catalogo-agentes | Informe y matriz bien redactados |

**Fuentes usadas: 6** (claude-mem, catalogo-agentes, built-in, superpowers, ECC, skills-local/Anthropic — más que el mínimo de 5). **claude-ads: no aplica** — el formulario es una herramienta interna de telemarketing/captura; no hay campañas pagadas, tracking de ads ni creatividades que auditar. **community: no aplica en este plan** — production-audit/blueprint ya cubren los planes 1 y 3; para un módulo de ~600 líneas la auditoría con los 4 reviewers de catalogo-agentes es suficiente y añadir council/blueprint sería ceremonia sin decisión que tomar.

## 4. Gates de verificación por tarea

| Tarea | Gate |
|---|---|
| T2.1 | Diagrama validado contra líneas reales de app.py |
| T2.2 | Cada fila de la matriz citada con rango de celdas exacto del código |
| T2.3 | 4 reviewers ejecutados; hallazgos con severidad y línea |
| T2.4 | pytest verde total (baseline + nuevos); pr-test-analyzer sin HIGH |
| T2.5 | Screenshots de 3 rutas E2E + verification-before-completion |

## 5. Tabla PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T2.1 | Contexto y mapeo del módulo | PENDIENTE | | |
| T2.2 | Matriz de flujo exhaustiva | PENDIENTE | | |
| T2.3 | Auditoría calidad + seguridad | PENDIENTE | | |
| T2.4 | Tests caracterización guardado | PENDIENTE | | |
| T2.5 | E2E ligero + PR + cierre | PENDIENTE | | |

## 6. Riesgos y rollback

| Riesgo | Mitigación | Rollback |
|---|---|---|
| E2E contra hojas REALES escribe datos basura | Usar mock de `get_gs_client` o una hoja de staging; NUNCA guardar contra producción en tests | Borrar filas de prueba identificables por timestamp |
| El formulario está en uso diario por el operador | Plan de solo lectura/análisis; ningún cambio de comportamiento | N/A (no hay cambios) |
| La matriz revela ambigüedades que bloquean Plan 3/4 | Escalar como preguntas concretas al owner en el PR, no asumir | N/A |
| Railway auto-deploya `main` | Trabajar solo en rama `plan2/...`; merge únicamente con gates verdes | `git revert` del merge |
