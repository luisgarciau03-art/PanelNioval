# Plan 4 — Captura de correo en conclusión "Correo" → columna T de LISTA DE CONTACTOS

**Fecha:** 2026-08-13 · **Proyecto:** `C:\Users\PC 1\PanelNioval` · **Rama:** `plan4/captura-correo` · **Depende de:** Plan 2 (matriz de flujo). Independiente de Plan 3 (puede ejecutarse en paralelo tras Plan 2).

## 1. Objetivo, alcance y criterios de éxito

**Objetivo:** cuando el operador cierra una llamada con **"📧 Correo"**, abrir un HTML (modal) para capturar el correo del cliente y guardarlo en su **columna correspondiente (celda de la columna T) de la hoja `LISTA DE CONTACTOS`** — spreadsheet `1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4`, gid `823047163` (URL dada por el owner). El resto del guardado actual (conclusión "Correo" en col J de `Respuestas de formulario 1`) se conserva intacto.

**Contexto para sesión fría:**
- Botón: `FORMULARIO_HTML` en app.py, ≈línea 3177: `<button ... onclick="resp7('Correo')">📧 Correo</button>`; `resp7(v)` asigna `O.r7` y llama `guardar()` directo.
- El contacto activo `O.contacto` trae `_row` (fila 1-indexada en `LISTA DE CONTACTOS`) — es la fila donde hay que escribir el correo.
- OJO — ambigüedad a resolver en T4.1: en `Respuestas de formulario 1` la col T ya se usa para `r0` (línea ≈2864 de app.py). La instrucción del owner dice claramente **HOJA LISTA DE CONTACTOS**, columna T. Antes de implementar hay que leer los headers reales de `LISTA DE CONTACTOS` y confirmar qué hay hoy en col T (¿header "CORREO"? ¿vacía? ¿ocupada por otro dato?). Si col T está ocupada por otro dato → BLOQUEAR y preguntar al owner, no pisar datos.

**Criterios de éxito medibles:**
- [ ] Pulsar "Correo" abre modal de captura ANTES de guardar; el operador escribe el correo (o "sin correo" explícito) y el flujo continúa como hoy.
- [ ] El correo queda en la celda `T{_row}` de `LISTA DE CONTACTOS` (verificado leyendo la celda tras el guardado en el test de integración).
- [ ] Validación doble (cliente + servidor) del formato de correo; correos inválidos rechazados con mensaje claro y sin escritura en hoja.
- [ ] El guardado actual en `Respuestas de formulario 1` (col J = "Correo", S, T=r0) NO cambia — verificado por los tests de caracterización del Plan 2 sin modificar.
- [ ] Baseline completo verde: `python -m pytest tests/ -q` (suites Planes 1-2 + ≥8 tests nuevos).

## 2. Tareas (formato blueprint)

### T4.1 — Verificación de la hoja real + contrato (sin dependencias) — GATE DE DATOS
**Brief autocontenido:** con las credenciales del proyecto (env `GOOGLE_CREDENTIALS_JSON` o el .json local), script de solo lectura `tools/inspeccionar_contactos.py` que imprime: headers completos de `LISTA DE CONTACTOS`, contenido de la columna T (header + 5 muestras + % de celdas ocupadas). Decisión: si T está vacía o ya es la columna de correo → proceder; si está ocupada por otro dato → BLOQUEADA, preguntar al owner (mostrar evidencia). Documentar el contrato del endpoint `POST /api/formulario/correo` `{row:int, correo:str}` → escribe `T{row}` + respuesta `{ok, error?}`.
**Salida:** nota de verificación en el doc del plan + contrato.

### T4.2 — Backend: endpoint de guardado de correo (depende de T4.1) — TDD
**Brief:** RED: tests con MagicMock de gspread: correo válido → `update_cell(row, 20, correo)` (col T = 20); correo inválido (sin @, dominio malo, espacios, >254 chars, inyección `=HYPERLINK(...)` — prefijar `'` si empieza con `=`,`+`,`-`,`@` para evitar formula injection en Sheets) → 400 sin escritura; row inválido/faltante → 400. GREEN: implementar en app.py junto a los endpoints del formulario, con invalidación del cache `contactos`.
**Gate:** pytest verde; security-reviewer (input de usuario + formula injection + email = dato personal, no loggear completo).

