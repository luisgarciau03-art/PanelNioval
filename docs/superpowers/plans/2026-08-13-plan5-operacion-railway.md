# Plan 5 — Todo el sistema funcionando desde Railway

**Fecha:** 2026-08-13 · **Proyecto:** `C:\Users\PC 1\PanelNioval` · **Rama:** `plan5/operacion-railway` · **Depende de:** Planes 1-4 (en especial la matriz de portabilidad del Plan 1 y la cola transport-agnostic del Plan 3)

## 1. Objetivo, alcance y criterios de éxito

**Objetivo:** que el flujo completo — formulario de llamadas → encolado → **envío de catálogo** → validación de estado → corrección de número → captura de correo — funcione **operado desde Railway**, sin depender de que esta PC esté encendida, o con esa dependencia reducida al mínimo y documentada si el owner elige la opción híbrida.

**Estado real (del Plan 1):** `app.py` YA corre en Railway (Procfile + nixpacks.toml + gunicorn, credenciales por `GOOGLE_CREDENTIALS_JSON`). Lo que NO puede correr en Railway tal cual es el transporte WhatsApp Web de `envio_catalogo.py`: necesita Chrome con perfil persistente y sesión de WhatsApp escaneada por QR, y archivos locales (`C:/Users/PC 1/Files mensajes`). **Este plan tiene una decisión de arquitectura con gate del owner.**

**Las 3 opciones (decisión T5.1, council + owner):**
- **A — WhatsApp Business Cloud API (RECOMENDADA):** reemplazar el transporte Selenium por la API oficial (el owner YA la opera en BruceWhatsapp, API v22.0: mismo know-how, plantillas, media upload para el PDF del catálogo). Pros: 100% Railway, sin riesgo de baneo, entrega con estados reales (sent/delivered/failed vía webhooks = validación "no le llegó" DE VERDAD, mejor que lo prometido en Plan 3). Contras: los archivos se envían desde un número Business (¿el mismo de Bruce u otro?), costo por conversación de Meta, y requiere plantillas aprobadas si es fuera de ventana de 24h. Gate owner: elegir número + confirmar costo.
- **B — Híbrido (worker local + Railway orquesta):** Railway mantiene cola y panel; un worker en la PC del owner (Tarea Programada de Windows) hace polling de `ENVIOS_CATALOGO` y ejecuta el transporte Selenium actual. Pros: cero costo Meta, cero cambios de transporte. Contras: depende de la PC encendida (exactamente lo que el owner quiere evitar — solo aceptable como transición).
- **C — Selenium en Railway:** Chrome headless en contenedor + volumen persistente para la sesión WA Web. Contras: QR re-scan frecuente, detección/baneo de WhatsApp, frágil. Se presenta por completitud con recomendación EN CONTRA.

**Criterios de éxito medibles:**
- [ ] Decisión de arquitectura documentada (ADR) con firma del owner.
- [ ] Flujo E2E ejecutado 100% con la PC del owner apagada (opción A/C) o con el worker local instalado como servicio documentado (opción B): cerrar llamada en `/formulario` (Railway) → catálogo llega a un número de prueba → estado visible en el panel → corrección de número funciona.
- [ ] Archivos del catálogo (IMG1.jpg, Video1.mp4, CATÁLOGO NIOVAL.pdf, LPNIOVAL.pdf) servidos desde almacenamiento accesible al transporte elegido (Drive/media API/volumen), no desde `C:/Users/PC 1`.
- [ ] 0 secretos hardcodeados; todas las credenciales en variables Railway (`GOOGLE_CREDENTIALS_JSON`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, y las de WhatsApp API si opción A). Token Telegram ROTADO por el owner antes del go-live (gate).
- [ ] Baseline completo verde + smoke test post-deploy automatizado contra la URL de Railway.
- [ ] Runbook de operación (`docs/RUNBOOK.md`): cómo ver estados, reintentar, leer logs Railway, qué hacer si el envío falla.

## 2. Tareas (formato blueprint)

