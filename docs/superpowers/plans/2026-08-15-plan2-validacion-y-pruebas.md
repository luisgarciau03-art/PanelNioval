# PLAN 2 — VALIDACIÓN Y PRUEBAS: PARIDAD VERIFICABLE

**Fecha de diseño:** 2026-08-15
**Repositorio canónico:** `C:\Users\PC 1\migracion-claude-code`
**Rama de trabajo:** `migracion/vscode-a-claude-code`
**Depende de:** Plan 0 cerrado y Plan 1 cerrado.
**Modo:** duplicar, no reemplazar. Este plan no modifica el entorno salvo para crear scripts de prueba.

---

## 0. Principio rector

**"Se ve bien" no es un resultado.** Para cada componente del entorno tiene que existir un comando que se ejecuta, una salida esperada, y un veredicto binario. Si una comprobación no se puede ejecutar, no cuenta como verificada y se declara así en el informe.

El plan mide el entorno contra dos referencias distintas, y esa distinción es el corazón del diseño:

- **Referencia declarada:** `BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas, 229 agentes + 424 skills, 6 fuentes.
- **Referencia observada:** lo que hay en disco — 229 agentes, 393 skills locales, 509 comandos, 114 reglas, 28 hooks, 2 plugins.

Cuadran, pero solo si se explica la diferencia: **393 skills locales + 14 de superpowers + ~17 de claude-mem = 424**. Las 31 restantes viven en `plugins\cache\`, no en `skills\`. Una prueba de paridad que no contemple esto reportará un falso negativo de 31 skills faltantes.

---

## 1. Objetivo

Producir evidencia ejecutable y reproducible de que el entorno funciona igual desde terminal y desde el sidebar, y de que cada componente declarado en la biblioteca existe y carga.

## 2. Alcance

**SÍ entra:** matriz de comprobación por componente; scripts de verificación reutilizables; pruebas de carga por fuente; prueba del grafo de 28 hooks; prueba de MCP; prueba end-to-end de memoria; formalización del baseline de no regresión de VSCode; aplicación del checklist a los 7 proyectos; informe de paridad.

**NO entra:** arreglar lo que las pruebas encuentren roto. Un hallazgo de este plan que no sea trivial se convierte en tarea del Plan 3, o en un Plan 4 si su tamaño lo justifica. **Mezclar diagnóstico con reparación es cómo una batería de pruebas se convierte en una refactorización.**

## 3. Criterios de éxito (medibles)

| # | Criterio | Comprobación ejecutable | Umbral |
|---|---|---|---|
| CE-2.1 | Existe un script de censo reproducible | `pwsh -File scripts\censo-entorno.ps1` | Devuelve JSON con los 6 conteos, exit code 0 |
| CE-2.2 | El censo cuadra con la biblioteca | Comparación censo vs. 653/229/424 | Diferencia explicada al 100%, 0 discrepancias sin justificar |
| CE-2.3 | Cada fuente carga, no solo lista | Muestreo de carga (T2.3) | ≥1 herramienta cargada con éxito por cada una de las 6 fuentes |
| CE-2.4 | El grafo de hooks está íntegro | `scripts\verificar-hooks.ps1` | Los 28 hooks resuelven a un script existente; 0 rutas rotas |
| CE-2.5 | Los MCP activos conectan en ambas ventanas | `/mcp` en CLI y sidebar | Salidas idénticas |
| CE-2.6 | La memoria graba end-to-end | Sesión de prueba → query en la base | ≥1 observación nueva con `session_id` de la prueba |
| CE-2.7 | VSCode sin regresión, formalizado | `docs\pruebas\baseline-vscode.md` ejecutado | 5/5 pasos en verde |
| CE-2.8 | Los 7 proyectos alineados | Checklist del Plan 1 T1.7 aplicado | 7/7 con resultado registrado (alineado o excepción documentada) |
| CE-2.9 | Informe de paridad publicado | `docs\pruebas\informe-paridad.md` | Una fila por componente, con comando, salida y veredicto |

## 4. Dependencias

```
T2.1 (matriz) ──> T2.2 (censo) ──┬──> T2.3 (carga por fuente) ──┐
                                 ├──> T2.4 (hooks) ─────────────┤
                                 ├──> T2.5 (MCP) ───────────────┼──> T2.9 (informe)
                                 ├──> T2.6 (memoria) ───────────┤
                                 └──> T2.7 (baseline VSCode) ───┤
                                                T2.8 (proyectos)┘