### T4.3 — Frontend: modal de captura (depende de T4.2)
**Brief:** modificar `resp7('Correo')` para abrir modal (mismo lenguaje visual del formulario: card, .btn, colores --blue/--green) con: input type=email autofocus, botón "Guardar correo" (deshabilitado hasta validez), botón "Continuar sin correo" (registra la conclusión sin escribir T), manejo de error del servidor (mensaje inline, no alert). Tras guardar el correo con éxito → continúa `guardar()` normal. Teclado: Enter envía, Esc = sin correo. Escapar datos inyectados al DOM.
**Gate:** review visual (checklist de estados hover/focus/error/disabled) + code-reviewer del JS.

### T4.4 — Integración E2E + cierre (depende de T4.3)
**Brief:** con hoja de staging (o mock del cliente gspread en servidor de prueba): flujo completo APROBADO→…→Correo→modal→guardar → assert celda T escrita y respuesta guardada; ruta de correo inválido; ruta "sin correo". Recorrido Playwright con screenshots. PR + PROGRESO + handoff.

## 3. Tabla de asignación de herramientas (por etapa)

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T4.1 | claude-mem:mem-search | skill | claude-mem | Contexto Plan 2 (matriz) + memoria "verificar col T" de la tanda de llamadas previa |
| A | T4.1 | Explore | agente | built-in | Confirmar usos actuales de col T en el codebase |
| B | T4.1 | api-designer | agente | catalogo-agentes | Contrato del endpoint con errores explícitos |
| B | T4.1 | superpowers:brainstorming | skill | superpowers | Resolver la ambigüedad col T con el owner antes de diseñar |
| C | T4.2 | tdd-guide + superpowers:test-driven-development | agente+skill | catalogo-agentes + superpowers | Endpoint escrito test-first |
| C | T4.2 | python-testing | skill | ECC | Mocks gspread + parametrización de correos inválidos |
| C | T4.3 | impeccable | skill | community | Modal con estados diseñados, coherente con la UI existente |
| C | T4.3 | frontend-patterns | skill | ECC | Patrón de validación en cliente + manejo de error inline |
| D | T4.2 | security-reviewer | agente | catalogo-agentes | Input usuario + formula injection en Sheets + dato personal |
| D | T4.2-T4.3 | code-reviewer + python-reviewer | agentes | catalogo-agentes | Review por cambio |
| D | T4.4 | webapp-testing | skill | skills-local (Anthropic) | Recorrido Playwright del modal |
| D | T4.4 | superpowers:verification-before-completion | skill | superpowers | Gate final con evidencia |
| E | T4.4 | pr / github-ops | skill | ECC | PR convencional |
| E | T4.4 | claude-mem:handoff | skill | claude-mem | Registro del contrato para futuras tandas |

**Fuentes usadas: 7** (claude-mem, built-in, catalogo-agentes, superpowers, ECC, community, skills-local/Anthropic). **claude-ads: no aplica** — capturar un correo en una llamada no es trabajo de campañas; si el owner luego quiere una secuencia de email marketing con esos correos, eso sería un plan nuevo donde claude-ads/marketing-campaign SÍ entraría (ver Mejoras propuestas en el índice).

## 4. Gates de verificación por tarea

| Tarea | Gate |
|---|---|
| T4.1 | Evidencia impresa de headers reales; si col T ocupada → BLOQUEADA con pregunta al owner |
| T4.2 | TDD demostrado; security-reviewer verde; formula injection cubierta por test |
| T4.3 | Checklist visual de estados + code-reviewer sin CRITICAL/HIGH |
| T4.4 | E2E 3 rutas con screenshots; pytest total verde; verification-before-completion |

## 5. Tabla PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T4.1 | Verificación hoja real + contrato | PENDIENTE | | |
| T4.2 | Endpoint guardado correo (TDD) | PENDIENTE | | |
| T4.3 | Modal de captura | PENDIENTE | | |
| T4.4 | E2E + PR + cierre | PENDIENTE | | |

## 6. Riesgos y rollback

| Riesgo | Mitigación | Rollback |
|---|---|---|
| Col T de LISTA DE CONTACTOS ya contiene otro dato | Gate T4.1 bloquea antes de escribir; nunca pisar datos sin confirmación | N/A (bloqueo preventivo) |
| Escribir en fila equivocada (desfase _row) | Test de integración lee la celda tras escribir y compara tienda de la misma fila | Corrección manual de la celda + fix |
| Formula injection vía correo malicioso | Sanitización con prefijo `'` + test dedicado | Limpiar celdas afectadas |
| Modal interrumpe el ritmo del operador | Atajos de teclado + botón "sin correo" en 1 clic | Feature flag `CAPTURA_CORREO=0` restaura resp7 directo |
