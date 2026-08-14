# Índice — Tanda PanelNioval 2026-08-13 (evaluación + integración catálogo + correo + Railway)

**Proyecto:** `C:\Users\PC 1\PanelNioval` (Flask + Google Sheets + Railway)
**Biblioteca usada:** `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas (229 agentes + 424 skills) de 6 fuentes: catalogo-agentes, ECC, claude-ads, community, claude-mem, superpowers (+ built-in de Claude Code).

## Progreso global

**Planes completados: 3 / 5** · Baseline oficial: `pytest tests/ -q` → **117 passed**

| Plan | Documento | Estado |
|---|---|---|
| 1 | [2026-08-13-plan1-evaluacion-22py.md](2026-08-13-plan1-evaluacion-22py.md) | ✅ COMPLETO (5/5) |
| 2 | [2026-08-13-plan2-evaluacion-formulario-llamadas.md](2026-08-13-plan2-evaluacion-formulario-llamadas.md) | ✅ COMPLETO (5/5) |
| 3 | [2026-08-13-plan3-integracion-catalogo.md](2026-08-13-plan3-integracion-catalogo.md) | ✅ COMPLETO (corrida real WA = gate owner) |
| 4 | [2026-08-13-plan4-captura-correo-colT.md](2026-08-13-plan4-captura-correo-colT.md) | PENDIENTE |
| 5 | [2026-08-13-plan5-operacion-railway.md](2026-08-13-plan5-operacion-railway.md) | PENDIENTE |

## Orden de ejecución y dependencias

```
Plan 1 (evaluar 22.py + baseline tests + sanitizar secretos)
   └─► Plan 2 (evaluar formulario + matriz de flujo)
          ├─► Plan 3 (integración catálogo + estados + corrección número)
          └─► Plan 4 (captura correo → col T)   [paralelizable con Plan 3]
                 └─► Plan 5 (todo desde Railway) [requiere 3 y 4 mergeados]
