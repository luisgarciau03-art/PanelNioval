# Plan 3 — Integrar el envío de catálogo (`envio_catalogo.py`, ex-22.PY) al final del sistema de llamadas

**Fecha:** 2026-08-13 · **Proyecto:** `C:\Users\PC 1\PanelNioval` · **Rama:** `plan3/integracion-catalogo` · **Depende de:** Plan 1 (script sanitizado + baseline) y Plan 2 (matriz de flujo del formulario)

## 1. Objetivo, alcance y criterios de éxito

**Objetivo:** que al cerrar una llamada con el botón **"📖 Revisará el Catálogo"** (y también **"📦 Pedido"**, que hoy `22.PY` ya trata igual — confirmar con el owner en T3.1) se **active el envío del catálogo** por WhatsApp, y que el sistema de llamadas **valide el resultado**: `ENVIADO` / `FALLÓ` / `NÚMERO INVÁLIDO (no le llegó)`. Si no le llegó, el panel muestra un **HTML para corregir el número** y reintentar el envío.

**Alcance:** cola de envíos + estados + endpoints + UI de estado y corrección de número + refactor de `envio_catalogo.py` a worker procesador de cola. El TRANSPORTE sigue siendo el actual (Selenium/WhatsApp Web ejecutado donde hoy corre); mover el transporte a Railway es Plan 5. La cola se diseña **transport-agnostic** para que Plan 5 solo cambie el "enviador".

**Contexto para sesión fría:**
- El formulario (app.py `FORMULARIO_HTML`, botones `resp7(...)` ≈línea 3175-3180) guarda la conclusión en `Respuestas de formulario 1` col J vía `guardar_respuesta_formulario` (≈2815).
- `envio_catalogo.py` (renombrado en Plan 1) hoy corre MANUAL: barre esa hoja filtrando fecha=hoy + col J ∈ {pedido, revisara el catalogo}, resuelve teléfono en `BD CONTACTOS` col S, envía por WhatsApp Web, marca `ENVIADO_WA`, detecta popup "número no válido" y reporta por Telegram.
- Estados honestos que Selenium/WA Web puede garantizar: `ENVIADO` (mensaje salió del chat), `NUMERO_INVALIDO` (popup detectado = no le llegará al cliente), `FALLO` (chat no cargó / error de envío). La "entrega" real (doble check) NO es detectable de forma fiable — el diseño usa NUMERO_INVALIDO como el caso "no le llegó" que dispara la corrección, y así se comunica al owner.

**Criterios de éxito medibles:**
- [ ] Al pulsar "Revisará el Catálogo" o "Pedido" se crea un registro de envío `PENDIENTE` (verificable en la hoja/estado) sin bloquear el flujo del operador (el formulario pasa al siguiente contacto igual que hoy).
- [ ] El worker procesa pendientes y deja cada registro en `ENVIADO` / `NUMERO_INVALIDO` / `FALLO` con timestamp, visible en el panel.
- [ ] Caso número inválido: el panel muestra el contacto con badge rojo + botón "Corregir número" → modal HTML valida el número (E.164 / 10-13 dígitos), lo actualiza en la hoja de teléfonos y re-encola; el reintento queda trazado.
- [ ] 0 envíos duplicados a la misma tienda por el mismo cierre (idempotencia por fila de respuesta, no por día).
- [ ] Baseline completo verde (`python -m pytest tests/ -q`, suites de Planes 1-2 + ≥15 tests nuevos).
- [ ] Reporte Telegram sigue funcionando (token desde env var).

## 2. Tareas (formato blueprint)

### T3.1 — Diseño de la cola y contrato de estados (sin dependencias de código; requiere docs de Planes 1-2)
**Brief autocontenido:** leer `docs/auditoria/2026-08-13-auditoria-22py.md` y `docs/analisis/2026-08-13-matriz-formulario.md`. Diseñar con blueprint: (a) almacenamiento de la cola — recomendación: worksheet nueva `ENVIOS_CATALOGO` en el spreadsheet de respuestas con columnas `fecha_solicitud, tienda, telefono, fila_respuesta, conclusion, estado (PENDIENTE/EN_PROCESO/ENVIADO/NUMERO_INVALIDO/FALLO), intentos, timestamp_estado, detalle`; (b) contrato de los endpoints `POST /api/catalogo/encolar`, `GET /api/catalogo/envios?estado=`, `POST /api/catalogo/corregir-numero`, `POST /api/catalogo/reintentar`; (c) máquina de estados con transiciones válidas. Decidir con council (2 opciones válidas): ¿el encolado lo hace el backend dentro de `guardar_respuesta_formulario` (menos requests, acoplado) o un endpoint aparte llamado por el JS (desacoplado, 1 request extra)? Preguntar al owner UNA cosa: ¿"Pedido" también envía catálogo (comportamiento actual de 22.PY) o solo "Revisará el Catálogo"?
**Salida:** `docs/superpowers/plans/2026-08-13-plan3-diseno-cola.md` con el contrato aprobado.