### T5.1 — Decisión de arquitectura (ADR) — GATE DEL OWNER (sin dependencias)
**Brief autocontenido:** leer matriz de portabilidad (Plan 1) y contrato de cola (Plan 3). Convocar council (4 voces) sobre las opciones A/B/C con criterios: independencia de la PC, riesgo de baneo, costo mensual estimado (calcular conversaciones/mes según volumen real de llamadas del owner), fiabilidad de la validación de entrega, esfuerzo. Producir ADR con recomendación (A) y presentarla al owner con la estimación de costo Meta. NADA se implementa sin su elección.
**Salida:** `docs/adr/2026-08-13-transporte-catalogo.md`.

### T5.2 — Implementación del transporte elegido (depende de T5.1) — TDD
**Brief (rama A, la recomendada):** implementar `transporte_whatsapp_api.py` con la MISMA interfaz `enviar(telefono, mensajes, archivos) -> ResultadoEnvio` definida en Plan 3: upload de media (PDF/imagen/video) a la API de Meta, envío de mensajes (plantilla si >24h, texto libre si sesión abierta), y webhook `POST /webhook/whatsapp-status` en app.py que actualiza `ENVIOS_CATALOGO` con estados reales `sent/delivered/failed` → esto convierte "no le llegó al cliente" en un estado VERIFICADO (mejora sobre Plan 3). Reusar patrones de BruceWhatsapp (`routers_webhooks.py` de ese repo como referencia de verificación de firma del webhook). Archivos del catálogo: subirlos 1 vez como media IDs reutilizables o servirlos desde Drive.
**Brief (rama B):** empaquetar el worker del Plan 3 como servicio Windows (Tarea Programada cada N min + lock file), con instalador `instalar-worker.ps1` y logs locales + heartbeat a Railway (`/api/catalogo/heartbeat`) para que el panel muestre "worker vivo/muerto".
**Gate:** TDD; security-reviewer OBLIGATORIO (webhook público con verificación de firma, tokens, teléfonos).

### T5.3 — Configuración Railway + secretos (depende de T5.2)
**Brief:** actualizar `requirements.txt` (dependencias reales del transporte; quitar las que no corren en Railway si opción A), `Procfile`/`nixpacks.toml` (proceso worker aparte si aplica: `worker: python worker_catalogo.py`), checklist de variables Railway documentada en `.env.example` (sin valores). Gates del owner: rotar `TELEGRAM_TOKEN` (el `8404009072` está expuesto en ~14 copias históricas) y cargar credenciales WhatsApp. Verificar que el deploy no rompe el panel actual (deploy a entorno/URL de prueba primero si Railway lo permite; si no, merge en horario de no-uso del operador).

### T5.4 — Smoke test post-deploy + monitoreo (depende de T5.3)
**Brief:** script `tools/smoke_railway.py` (sin costo LLM): GET `/`, `/formulario`, `/api/formulario/siguiente`, `/api/catalogo/envios` contra la URL productiva → códigos 200 y shape JSON esperado; verificación canary post-deploy (endpoints + assets + errores de consola). Alarma simple: si el worker/webhook no procesa pendientes en X horas → aviso Telegram (reutilizando `enviar_reporte_telegram` con token de env).

### T5.5 — Prueba E2E real + runbook + cierre (depende de T5.4) — GATE HUMANO
**Brief:** con el owner: 1 llamada real de prueba desde `/formulario` en Railway → conclusión "Revisará el Catálogo" → catálogo llega al teléfono de prueba del owner → estado ENVIADO/DELIVERED en panel → forzar un número inválido → corregirlo por el modal → reintento llega. Escribir `docs/RUNBOOK.md`. PR final + PROGRESO + actualización del índice + handoff de memoria con el estado de toda la tanda.