```

- **Plan 1 primero**: crea el baseline de tests (hoy NO existe ninguno) y quita el token Telegram hardcodeado antes de que cualquier plan haga commits.
- **Plan 2 segundo**: su matriz de flujo es el contrato que consumen los Planes 3 y 4.
- **Planes 3 y 4 en paralelo** (ramas separadas) si hay capacidad; si es secuencial, primero el 3 (mayor valor de negocio).
- **Plan 5 al final**: contiene la decisión de arquitectura (gate del owner) que convierte todo en operación 100% Railway.

**Baseline oficial de verificación:** `python -m pytest tests/ -q` — la suite la CREA el Plan 1 (T1.4); desde ese momento, ningún plan mergea con la suite en rojo. Railway auto-deploya `main`: NUNCA trabajar directo en `main`.

## Gates del owner (no automatizables)

1. Plan 3 T3.1: ¿"Pedido" también envía catálogo, o solo "Revisará el Catálogo"?
2. Plan 3 T3.6 / Plan 5 T5.5: corridas reales de WhatsApp (usa su sesión/número).
3. Plan 4 T4.1: confirmar columna T de `LISTA DE CONTACTOS` si está ocupada por otro dato.
4. Plan 5 T5.1: elegir transporte (A=WhatsApp Business API recomendada / B=worker local / C=Selenium en Railway).
5. Plan 5 T5.3: rotar `TELEGRAM_TOKEN` (bot `8404009072`, expuesto en ~14 copias históricas) y cargar secretos en Railway.

## Resumen de asignación de herramientas por fuente (auditoría de diversidad)

| Fuente | Plan 1 | Plan 2 | Plan 3 | Plan 4 | Plan 5 |
|---|---|---|---|---|---|
| catalogo-agentes | code-explorer, python-pro, tdd-guide, 4 reviewers, pr-test-analyzer, doc-updater | code-explorer, api-designer, tdd-guide, 4 reviewers, doc-updater | api-designer, python-pro, tdd-guide, reviewers, silent-failure-hunter | api-designer, tdd-guide, reviewers, security-reviewer | docs-lookup, cloud-architect, python-pro, reviewers, technical-writer |
| ECC | python-testing, pr/github-ops | python-testing, browser-qa, pr | backend-patterns, error-handling, browser-qa, pr | python-testing, frontend-patterns, pr | context7-mcp, ADR, error-handling, deployment-patterns, canary-watch, pr |
| community | production-audit | — (justificado) | blueprint, council, impeccable | impeccable | council, production-audit |
| claude-mem | mem-search, standup/handoff | mem-search, handoff | mem-search, handoff | mem-search, handoff | mem-search, standup+handoff |
| superpowers | writing-plans, TDD, verification | writing-plans, TDD, verification | brainstorming, TDD, verification | brainstorming, TDD, verification | TDD, verification |
| claude-ads | no aplica (justificado) | no aplica (justificado) | copy-writer [OPCIONAL] | no aplica (justificado) | no aplica (justificado) |
| built-in | Explore | Explore | Explore | Explore | Explore (verificaciones) |
| skills-local (Anthropic) | — | webapp-testing | — | webapp-testing | — |

**Conteo de fuentes por plan:** Plan 1 = 6 · Plan 2 = 6 · Plan 3 = 7 · Plan 4 = 7 · Plan 5 = 6. Todos ≥5. Las exclusiones (claude-ads en 1/2/4/5; community en 2) están justificadas por escrito en cada plan.

## PASO 2 — Mejoras propuestas (no pedidas por el owner)

| # | Mejora | Impacto | Esfuerzo | Dónde encaja |
|---|---|---|---|---|
| M1 | **Autenticación del panel** (hoy TODOS los endpoints están abiertos: cualquiera con la URL de Railway puede leer/escribir las hojas de negocio) | ALTO (seguridad de datos de clientes) | Medio | Plan nuevo corto o extensión del Plan 5 (T5.3): token simple tipo `SL_DASHBOARD_TOKEN` como ya se hizo en SistemaLanzamiento |
| M2 | **Trocear `app.py` (3.583+ líneas)** en módulos (rutas/servicios/HTML a templates) — viola el límite de 800 líneas de las reglas globales | MEDIO (mantenibilidad) | Alto | Plan nuevo post-tanda; NO hacerlo a la vez que los Planes 3-4 (conflictos) |
| M3 | **Rotar credencial de servicio Google** si el .json local se copió alguna vez a otro equipo, y verificar permisos mínimos (solo las 5 hojas) | ALTO | Bajo (owner) | Gate adicional en Plan 5 T5.3 |
| M4 | **Batch/caché de gspread en todo app.py** (varias rutas leen hoja completa por request; con 2+ operadores se agota cuota) | MEDIO (fiabilidad) | Medio | Extensión del Plan 3 (ya introduce lecturas batch en el worker) |
| M5 | **CLAUDE.md del proyecto** (no existe): pipeline, hojas/IDs, reglas de datos personales, baseline | MEDIO (DX, futuras sesiones) | Bajo | Añadir como entregable de cierre del Plan 1 |
| M6 | **Secuencia de email a los correos capturados** (los correos de Plan 4 hoy solo se almacenan): campaña de seguimiento B2B con marketing-campaign + copy-writer (claude-ads) | MEDIO (ventas) | Medio | Plan nuevo — AQUÍ sí aplica la suite claude-ads completa |
| M7 | **Telemetría de llamadas** (tiempo por llamada, tasa de conversión por conclusión) con dataviz/dashboard-builder sobre datos ya existentes | BAJO-MEDIO | Bajo | Plan nuevo opcional |
| M8 | **Limpieza de screenshots de debug** (`debug_invalid_*.png/html` con datos de clientes quedan en disco indefinidamente) | MEDIO (privacidad) | Bajo | Plan 3 T3.3 (rotación/retención al refactorizar) |

## PASO 4 — Autoevaluación final

- **¿Cuántas fuentes usa cada plan?** 6/6/7/7/6 — todas ≥5. ✅
- **¿Aparecen ECC, claude-mem, catalogo-agentes y community además de superpowers?** Sí: ECC, claude-mem y catalogo-agentes en los 5 planes; community en 4 de 5 (excluida en Plan 2 con justificación escrita). Superpowers nunca es la fuente dominante. ✅
- **¿claude-ads evaluada?** Sí en los 5 planes: incluida como opcional en Plan 3 (copy del mensaje de catálogo) y excluida con justificación escrita en 1/2/4/5; M6 propone el plan donde entraría a fondo. ✅
- **¿Toda tarea tiene etapa D (verificación)?** Sí — cada plan tiene tabla de gates por tarea y ninguna tarea de implementación cierra sin reviewer + pytest; los planes de evaluación (1-2) también verifican (reviewers cruzados, pr-test-analyzer, E2E). ✅
- **¿Toda tabla PROGRESO está pre-poblada?** Sí, en los 5 documentos, todas en PENDIENTE. ✅
- **Punto débil declarado:** el proyecto no tenía tests ni CLAUDE.md; el baseline nace en Plan 1 T1.4 — hasta ese momento el único gate es review + arranque local del panel. Mitigado poniendo Plan 1 primero en el orden.