### T3.2 — Encolado desde el formulario (depende de T3.1) — TDD
**Brief:** RED: tests de que cerrar con conclusión elegible crea fila `PENDIENTE` en `ENVIOS_CATALOGO` con teléfono resuelto (lookup en `LISTA DE CONTACTOS` col TELÉFONO del contacto activo — el formulario YA tiene el teléfono en `O.contacto`, usarlo en el payload en vez de re-buscar), y de que conclusiones no elegibles NO encolan. GREEN: implementar en app.py. Idempotencia: clave `fila_respuesta` única — reencolar la misma fila no duplica.
**Gate:** pytest verde; code-reviewer + python-reviewer.

### T3.3 — Refactor de `envio_catalogo.py` a worker de cola (depende de T3.1) — TDD
**Brief:** separar el script en: `nucleo_envio.py` (lógica pura testeable: selección de pendientes, transición de estados, armado de reporte) y `transporte_whatsapp_web.py` (Selenium actual, sin cambios de comportamiento, interfaz `enviar(telefono, mensajes, archivos) -> ResultadoEnvio`). El worker: lee `ENVIOS_CATALOGO` PENDIENTE → marca EN_PROCESO → llama transporte → escribe estado final + `ENVIADO_WA` en la fila de respuestas (compatibilidad con el flujo actual) + Telegram. Batch de lecturas gspread (una lectura por corrida, no celda a celda). Los tests de caracterización del Plan 1 se actualizan a la nueva estructura SIN perder casos.
**Gate:** pytest verde; silent-failure-hunter sobre el worker (los except silenciosos del script original NO deben sobrevivir al refactor); security-reviewer (teléfonos = dato personal: no volcarlos completos en logs).

### T3.4 — Panel de estado de envíos + modal corrección de número (depende de T3.2, T3.3) — TDD backend, review visual frontend
**Brief:** en el panel (o en el propio formulario, sección visible tras guardar): lista de envíos del día con badges por estado; para `NUMERO_INVALIDO` y `FALLO`, botón "Corregir número" → modal HTML (mismo estilo del FORMULARIO_HTML: card blanca, botones .btn) con input tel, validación en cliente Y servidor (solo dígitos y `+`, longitud 10-13; rechazo explícito con mensaje claro), escritura del número corregido en la celda de teléfono de `LISTA DE CONTACTOS` (misma fila del contacto) y re-encolado (`intentos+1`). Escapar TODO dato de hoja antes de inyectarlo al DOM (hallazgo XSS del Plan 2 no se replica aquí).
**Gate:** pytest de los 2 endpoints nuevos; security-reviewer (input de usuario + escritura en hoja); recorrido browser-qa del modal.

### T3.5 — [OPCIONAL] Revisión del mensaje de catálogo (independiente; condición: si el owner quiere tocar el copy)
**Brief:** los mensajes que acompañan al catálogo viven en worksheet `Mensajes`. Con copy-writer (claude-ads) proponer 2 variantes del mensaje de acompañamiento (B2B ferretero, tono usted, sin emojis excesivos) para que el owner elija. NO se cambia nada en las hojas sin aprobación del owner.

### T3.6 — Integración E2E + cierre (depende de T3.2-T3.4)
**Brief:** prueba integral en local con hoja de staging (copia de `ENVIOS_CATALOGO`): cerrar llamada → fila PENDIENTE → correr worker con transporte FAKE (mock que simula ok/inválido/fallo) → estados correctos → corregir número → reintento OK. Prueba real con WhatsApp: UNA corrida con 1-2 números del owner (gate humano: coordinar con el owner, costo cero pero usa su sesión de WhatsApp). PR + PROGRESO + handoff.