```

T2.3 a T2.8 son independientes entre sí: se pueden ejecutar en paralelo con `Workflow` o con subagentes.

---

## 5. TAREAS (formato blueprint — contexto autocontenido)

### T2.1 — Diseñar la matriz de comprobación

**Contexto para una sesión fría:** el entorno Claude de esta máquina vive en `C:\Users\PC 1\.claude\` y lo comparten Claude Code CLI y la extensión `anthropic.claude-code` de VSCode (ver Plan 1 §0 para la evidencia). Los componentes a verificar, con sus cantidades observadas en disco el 2026-08-15, son:

| Componente | Cantidad | Ubicación |
|---|---|---|
| Agentes | 229 `.md` | `.claude\agents\` |
| Skills locales | 393 dirs | `.claude\skills\` |
| Skills de plugins | ~31 | `.claude\plugins\cache\{obra,thedotmack}\` |
| Comandos | 509 `.md` | `.claude\commands\` |
| Reglas | 114 archivos, 21 lenguajes | `.claude\rules\ecc\` |
| Hooks | 28 en 7 eventos | `.claude\hooks\hooks.json` |
| Scripts de hooks | 44 | `.claude\scripts\hooks\` |
| Plugins | 2 | `.claude\plugins\installed_plugins.json` |
| Marketplaces | 2 | `.claude\plugins\known_marketplaces.json` |
| Catálogo MCP | 33 definidos | `.claude\mcp-configs\mcp-servers.json` |

**Entregable:** `docs\pruebas\matriz-comprobacion.md`, una fila por componente con: qué se afirma, comando exacto, salida esperada, y qué significa un fallo.

**Definition of done:** matriz revisada y aprobada antes de escribir un solo script. Diseñar las pruebas después de escribirlas es cómo se acaba probando lo que es fácil de probar en vez de lo que importa.

---

### T2.2 — Script de censo del entorno

**Contexto:** el censo del 2026-08-15 se hizo a mano, sobre un snapshot, por una sesión que no tenía shell en la máquina. No es repetible. Esta tarea lo convierte en un script que cualquiera corre en 5 segundos.

**Entregable:** `scripts\censo-entorno.ps1` que emite JSON:

```json
{
  "fecha": "...",
  "agentes": 229, "skillsLocales": 393, "skillsPlugins": 31,
  "comandos": 509, "reglas": 114, "hooks": 28, "scriptsHooks": 44,
  "plugins": ["claude-mem@thedotmack 13.15.0", "superpowers@obra 6.3.0"],
  "marketplaces": ["thedotmack", "obra"],
  "mcpCatalogo": 33,
  "discrepancias": []
}
```

**Pasos:**
1. Contar cada componente con `Get-ChildItem`.
2. Parsear `installed_plugins.json` y `known_marketplaces.json` para versiones reales.
3. Parsear `hooks\hooks.json` y contar entradas por evento.
4. Comparar contra los valores declarados en `BIBLIOTECA-HERRAMIENTAS.md` (653 = 229 + 424) y **emitir la reconciliación explícita** 393 + 14 + 17 = 424.
5. Poblar `discrepancias[]` con todo lo que no cuadre. Un array vacío es el resultado deseado; un array con contenido es un hallazgo, no un fallo del script.
6. Exit code 0 si `discrepancias` está vacío, 1 si no.

**Definition of done:** CE-2.1 y CE-2.2. El script se guarda en el repo y se vuelve la herramienta de censo permanente, sustituyendo a `generar-inventario.ps1` como fuente de conteos.

---

### T2.3 — Prueba de carga por fuente (muestreo, no exhaustivo)

**Contexto:** listar 653 herramientas no prueba que carguen. Invocar las 653 es inviable y no aporta: el modo de fallo realista es *por fuente* (una fuente mal instalada rompe todas sus herramientas), no *por herramienta*.

**Diseño del muestreo — y su límite, declarado:** se prueban **5 herramientas por fuente**, elegidas por criterio, no al azar: la más usada, la más grande, la más pequeña, una con dependencias externas, una escrita más recientemente. **Esto NO prueba las 653.** Cubre ~30 de 653 (4.6%). El informe debe decirlo con esas palabras: un muestreo que se reporta como cobertura total es peor que no muestrear.

| Fuente | Herramientas a probar (ejemplos a confirmar en disco) |
|---|---|
| catalogo-agentes | `code-reviewer` (14,210 B, la mayor), `m365-admin` (1,897 B, la menor), `security-reviewer`, `python-reviewer`, `powershell-7-expert` |
| ECC | `ecc-guide`, `security-review`, `gateguard`, `mcp-builder`, `hookify-rules` |
| claude-ads | `ads-plan`, `audit-tracking`, `copy-writer`, `creative-strategist`, `format-adapter` |
| community | `blueprint`, `council`, `deep-research`, `dashboard-builder`, `production-audit` |
| claude-mem | `mem-search`, `make-plan`, `standup`, `timeline`, `learn-codebase` |
| superpowers | `brainstorming`, `writing-plans`, `test-driven-development`, `systematic-debugging`, `verification-before-completion` |

**Pasos:**
1. Para cada una: invocarla en sesión del CLI y registrar si carga, si falla o si no existe.
2. Repetir en el sidebar de VSCode.
3. Cualquier "no existe" es un hallazgo: la biblioteca declara algo que el disco no tiene.

**Definition of done:** CE-2.3, más tabla de 30 filas con veredicto y la nota de cobertura del 4.6%.

---

### T2.4 — Verificar el grafo de 28 hooks

**Contexto:** `.claude\hooks\hooks.json` pesa 49,658 B y define **28 hooks** en 7 eventos (`PreToolUse`, `PreCompact`, `SessionStart`, `PostToolUse`, `PostToolUseFailure`, `Stop`, `SessionEnd`). Casi todo el peso es boilerplate: cada `command` es un `node -e "..."` que resuelve `CLAUDE_PLUGIN_ROOT` probando rutas en orden.

**Fragilidad conocida, a confirmar:** ese resolvedor prueba rutas como `~/.claude/plugins/ecc`, `~/.claude/plugins/ecc@ecc`, `~/.claude/plugins/marketplaces/ecc`, `~/.claude/plugins/cache/ecc/...`. **Ninguna existe**, porque ECC no está instalado como plugin: sus archivos están vertidos directamente en `~/.claude`. El resolvedor cae al fallback `~/.claude` y funciona. **Funciona por el último candidato de una lista, no por diseño.** Esta tarea lo documenta; arreglarlo es del Plan 3.

**Pasos:**
1. Script `scripts\verificar-hooks.ps1`: parsear `hooks.json`, extraer los 28 destinos, comprobar que cada `scripts\hooks\<x>.js` existe en disco.
2. Contrastar con los 44 scripts presentes: cuántos se usan, cuántos son código muerto.
3. Probar los perfiles: `ECC_HOOK_PROFILE` acepta `minimal|standard|strict` (default `standard`). Correr una sesión con cada uno y registrar diferencia de comportamiento.
4. Probar el desactivador: `ECC_DISABLED_HOOKS=<id>` con un hook inocuo (p. ej. `stop:desktop-notify`) y confirmar que deja de dispararse. **Es el mecanismo de rollback de emergencia de todo el grafo**; si no funciona, es un hallazgo grave.
5. Medir el coste: los hooks `Stop` tienen timeout de hasta 300 s (`stop:format-typecheck`). Cronometrar una sesión trivial de principio a fin.

**Definition of done:** CE-2.4, más informe con: rutas rotas (0 esperado), scripts muertos (número), perfiles verificados, `ECC_DISABLED_HOOKS` verificado, sobrecoste por sesión en segundos.

---

### T2.5 — Verificar los servidores MCP

**Contexto:** `.claude\mcp-configs\mcp-servers.json` define 33 servidores, **todos con credenciales `YOUR_*_HERE`: es un catálogo de ECC, no configuración activa.** Los activos reales viven en `~/.claude.json`. Además, `.cursor\mcp.json` y `.roo\mcp.json` declaran cada uno el MCP `claude-mem`, con runtimes distintos (`bun` en los hooks de Cursor, `node` en el MCP de Roo).

**Pasos:**
1. `/mcp` en el CLI y en el sidebar. Comparar salidas. **Deben ser idénticas** — mismo archivo de configuración, mismo motor.
2. Para cada MCP activo: invocar una herramienta suya y confirmar respuesta, no solo estado "connected".
3. Revisar `mcp-needs-auth-cache.json` (273 B): qué servidores quedaron marcados como pendientes de autenticación.
4. Confirmar que ningún MCP activo tiene credenciales en archivo (deben estar en variables de entorno tras el Plan 0).

**Definition of done:** CE-2.5.

---

### T2.6 — Prueba end-to-end de la memoria

**Contexto:** la captura estuvo rota del 2026-07-09 al arreglo del Plan 1 T1.1 — **36+ días**. El fallo era silencioso: la base seguía recibiendo escrituras por otras vías mientras el camino roto fallaba sin alertar. Una prueba que solo mire "¿hay filas nuevas?" puede dar verde con la captura a medias.

**Pasos:**
1. Anotar el `COUNT(*)` de `observations` antes.
2. Sesión de prueba en el CLI con una acción que deba generar observación (editar un archivo en un proyecto de prueba).
3. Consultar la base filtrando por el `session_id` de esa sesión. **Debe aparecer**, no basta con que el total suba.
4. Repetir desde el sidebar de VSCode. Comparar.
5. Repetir desde Cursor (que escribe la misma base con otro runtime). Registrar si escribe, y con qué `project`.
6. Verificar que `CAPTURE_BROKEN` no reaparece tras las tres.
7. Registrar el estado de Chroma: `CLAUDE_MEM_CHROMA_ENABLED` está en `"false"`, pero `chroma-sync-state.json` reporta BruceWhatsapp **201 observaciones sincronizadas de 10,163** y SistemaLanzamiento **0 de 1,203**, con resúmenes en 1,215 y 1,223. La búsqueda semántica cubre resúmenes, casi no cubre observaciones, y está apagada. **Documentarlo aquí; decidirlo en el Plan 3.**

**Definition of done:** CE-2.6, con la tabla de qué entorno escribe qué.

---

### T2.7 — Formalizar el baseline de no regresión de VSCode

**Contexto:** los Planes 0 y 1 exigen "VSCode sigue funcionando" tras cada tarea. Hasta ahora eso es una frase. Esta tarea la vuelve un procedimiento de 5 pasos que cualquiera ejecuta igual.

**Entregable:** `docs\pruebas\baseline-vscode.md` con:

1. VSCode abre sin error en la consola de extensiones.
2. La extensión `anthropic.claude-code` aparece activa. **Nota:** `extensions.json` registra 2.1.205 pero en disco conviven 2.1.205 y 2.1.233. Anotar cuál está activa realmente — es un hallazgo abierto que hereda el Plan 3.
3. Claude abre en el sidebar (`preferredLocation: "sidebar"`).
4. Petición simple responde.
5. Un edit de archivo muestra diff antes de aplicar (`showDiffBeforeApplying: true`) — **este paso es el que no tiene equivalente en terminal**, y por eso se prueba explícitamente: es la diferencia real de seguridad entre las dos ventanas.

**Definition of done:** CE-2.7, documento ejecutado con 5/5.

---

### T2.8 — Aplicar el checklist a los 7 proyectos

**Contexto:** el Plan 1 T1.7 produce `docs\checklist-alineacion-proyecto.md` y lo prueba en un piloto. Aquí se aplica a los siete y se registra el resultado. Estado de partida:

| Proyecto | `.claude` | `.git` | `.superpowers` | Nota |
|---|---|---|---|---|
| BruceWhatsapp | ✅ | ✅ | ✅ | 10,163 obs, 133 sesiones |
| SistemaLanzamiento | ✅ | ✅ | ✅ | 1,203 obs, 28 sesiones |
| FinanzasAPPANDROID | ✅ | ✅ | ✅ | 136 obs, 1 sesión |
| NIOVAL_ANTHROPIC | ✅ | ✅ | ✗ | |
| SUPRATECHWEB | ✅ | ✅ | ✗ | |
| veo-asesores-claude | ✅ | **✗** | ✗ | **Sin control de versiones** |
| PanelNioval | **✗** | ✅ | ✗ | Sin config de Claude |

**Pasos:**
1. Ejecutar el checklist en cada uno, en el orden: PanelNioval (piloto del Plan 1), luego los tres completos, luego los dos sin `.superpowers`, y **`veo-asesores-claude` al final**, porque hasta que tenga git cualquier error ahí es irreversible.
2. Copiar los 5 documentos de planes a `docs\superpowers\plans\` de cada uno, **marcados como copia de solo lectura**. La canónica es la de `migracion-claude-code`.
3. Registrar por proyecto: alineado / excepción documentada. Una excepción explicada es un resultado válido; un proyecto sin registrar no lo es.

**Definition of done:** CE-2.8, 7/7 registrados.

---

### T2.9 — Informe de paridad

**Entregable:** `docs\pruebas\informe-paridad.md` con una fila por componente:

| Componente | Comando | Esperado | Obtenido | Veredicto | Evidencia |
|---|---|---|---|---|---|

Más una sección de **límites declarados**: qué NO se probó y por qué. Como mínimo: el muestreo de T2.3 cubre 4.6% de las herramientas; los subárboles de `skills\<393>\**` y de los dos clones de marketplace no se recorrieron exhaustivamente; los perfiles `minimal` y `strict` de hooks se probaron en una sesión cada uno, no en uso sostenido.

**Definition of done:** CE-2.9. **Un informe que no declara sus límites es propaganda.**

---

## 6. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

Fuentes usadas: **catalogo-agentes, ECC, community, claude-mem, superpowers, built-in** — 6 fuentes. Justificación de claude-ads en §6.1.

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T2.1, T2.6 | `claude-mem:mem-search` | skill | claude-mem | **Obligatorio.** 162 sesiones de historial dicen qué herramientas se usaron de verdad y cuáles nunca. Eso decide el muestreo de T2.3: "la más usada" no es una suposición, es un dato recuperable. |
| A | T2.1 | `claude-mem:learn-codebase` | skill | claude-mem | [OPCIONAL] Si el ejecutor no conoce la estructura de `.claude\`. Condición de uso: primera sesión que toca este entorno. |
| A | T2.2, T2.4 | `Explore` | agente | built-in | Censo sobre 12,292 archivos y 44 scripts de hooks sin quemar contexto principal. |
| A | T2.1 | `repo-scan` | skill | ECC | Estado real del árbol antes de diseñar qué se mide. |
| B | T2.1 | `blueprint` | skill | community | La matriz debe ser ejecutable por sesión fría. Estándar de la plantilla. |
| B | T2.3 | `council` | skill | community | [OPCIONAL] Decisión con tradeoff real: qué 5 herramientas por fuente representan mejor a las demás. Condición de uso: si el criterio propuesto (más usada / mayor / menor / con dependencias / más reciente) se discute. |
| B | T2.1, T2.9 | `qa-expert` | agente | catalogo-agentes | Estrategia de QA integral: qué se prueba, con qué cobertura, y cómo se reportan los límites. Es el agente que define la forma del plan. |
| C | T2.2, T2.4, T2.7 | `powershell-7-expert` | agente | catalogo-agentes | Los tres scripts (`censo-entorno.ps1`, `verificar-hooks.ps1`, baseline) son PowerShell sobre Windows. Especialista del stack real. |
| C | T2.2, T2.4 | `powershell-module-architect` | agente | catalogo-agentes | [OPCIONAL] Si los scripts crecen y conviene empaquetarlos como módulo reutilizable. Condición de uso: si `censo-entorno.ps1` supera ~200 líneas. |
| C | T2.2, T2.9 | `test-automator` | agente | catalogo-agentes | Convertir comprobaciones manuales en scripts repetibles con exit code, que es literalmente el objetivo del plan. |
| C | T2.6 | `database-reviewer` | agente | catalogo-agentes | Consultas de solo lectura sobre `claude-mem.db`: primero `.schema`, luego el `SELECT` por `session_id`. El esquema de claude-mem 13.15.0 no se supone. |
| C | T2.4, T2.5 | `mcp-builder` | skill | ECC | Convenciones MCP de ECC, que es de donde vienen tanto el catálogo de 33 como el grafo de hooks. |
| C | T2.4 | `browser-harness` / `e2e-runner` | skill / agente | ECC / catalogo-agentes | [OPCIONAL] Si alguna comprobación necesita flujo E2E real en vez de invocación directa. Condición de uso: si T2.3 no puede invocar una skill sin UI. |
| C | T2.3, T2.8 | `Workflow` | built-in | built-in | T2.3 a T2.8 son independientes: fan-out determinista de subagentes, un agente por fuente y un agente por proyecto. Es el caso de uso exacto de la herramienta. |
| C | T2.8 | `git-workflow-manager` | agente | catalogo-agentes | El checklist incluye `git init` en `veo-asesores-claude`. |
| D | Todas | `code-reviewer` | agente | catalogo-agentes | Gate general sobre todo script escrito. |
| D | T2.4, T2.5 | `security-reviewer` | agente | catalogo-agentes | **Obligatorio**: T2.4 toca hooks y T2.5 toca MCP y credenciales. |
| D | Todas | `silent-failure-hunter` | agente | catalogo-agentes | Riesgo central de un plan de pruebas: un script que devuelve exit 0 porque no encontró nada que mirar. La captura de memoria ya falló 36 días en silencio; este plan no puede repetir el patrón. |
| D | T2.2, T2.9 | `pr-test-analyzer` | agente | catalogo-agentes | ¿Las comprobaciones cubren comportamiento real o solo lo fácil de medir? Pregunta obligada antes de firmar el informe. |
| D | T2.9 | `superpowers:verification-before-completion` | skill | superpowers | Gate final del plan. |
| D | T2.3, T2.9 | `verification-loop` | skill | ECC | Itera hasta verde cuando una comprobación falla por entorno y no por defecto real. |
| D | T2.4 | `performance-optimizer` | agente | catalogo-agentes | [OPCIONAL] Si el paso 5 de T2.4 revela que los hooks `Stop` (timeout 300 s) añaden latencia inaceptable. Condición de uso: sobrecoste medido > 10 s por sesión. |
| D | T2.9 | `ai-writing-auditor` | agente | catalogo-agentes | [OPCIONAL] El informe es un documento que otros leerán como verdad; conviene que no exagere. Condición de uso: antes de distribuir a los 7 proyectos. |
| E | Cierre | `pr` / `git-workflow` | skill | ECC | PR con commits `test:` convencionales en español. |
| E | Cierre | `technical-writer` | agente | catalogo-agentes | El informe de paridad y la matriz son entregables públicos del plan. |
| E | Cierre | `claude-mem:standup` | skill | claude-mem | Persistir el resultado de la validación para que el Plan 3 arranque sabiendo qué quedó abierto. |
| E | Distribución | `handoff` | skill | ECC | Copia a los 7 proyectos + contexto para el Plan 3. |

### 6.1 — Evaluación de claude-ads (justificación obligatoria por escrito)

**claude-ads NO aplica al Plan 2 como herramienta de ejecución, pero SÍ como objeto de prueba.**

Como ejecutora no aplica: no hay campañas, píxeles ni creatividades que auditar en una batería de pruebas de entorno.

Como objeto sí: **claude-ads es una de las 6 fuentes de la biblioteca (~60 herramientas), y T2.3 tiene que probar que carga igual que las demás.** Si `ads-plan`, `audit-tracking`, `copy-writer`, `creative-strategist` y `format-adapter` no cargan, hay 60 herramientas rotas que nadie notaría hasta necesitarlas. Esa fila del muestreo es obligatoria y no se omite por "aquí no hay publicidad".

---

## 7. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Gate obligatorio | Gate de seguridad | Gate adicional |
|---|---|---|---|
| T2.1 | `qa-expert` + `code-reviewer` | — | Matriz aprobada antes de escribir scripts |
| T2.2 | `code-reviewer` + `test-automator` | — | Exit code correcto en caso con y sin discrepancias |
| T2.3 | `code-reviewer` | — | 6/6 fuentes con ≥1 carga exitosa; cobertura declarada |
| T2.4 | `code-reviewer` | `security-reviewer` **crítico** (hooks) | `ECC_DISABLED_HOOKS` verificado como rollback |
| T2.5 | `code-reviewer` + `mcp-developer` | `security-reviewer` **crítico** (MCP, credenciales) | Salidas CLI y sidebar idénticas |
| T2.6 | `database-reviewer` | `security-reviewer` (base con 77 obs sensibles) | Observación localizada por `session_id`, no por conteo |
| T2.7 | `code-reviewer` | — | 5/5 pasos, incluido el diff previo |
| T2.8 | `git-workflow-manager` | `security-reviewer` | 7/7 registrados |
| T2.9 | `superpowers:verification-before-completion` + `pr-test-analyzer` | `security-reviewer` (cierre) | Sección de límites presente |

## 8. BASELINE DE NO REGRESIÓN DEL ENTORNO

Tras cada tarea: VSCode abre Claude y responde; el CLI responde y lista 229 agentes y 2 plugins. A partir de T2.6, además: Cursor y Roo arrancan con su MCP `claude-mem` conectado.

Este plan **no modifica el entorno**, así que una regresión aquí significa que algo externo cambió — y eso también es un hallazgo que se registra.

## 9. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback concreto |
|---|---|---|---|---|---|
| R2.1 | Falso negativo de 31 skills por no reconciliar 393 + plugins = 424 | **Alta** si se omite | Medio | La reconciliación es paso 4 explícito de T2.2 | Corregir el script; no hay daño al entorno |
| R2.2 | Un script de prueba escribe donde no debe (la base, `settings.json`) | Baja | **Alto** | Todas las consultas a la base son solo lectura; los scripts no editan configuración | Restaurar desde `_respaldo-migracion-2026-08-15\` (Plan 1 T1.0) |
| R2.3 | El informe reporta paridad total con un muestreo del 4.6% | Media | **Alto** | La sección de límites es requisito de cierre de T2.9, con `pr-test-analyzer` como gate | Reeditar el informe; el daño es de credibilidad, no técnico |
| R2.4 | Probar `ECC_DISABLED_HOOKS` desactiva un hook y no se vuelve a activar | Baja | Medio | Usar un hook inocuo (`stop:desktop-notify`), en sesión aislada, con variable de entorno de sesión y no de usuario | Cerrar la terminal: la variable de sesión muere con ella |
| R2.5 | La sesión de prueba de memoria ensucia la base con datos de prueba | Media | Bajo | Usar un proyecto de prueba dedicado, marcable y purgable | Borrar por `session_id` de la sesión de prueba, que es conocido |
| R2.6 | T2.8 rompe un proyecto al aplicar el checklist | Media | Alto | Orden deliberado: piloto → completos → incompletos → `veo-asesores-claude` al final | `git checkout` en cada repo; en `veo-asesores-claude` solo tras su `git init` |
| R2.7 | Las pruebas encuentran algo roto y el ejecutor lo arregla sobre la marcha | **Alta** | Medio | El alcance lo prohíbe explícitamente: los hallazgos van al Plan 3 | Revertir el arreglo improvisado y abrir la tarea donde toca |

---

## 10. TABLA PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T2.1 | Diseñar la matriz de comprobación | PENDIENTE | | |
| T2.2 | Script de censo del entorno | PENDIENTE | | |
| T2.3 | Prueba de carga por fuente (6 fuentes × 5) | **HECHA** — *con límite declarado* | **CE-2.3 CUMPLIDO: 6/6 fuentes con carga exitosa. 29/30 CARGAN.** Informe: `docs\pruebas\informe-carga-t2.3.md`. Método: 21 skills invocadas con `Skill`, 9 agentes despachados como subagente (evidencia = contenido que solo puede venir de su definición). Hallazgos: **H-T2.3-1** `timeline` NO EXISTE como skill (nombre inexacto del muestreo; lo que existe es `timeline-report`, y `timeline` es herramienta MCP) — confirmado por disco y por invocación, **no sustituido**; **H-T2.3-2** 5 de 9 agentes declaran una identidad distinta a su nombre de archivo. Cobertura declarada **4.6% (30/653)**. **Límite: solo CLI — falta repetir en el sidebar (paso 2)** | 2026-08-15 |
| T2.4 | Verificar el grafo de 28 hooks | PENDIENTE | | |
| T2.5 | Verificar los servidores MCP | PENDIENTE | | |
| T2.6 | Prueba end-to-end de la memoria | PENDIENTE | | |
| T2.7 | Formalizar el baseline de no regresión de VSCode | PENDIENTE | | |
| T2.8 | Aplicar el checklist a los 7 proyectos | PENDIENTE | | |
| T2.9 | Informe de paridad | PENDIENTE | | |

**Avance del Plan 2: 1/9 tareas HECHAS (11%).**