## 3. Tabla de asignación de herramientas (por etapa)

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T5.1 | claude-mem:mem-search | skill | claude-mem | Recuperar know-how WhatsApp API de BruceWhatsapp y matriz Plan 1 |
| A | T5.1 | docs-lookup / context7-mcp | agente/skill | catalogo-agentes / ECC | Docs ACTUALIZADAS de WhatsApp Cloud API (media, plantillas, webhooks) antes de decidir |
| B | T5.1 | council | skill | community | Decisión A/B/C con desacuerdo estructurado antes del gate owner |
| B | T5.1 | architecture-decision-records | skill | ECC | ADR formal de la decisión |
| B | T5.1 | cloud-architect | agente | catalogo-agentes | Evaluar volumen persistente/worker/costos en Railway |
| C | T5.2 | python-pro + tdd-guide | agentes | catalogo-agentes | Transporte nuevo test-first con interfaz ya definida |
| C | T5.2 | superpowers:test-driven-development | skill | superpowers | Disciplina RED-GREEN en webhook y transporte |
| C | T5.2 | error-handling | skill | ECC | Reintentos, timeouts y circuit breaker hacia la API de Meta |
| C | T5.3 | deployment-patterns | skill | ECC | Procfile multi-proceso, health checks, rollback |
| C | T5.2(B) | powershell-5.1-expert [OPCIONAL] | agente | catalogo-agentes | Solo si opción B: instalador de Tarea Programada Windows |
| D | T5.2 | security-reviewer | agente | catalogo-agentes | Webhook público, firma, tokens, datos personales — OBLIGATORIO |
| D | T5.2 | code-reviewer + python-reviewer + silent-failure-hunter | agentes | catalogo-agentes | Review por cambio + fallos silenciosos en integración externa |
| D | T5.4 | canary-watch | skill | ECC | Verificación del deploy en la URL real |
| D | T5.4 | production-audit | skill | community | "¿Qué se rompe en prod?" antes del go-live |
| D | T5.5 | superpowers:verification-before-completion | skill | superpowers | Gate final con evidencia E2E |
| E | T5.5 | pr / github-ops | skill | ECC | PR final |
| E | T5.5 | doc-updater / technical-writer | agente | catalogo-agentes | RUNBOOK operable por el owner |
| E | T5.5 | claude-mem:standup + handoff | skill | claude-mem | Cierre de tanda con estado global |

**Fuentes usadas: 6** (claude-mem, catalogo-agentes, ECC, community, superpowers, built-in vía Explore en verificaciones). **claude-ads: no aplica** — es infraestructura de entrega; no hay campañas pagadas. Si más adelante el catálogo se promociona con ads, la suite claude-ads entra en ese plan futuro.

## 4. Gates de verificación por tarea

| Tarea | Gate |
|---|---|
| T5.1 | ADR con las 3 opciones + costo estimado; DECISIÓN EXPLÍCITA del owner registrada |
| T5.2 | TDD; security-reviewer en verde (firma webhook probada por test); baseline total verde |
| T5.3 | Deploy de prueba OK; owner confirma rotación de token Telegram y alta de secretos |
| T5.4 | Smoke test verde contra URL productiva; alarma probada (forzar 1 fallo) |
| T5.5 | E2E real con el owner (checklist firmado en el PR); RUNBOOK revisado |

## 5. Tabla PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T5.1 | ADR transporte (gate owner) | PENDIENTE | | |
| T5.2 | Implementación transporte elegido | PENDIENTE | | |
| T5.3 | Config Railway + secretos | PENDIENTE | | |
| T5.4 | Smoke test + monitoreo | PENDIENTE | | |
| T5.5 | E2E real + runbook + cierre | PENDIENTE | | |

## 6. Riesgos y rollback

| Riesgo | Mitigación | Rollback |
|---|---|---|
| Railway auto-deploya main y rompe el panel en uso | Todo por rama+PR; merge solo con gates verdes y smoke test listo para correr al minuto | `git revert` + redeploy (Railway toma el revert automáticamente) |
| Opción A: costo Meta inesperado | Estimación de costo en el ADR con volumen real ANTES del gate; alerta de presupuesto | Feature flag para pausar envíos API |
| Opción A: plantillas rechazadas por Meta | Diseñar plantilla neutra (envío de catálogo solicitado en llamada = utility) y someterla temprano en T5.2 | Mensaje de sesión (ventana 24h post-llamada suele estar abierta: el cliente acaba de hablar) |
| Opción B: PC apagada = envíos parados | Heartbeat visible en panel + alarma Telegram | Reactivar PC; migrar a opción A |
| Webhook público atacado | Verificación de firma (X-Hub-Signature-256) + rate limiting; probado por test | Desactivar ruta y regenerar app secret |
| Token Telegram viejo sigue activo | Gate T5.3: owner rota ANTES del go-live | Revocar vía BotFather |