## 3. Tabla de asignación de herramientas (por etapa)

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T3.1 | claude-mem:mem-search | skill | claude-mem | Recuperar matriz Plan 2 + auditoría Plan 1 + decisiones previas |
| A | T3.1 | Explore | agente | built-in | Verificar puntos de integración exactos en app.py |
| B | T3.1 | blueprint | skill | community | Plan multi-tarea con briefs autocontenidos — el estándar de esta plantilla |
| B | T3.1 | council | skill | community | Decisión encolado-backend vs endpoint-aparte con tradeoffs explícitos |
| B | T3.1 | api-designer | agente | catalogo-agentes | Contrato de los 4 endpoints nuevos |
| B | T3.1 | superpowers:brainstorming | skill | superpowers | Explorar requisitos del flujo de corrección antes de fijar diseño |
| C | T3.2-T3.4 | tdd-guide + superpowers:test-driven-development | agente+skill | catalogo-agentes + superpowers | RED-GREEN-REFACTOR en cada endpoint y en el worker |
| C | T3.2-T3.3 | python-pro | agente | catalogo-agentes | Refactor idiomático del script a módulos |
| C | T3.3 | backend-patterns / error-handling | skill | ECC | Patrones de cola, reintentos y propagación de errores |
| C | T3.4 | impeccable | skill | community | Modal y badges con estados diseñados (hover/focus/error), no template genérico |
| C | T3.5 | copy-writer [OPCIONAL] | agente | claude-ads | Copy del mensaje B2B que acompaña al catálogo — solo si el owner lo pide |
| D | T3.2-T3.4 | code-reviewer + python-reviewer | agentes | catalogo-agentes | Review por cambio, siempre |
| D | T3.3, T3.4 | security-reviewer | agente | catalogo-agentes | Input de usuario + datos personales (teléfonos) + escritura en hojas |
| D | T3.3 | silent-failure-hunter | agente | catalogo-agentes | El refactor no debe heredar los `except: pass` del original |
| D | T3.6 | browser-qa | skill | ECC | Recorrido del modal y badges en navegador |
| D | T3.6 | superpowers:verification-before-completion | skill | superpowers | Gate final con evidencia |
| E | T3.6 | pr / github-ops | skill | ECC | PR convencional a main |
| E | T3.6 | claude-mem:handoff | skill | claude-mem | Estados y contrato quedan para Plan 5 |

**Fuentes usadas: 7** (claude-mem, built-in, community, catalogo-agentes, superpowers, ECC, claude-ads[opcional]) — cumple el mínimo de 5 incluso sin la opcional.

## 4. Gates de verificación por tarea

| Tarea | Gate |
|---|---|
| T3.1 | Contrato aprobado + respuesta del owner sobre "Pedido" registrada en el doc |
| T3.2 | TDD (test primero en rojo, luego verde); reviewers sin CRITICAL/HIGH |
| T3.3 | pytest total verde; silent-failure-hunter en verde; caracterización Plan 1 migrada sin perder casos |
| T3.4 | security-reviewer en verde (validación server-side demostrada por test) |
| T3.6 | E2E staging con transporte fake (3 estados) + 1 corrida real aprobada por owner |

## 5. Tabla PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T3.1 | Diseño cola + contrato estados | PENDIENTE | | |
| T3.2 | Encolado desde el formulario | PENDIENTE | | |
| T3.3 | Worker de cola (refactor script) | PENDIENTE | | |
| T3.4 | Panel estados + modal corrección número | PENDIENTE | | |
| T3.5 | [OPCIONAL] Copy mensaje catálogo | PENDIENTE | | |
| T3.6 | E2E + PR + cierre | PENDIENTE | | |

## 6. Riesgos y rollback

| Riesgo | Mitigación | Rollback |
|---|---|---|
| Envíos duplicados a clientes reales | Idempotencia por `fila_respuesta` + estado EN_PROCESO como lock + tests dedicados | Marcar filas afectadas y disculpa manual del owner; pausar worker |
| WhatsApp banea el número por automatización | Mantener los sleeps del script original; corrida real limitada a 1-2 números; el riesgo estructural se resuelve en Plan 5 (API oficial) | Desactivar worker (flag env `CATALOGO_WORKER=0`) |
| "No le llegó" ≠ detectable al 100% con WA Web | Comunicar explícitamente al owner que el caso cubierto es NUMERO_INVALIDO + FALLO; doble-check no es fiable | N/A (limitación documentada) |
| Refactor rompe el flujo manual actual del script | Caracterización del Plan 1 migrada íntegra + corrida real de humo | `git revert`; el script original queda en la historia |
| Cuota API Google Sheets por polling | Lecturas batch 1×corrida + cache; worker corre bajo demanda o cada N min, no en loop caliente | Aumentar intervalo |
