# PLAN 3 — OPTIMIZACIÓN DEL ENTORNO YA DUPLICADO

**Fecha de diseño:** 2026-08-15
**Repositorio canónico:** `C:\Users\PC 1\migracion-claude-code`
**Rama de trabajo:** `migracion/vscode-a-claude-code`
**Depende de:** Planes 0, 1 y 2 cerrados. Este plan trabaja sobre hallazgos, y los hallazgos los produce el Plan 2.
**Modo:** duplicar, no reemplazar. Aquí es donde más fácil se rompe VSCode, porque se borra y se reorganiza.

---

## 0. Principio rector

Optimizar un entorno del que dependen dos IDE, un CLI y tres productos de terceros no es limpiar: es cirugía sobre algo que está en uso. **Cada tarea de este plan tiene que poder deshacerse**, y ninguna se ejecuta sin que el Plan 2 haya dejado un baseline verde contra el que comparar.

Las optimizaciones se ordenan por **impacto/esfuerzo**, no por lo llamativas que sean. Borrar 12.5 MB de telemetría es satisfactorio y casi irrelevante; reinstalar ECC bajo control del instalador es tedioso y es lo que decide si este entorno se puede mantener el año que viene.

---

## 1. Objetivo

Reducir la deuda técnica del entorno compartido y cerrar los hallazgos abiertos de los planes anteriores, sin perder capacidad ni romper ninguna de las cinco superficies que lo consumen (CLI, VSCode, Cursor, Roo, Windsurf).

## 2. Alcance

**SÍ entra:** ECC fuera de control del instalador; ~370 comandos stub; rutas fantasma del resolvedor de hooks; los 478 skills de `.copilot`; 12.5 MB de telemetría fallida y otro cruft; el estado a medias de Chroma y las colas de sincronización de claude-mem; la extensión de VSCode huérfana y los ajustes fantasma; homogeneización de los 7 proyectos.

**NO entra:** cambiar la postura de permisos (se decidió en el Plan 1 T1.3). NO entra mover código de proyectos.

## 3. Criterios de éxito (medibles)

| # | Criterio | Comprobación ejecutable | Umbral |
|---|---|---|---|
| CE-3.1 | ECC bajo control del instalador | `ecc\install-state.json` registra los módulos de skills/agents/commands/rules | `operations` cubre >90% de los archivos, no solo los 147 de `hooks-runtime` |
| CE-3.2 | Los comandos stub están resueltos | `scripts\censo-entorno.ps1` | Nº de comandos <100 B baja de ~370 a lo decidido, con criterio escrito |
| CE-3.3 | El resolvedor de hooks no depende del fallback | `scripts\verificar-hooks.ps1` | Resuelve en el primer candidato, no en el último |
| CE-3.4 | `.copilot` tiene destino decidido | `docs\decisiones\copilot-478-skills.md` | 478 clasificadas en portar/archivar/descartar, 0 sin decidir |
| CE-3.5 | Cruft eliminado | Tamaño de `.claude\` antes/después | ≥12 MB liberados, 0 componentes funcionales perdidos |
| CE-3.6 | Sincronización de memoria coherente | Query sobre `sync_outbox`, `sync_state`, `chroma-sync-state.json` | Estado consistente y documentado, o Chroma apagado limpiamente |
| CE-3.7 | VSCode sin extensión huérfana ni ajustes muertos | `Get-ChildItem ~\.vscode\extensions\anthropic.claude-code*` | Una sola versión; `settings.json` sin claves sin dueño |
| CE-3.8 | Los 7 proyectos homogéneos o con excepción escrita | Censo por proyecto | 7/7 registrados |
| CE-3.9 | Sin regresión | Baseline del Plan 2 T2.7 + censo T2.2 | Idénticos salvo lo intencionalmente cambiado |

## 4. Dependencias

```
Plan 2 cerrado
   │
   ├── ALTO IMPACTO / ALTO ESFUERZO
   │   ├──> T3.1 (ECC bajo instalador) ──> T3.2 (comandos stub) ──> T3.3 (rutas de hooks)
   │
   ├── ALTO IMPACTO / BAJO ESFUERZO
   │   ├──> T3.6 (memoria: colas y Chroma)
   │   └──> T3.7 (VSCode: extensión huérfana y ajustes)
   │
   ├── MEDIO / MEDIO
   │   ├──> T3.4 (.copilot 478 skills)
   │   └──> T3.8 (homogeneizar proyectos)
   │
   └── BAJO / BAJO
       └──> T3.5 (cruft) ──> T3.9 (verificación final)
```

**T3.1 antes que T3.2 y T3.3.** Si se limpian comandos y rutas y después se reinstala ECC bajo el instalador, el instalador los repone y el trabajo se pierde.

---

## 5. TAREAS (formato blueprint — contexto autocontenido)

### T3.1 — Poner ECC bajo control de su instalador [ALTO impacto / ALTO esfuerzo]

**Contexto para una sesión fría:** `C:\Users\PC 1\.claude\ecc\install-state.json` (63,182 B) registra la instalación de ECC en esta máquina. Dice:

```json
"request": { "profile": null, "modules": ["hooks-runtime"], ... },
"resolution": { "selectedModules": ["hooks-runtime"], "skippedModules": [] },
"operations": [ /* 147 entradas, todas kind:"copy-file", moduleId:"hooks-runtime" */ ]
```

**Solo se instaló el módulo `hooks-runtime`**: 147 archivos, que son `hooks\` (4) más `scripts\hooks\` y `scripts\lib\`. Pero en disco hay además **393 skills, 229 agentes, 509 comandos y 114 reglas** que ningún instalador registró: llegaron a mano.

**Por qué importa, y no es cosmético:**
- No hay ruta de actualización. ECC 2.0.0 → 2.1 no se puede aplicar: el instalador solo sabe de 147 archivos.
- No se puede saber en disco de qué fuente vino cada archivo. La biblioteca lo declara; el disco no lo sabe.
- No hay desinstalación limpia ni forma de detectar drift.

Es **la deuda técnica más seria del entorno**, y la menos visible.

**Pasos:**
1. El repo fuente está en `C:\Users\PC 1\ECC` (lo confirma el origen de las 147 operaciones: `C:\Users\PC 1\ECC\... → C:\Users\PC 1\.claude\...`). Verificar que existe y en qué commit está (el registrado es `2bc924faf2f8e893bfe0af86b1931283693c30ae`, repoVersion 2.0.0).
2. Leer los módulos disponibles del instalador (`install.ps1 --help` o los manifiestos en `scripts\lib\install-manifests.js`).
3. **Antes de instalar nada**, hacer diff: qué de lo que hay en disco coincide con el repo ECC y qué no. Lo que no coincida es una de tres cosas: personalización local, otra fuente (catalogo-agentes, claude-ads, community), o basura. **La personalización local es lo que hay que proteger** — un instalador con `ownership: "managed"` la sobrescribe sin avisar.
4. Instalar los módulos faltantes con `--target claude`, en un directorio de prueba primero si el instalador lo permite.
5. Verificar que el censo del Plan 2 (T2.2) devuelve los mismos conteos después.

**Definition of done:** CE-3.1, más `docs\decisiones\ecc-gestionado.md` listando qué quedó gestionado, qué quedó fuera y por qué.

**Rollback:** `.claude\` completo desde `_respaldo-migracion-2026-08-15\claude\`. Es la tarea con mayor superficie de daño del plan entero: se restaura entero, no por partes.

---

### T3.2 — Resolver los ~370 comandos stub [MEDIO / BAJO]

**Contexto:** `.claude\commands\` contiene **509 archivos `.md`**. De ellos, **~370 pesan entre 58 y 99 bytes**: son redirectores a skills homónimas. Los ~139 restantes son comandos reales, de 0.4 a 15.2 KB (los mayores: `sessions.md` 15,221 B, `prp-prd.md` 14,540 B, `prp-plan.md` 14,419 B, `multi-execute.md` 11,342 B).

**Antes de borrar, entender.** Un stub que redirige a una skill puede existir por una razón legítima: dar al usuario un `/comando` memorizable para una skill que se invocaría de otra forma. Borrarlos puede degradar la ergonomía sin que nadie lo note hasta echarlos de menos.

**Pasos:**
1. Muestrear 20 stubs y confirmar que la skill destino existe en `.claude\skills\`.
2. Detectar stubs huérfanos: los que apuntan a una skill que ya no está. Esos sí son basura inequívoca.
3. Consultar `claude-mem` (162 sesiones) qué comandos se han usado de verdad. **Dato, no intuición.**
4. Decidir con criterio escrito: conservar todos (ergonomía), conservar solo los usados, o eliminar solo los huérfanos. La opción conservadora — **eliminar solo huérfanos** — es la recomendada salvo que el conteo de uso diga otra cosa.
5. Aplicar y verificar que los comandos conservados siguen resolviendo.

**Definition of done:** CE-3.2, con criterio escrito y número final.

**Rollback:** `commands\` desde el respaldo fechado.

---

### T3.3 — Arreglar el resolvedor de rutas de los hooks [ALTO / MEDIO]

**Contexto:** cada uno de los 28 hooks de `hooks.json` ejecuta un `node -e "..."` de ~1.1 KB que resuelve `CLAUDE_PLUGIN_ROOT` probando candidatos en orden: `$CLAUDE_PLUGIN_ROOT` → `~/.claude` → `~/.claude/plugins/ecc` → `~/.claude/plugins/ecc@ecc` → `~/.claude/plugins/marketplaces/ecc` → `~/.claude/plugins/everything-claude-code` → ... → `~/.claude/plugins/cache/{ecc,everything-claude-code}/<org>/<version>`.

**Ninguno de los candidatos con `plugins/` existe**, porque ECC no está instalado como plugin. El resolvedor cae en `~/.claude` y funciona. Funciona por el segundo candidato de una lista de diez, no porque alguien lo haya diseñado así.

**Riesgo concreto, no teórico:** si T3.1 instala ECC como plugin de verdad, algunos candidatos empezarán a existir y el orden de resolución cambiará. Los hooks podrían resolver a una ruta distinta a la de hoy, en silencio.

**Pasos:**
1. Fijar `CLAUDE_PLUGIN_ROOT` como variable de entorno de usuario apuntando a la ruta correcta. Es el primer candidato de la lista: fijarlo hace determinista la resolución sin tocar los 49 KB de `hooks.json`.
2. Verificar con `scripts\verificar-hooks.ps1` (Plan 2 T2.4) que los 28 resuelven en el primer candidato.
3. Medir el ahorro: 28 hooks × ~10 candidatos probados × cada invocación de herramienta. Cronometrar antes y después.
4. Evaluar reducir los 49,658 B de `hooks.json`: con `CLAUDE_PLUGIN_ROOT` fijo, el boilerplate sobra. **Pero `hooks.json` es `ownership: "managed"` del instalador de ECC** — editarlo a mano lo pone en conflicto con T3.1. Decidir: o se fija la variable y se deja el archivo intacto (recomendado), o se propone el cambio aguas arriba.

**Definition of done:** CE-3.3, con medición de antes y después.

**Rollback:** eliminar la variable de entorno; el comportamiento vuelve al fallback. `hooks.json` desde el respaldo si se editó.

---

### T3.4 — Decidir el destino de los 478 skills de `.copilot` [MEDIO / MEDIO]

**Contexto:** `C:\Users\PC 1\.copilot\` contiene **478 archivos de skills (1.7 MB)** sobre Cloudflare, Wrangler, Workers, Durable Objects, Turnstile, web-perf, agents-sdk. **Es el activo más grande fuera del entorno Claude, y Claude Code hoy no lo ve.**

**Tres preguntas, en este orden:**
1. **¿Se usa?** Consultar `claude-mem` si algún proyecto toca Cloudflare/Workers. Si ninguno lo hace, portar 478 skills es trabajo por si acaso.
2. **¿Se puede portar?** Formato de skills de Copilot ≠ formato de Claude Code (`SKILL.md` con frontmatter). Portar implica convertir, no copiar.
3. **¿Se debe?** El propio `mcp-servers.json` advierte sobre el coste de contexto. 478 skills más sobre 393 existentes es +122% de superficie para un dominio que puede no usarse.

**Pasos:**
1. Responder las tres con datos, no con criterio.
2. Clasificar en tres cubos: **portar** (las de dominio que algún proyecto usa hoy), **archivar** (comprimir `.copilot\` a un `.zip` fechado y sacarlo del home), **descartar** (duplicadas de lo que ya existe en ECC).
3. Para las de "portar": convertir formato, probar carga, y **solo entonces** añadirlas.
4. Revisar licencias antes de incorporar nada a un repo.

**Definition of done:** CE-3.4, 478 clasificadas, 0 sin decidir.

**Rollback:** `.copilot\` desde `_respaldo-migracion-2026-08-15\entornos-ia\`.

---

### T3.5 — Eliminar cruft [BAJO / BAJO]

**Contexto — inventario exacto del 2026-08-15:**

| Ruta | Volumen | Naturaleza |
|---|---|---|
| `.claude\telemetry\1p_failed_events.*` | 10 archivos, **~12.5 MB** | Eventos de telemetría que nunca se enviaron |
| `.claude\session-env\` | ~370 dirs UUID, **todos vacíos** | Residuo de sesiones |
| `.claude\file-history\` | 59 dirs UUID | Historial de ediciones |
| `.claude\shell-snapshots\` | 62 `.sh` | Snapshots de shell |
| `.claude\plugins\plugin-catalog-cache.json` | 404,474 B | Caché regenerable |
| `.claude\plugins\data\{claude-mem-thedotmack,superpowers-obra}\` | **vacíos** | |
| `.claude\plugins\blocklist.json.21464b62931597bd.tmp` | 414 B | Temporal huérfano |
| `.claude\latest_logs.txt` | 88,616 B | Log suelto en la raíz |
| `.claude\debug\` | vacío | |

**Advertencia sobre `telemetry\`:** son eventos *fallidos*, con contenido de sesión sin auditar. **No se borran sin mirarlos**: pueden contener fragmentos sensibles, y el Plan 0 los movió a `secretos-extraidos\` precisamente por eso. Revisar antes de eliminar definitivamente.

**Advertencia sobre `file-history\`:** es el mecanismo de deshacer ediciones. Borrarlo elimina la posibilidad de revertir cambios recientes. **Conservar al menos los más recientes.**

**Pasos:**
1. Auditar `telemetry\` en busca de contenido sensible; después eliminar.
2. Eliminar dirs vacíos de `session-env\` y `plugins\data\`, y el `.tmp` huérfano.
3. `plugin-catalog-cache.json`: borrar y confirmar que se regenera al siguiente arranque. Si no se regenera, restaurar.
4. `file-history\` y `shell-snapshots\`: aplicar retención (p. ej. últimos 30 días), no borrado total.
5. Medir el tamaño de `.claude\` antes y después.

**Definition of done:** CE-3.5, ≥12 MB liberados, censo del Plan 2 sin cambios en componentes funcionales.

**Rollback:** todo desde el respaldo fechado. Nada de esta tarea es irreversible si el respaldo se verificó.

---

### T3.6 — Coherencia de la sincronización de memoria [ALTO / BAJO]

**Contexto — tres inconsistencias medidas:**

1. **Chroma a medio camino.** `.claude-mem\settings.json` dice `"CLAUDE_MEM_CHROMA_ENABLED": "false"`, pero `chroma-sync-state.json` conserva contadores:
   ```json
   { "BruceWhatsapp":       { "observations": 201, "summaries": 1215, "prompts": 1154 },
     "SistemaLanzamiento":  { "observations": 0,   "summaries": 1223, "prompts": 1177 } }
   ```
   Con **10,163 observaciones** en BruceWhatsapp y **1,203** en SistemaLanzamiento, el índice semántico cubre **201 y 0 observaciones respectivamente** — pero sí casi todos los resúmenes. La búsqueda semántica existe a medias y está apagada: el peor de los tres estados posibles.
2. **`sync_outbox` con 1,238 pendientes** y **`sync_state` vacía**. Una cola que nadie drena.
3. **`sync_launch_exclusions` con 11,828 filas**, casi tantas como observaciones totales (11,502).

**Pasos:**
1. Determinar qué hace cada tabla en claude-mem 13.15.0 antes de tocarla. **No suponer por el nombre.** Consultar la documentación del plugin o el código en `plugins\cache\thedotmack\claude-mem\13.15.0\`.
2. Decidir Chroma: **encenderlo y reindexar completo** (búsqueda semántica sobre 11,502 observaciones, coste de cómputo y espacio) o **apagarlo limpiamente** (borrar `chroma-sync-state.json` para que el estado refleje la realidad). Lo que no puede quedarse es el estado actual.
3. Decidir la cola: drenar los 1,238 pendientes o vaciarla con criterio escrito.
4. Entender qué son las 11,828 exclusiones antes de tocarlas: si es una lista de "no volver a procesar", vaciarla causaría un reprocesamiento masivo.
5. Trabajar siempre con respaldo previo. Esta tarea toca la base de 51.9 MiB que es irreemplazable.

**Definition of done:** CE-3.6, con decisión escrita para cada una de las tres.

**Rollback:** `.db` + `.db-wal` + `.db-shm` desde `_respaldo-migracion-2026-08-15\claude-mem\`, con los procesos detenidos (pids 13160 y 25020, ver Plan 1 T1.0).

---

### T3.7 — Limpiar VSCode: extensión huérfana y ajustes sin dueño [ALTO / BAJO]

**Contexto:**
- `~\.vscode\extensions\extensions.json` registra `anthropic.claude-code` **2.1.205**, pero en disco conviven **2.1.205 y 2.1.233**. Una quedó huérfana y ocupa espacio; peor, hay ambigüedad sobre cuál se carga.
- `AppData\Roaming\Code\User\settings.json` tiene `"github.copilot.nextEditSuggestions.enabled": true` **sin Copilot instalado**. Ajuste sin dueño.
- `keybindings.json` apunta a `claude-vscode.sidebar.open`, namespace de una extensión anterior. **El atajo no hace nada.** (Lo arregla el Plan 1 T1.5; aquí se verifica.)
- `agent-sessions.code-workspace` es `{"folders": []}` — un workspace vacío.

**Pasos:**
1. Confirmar en la UI de VSCode qué versión está activa. Desinstalar la otra por la UI, **no borrando carpetas a mano** — borrar directorios de extensiones deja `extensions.json` inconsistente.
2. Eliminar `github.copilot.nextEditSuggestions.enabled`, o instalar Copilot si se quiere. Un ajuste sin producto es ruido que confunde al siguiente que lea el archivo.
3. Verificar que el keybinding del Plan 1 T1.5 quedó con el ID correcto.
4. Decidir sobre `agent-sessions.code-workspace`: usarlo o borrarlo.
5. Ejecutar el baseline del Plan 2 T2.7 completo.

**Definition of done:** CE-3.7.

**Rollback:** `settings.json` y `keybindings.json` desde `_respaldo-migracion-2026-08-15\vscode\`. La extensión se reinstala desde el Marketplace.

---

### T3.8 — Homogeneizar los 7 proyectos [MEDIO / MEDIO]

**Contexto:** tras el Plan 2 T2.8 los 7 están registrados, pero registrado no es homogéneo. Estado de partida: solo 3 de 7 tienen `.superpowers`; `veo-asesores-claude` no tiene git; `PanelNioval` no tiene `.claude`.

**Pasos:**
1. **`veo-asesores-claude` primero**: `git init`, `.gitignore`, commit inicial. Es el único sin red de seguridad, y todo lo demás puede esperar a que la tenga.
2. `PanelNioval`: `.claude\` con `CLAUDE.md` mínimo.
3. `.superpowers`: **decidir el criterio antes de uniformar.** Que 3 de 7 lo tengan puede reflejar que solo 3 lo necesitan. Uniformar por simetría es cargar cuatro proyectos con configuración que no usan.
4. Verificar que cada proyecto abre en CLI y en VSCode.
5. Registrar excepciones con su razón.

**Definition of done:** CE-3.8, 7/7 homogéneos o con excepción escrita.

**Rollback:** `git checkout` por proyecto; en `veo-asesores-claude`, disponible solo después del paso 1.

---

### T3.9 — Verificación final del entorno optimizado

**Pasos:**
1. Correr `scripts\censo-entorno.ps1` (Plan 2 T2.2) y comparar contra el censo previo al Plan 3. **Toda diferencia debe ser intencional y estar en la tabla PROGRESO.**
2. Correr `scripts\verificar-hooks.ps1`.
3. Ejecutar el baseline de VSCode (Plan 2 T2.7), 5/5.
4. Ejecutar la prueba end-to-end de memoria (Plan 2 T2.6).
5. Confirmar que Cursor, Roo y Windsurf siguen arrancando.
6. Actualizar la tabla PROGRESO y el marcador global del índice.

**Definition of done:** CE-3.9.

---

## 6. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

Fuentes usadas: **claude-mem, catalogo-agentes, ECC, community, superpowers, built-in** — 6 fuentes. Justificación de claude-ads en §6.1.

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T3.2, T3.4 | `claude-mem:mem-search` | skill | claude-mem | **Obligatorio, y aquí es decisorio.** T3.2 y T3.4 se deciden por uso real: qué comandos se han invocado en 162 sesiones, si algún proyecto toca Cloudflare. Sin este dato, ambas tareas se resuelven por intuición. |
| A | T3.6 | `claude-mem:timeline` | skill | claude-mem | Cuándo se apagó Chroma y cuándo dejó de drenarse `sync_outbox`. La correlación con el fallo de captura del 2026-07-09 es una hipótesis a comprobar, no a asumir. |
| A | T3.1, T3.4 | `Explore` | agente | built-in | Diff entre 12,292 archivos del entorno y el repo ECC; barrido de 478 skills de `.copilot`. |
| A | T3.1 | `docs-lookup` / `context7-mcp` | agente / skill | catalogo-agentes / ECC | Documentación real del instalador de ECC 2.0.0 antes de correrlo. Reinstalar a ciegas sobre una instalación viva es el peor escenario del plan. |
| A | T3.5 | `production-audit` | skill | community | "¿Qué se rompe si borro esto?" sobre telemetría, `file-history` y cachés. |
| B | T3.4, T3.6 | `council` | skill | community | Dos decisiones con tradeoff genuino y sin respuesta obvia: portar/archivar/descartar 478 skills, y encender vs. apagar Chroma. Panel de 4 voces. |
| B | Todas | `blueprint` | skill | community | Cada tarea ejecutable por sesión fría. Estándar de la plantilla. |
| B | T3.1 | `architect` | agente | catalogo-agentes | La estructura resultante de `.claude\` (qué es gestionado, qué es local, qué es plugin) es una decisión de arquitectura, no de limpieza. |
| B | T3.3 | `harness-optimizer` | agente | catalogo-agentes | Especialista en optimizar el harness de agentes: es literalmente el objeto de T3.3. |
| C | T3.1 | `configure-ecc` | skill | ECC | La skill de la propia fuente para configurar ECC. Usar el instalador de ECC guiado por la skill de ECC es la vía de menor riesgo. |
| C | T3.5, T3.7 | `powershell-7-expert` | agente | catalogo-agentes | Borrados con retención, medición de tamaño, gestión de extensiones. Especialista del stack real. |
| C | T3.7 | `windows-infra-admin` | agente | catalogo-agentes | Desinstalar una extensión huérfana sin dejar `extensions.json` inconsistente es administración de Windows. |
| C | T3.6 | `database-administrator` | agente | catalogo-agentes | Tocar `sync_outbox` (1,238), `sync_state` y `sync_launch_exclusions` (11,828) en SQLite con esquema no documentado. Con respaldo previo y solo lectura hasta entender. |
| C | T3.6 | `data-engineer` | agente | catalogo-agentes | [OPCIONAL] Si se decide reindexar Chroma sobre 11,502 observaciones: es un pipeline de datos, no una consulta. Condición de uso: si T3.6 paso 2 elige encender. |
| C | T3.2 | `refactor-cleaner` | agente | catalogo-agentes | Eliminar redirectores muertos sin romper los vivos. |
| C | T3.4 | `license-engineer` | agente | catalogo-agentes | 478 skills de terceros que podrían entrar a un repo: la licencia se revisa **antes** de incorporar, no después. |
| C | T3.4 | `skill-creator` | skill | anthropic / built-in | [OPCIONAL] Conversión de formato Copilot → `SKILL.md` con frontmatter. Condición de uso: solo para las clasificadas como "portar". |
| C | T3.8 | `git-workflow-manager` | agente | catalogo-agentes | `git init` en `veo-asesores-claude` y verificación en los otros seis. |
| C | Todas | `superpowers:using-git-worktrees` | skill | superpowers | [OPCIONAL] Si T3.1 a T3.5 se ejecutan en paralelo con varios agentes mutando archivos. Condición de uso: solo si se paraleliza. |
| D | Todas | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio. |
| D | T3.1, T3.3, T3.6 | `security-reviewer` | agente | catalogo-agentes | **Obligatorio**: T3.1 y T3.3 tocan hooks, T3.6 toca una base con 77 observaciones sensibles. |
| D | T3.5 | `security-reviewer` | agente | catalogo-agentes | **Obligatorio**: la telemetría son eventos fallidos con contenido de sesión sin auditar. No se borra sin revisar qué se borra. |
| D | Todas | `silent-failure-hunter` | agente | catalogo-agentes | El modo de fallo de este plan es exactamente el silencioso: se borra algo, todo parece funcionar, y la capacidad perdida se descubre semanas después. |
| D | T3.1, T3.9 | `verification-loop` | skill | ECC | Itera hasta verde tras la reinstalación de ECC. |
| D | T3.9 | `superpowers:verification-before-completion` | skill | superpowers | Gate final del plan y de la migración completa. |
| D | T3.3 | `performance-optimizer` | agente | catalogo-agentes | Medición del ahorro de fijar `CLAUDE_PLUGIN_ROOT`: antes y después, en segundos. Sin medición no hay optimización, hay cambio. |
| D | T3.7 | `dx-optimizer` | agente | catalogo-agentes | [OPCIONAL] Evaluar si el resultado mejora la experiencia real o solo la limpieza del árbol. Condición de uso: al cerrar T3.7. |
| E | Cierre | `pr` / `git-workflow` | skill | ECC | PR con commits `refactor:` y `fix:` en español. |
| E | Cierre | `changelog-generator` | skill | ECC | Un changelog de qué cambió en el entorno, que es lo que la siguiente sesión necesitará leer. |
| E | Cierre | `doc-updater` + `technical-writer` | agente | catalogo-agentes | Actualizar `BIBLIOTECA-HERRAMIENTAS.md` con los conteos reales tras el plan. Si el plan cambia el inventario y la biblioteca no se actualiza, la biblioteca miente. |
| E | Cierre | `claude-mem:standup` | skill | claude-mem | Persistir el estado final del entorno. |
| E | Cierre | `handoff` / `save-session` | skill | ECC | Contexto para después de la migración. |

### 6.1 — Evaluación de claude-ads (justificación obligatoria por escrito)

**claude-ads NO aplica al Plan 3 como ejecutora.** Este plan reinstala módulos, borra cachés, decide sobre skills de Cloudflare y limpia configuración de VSCode. Ninguna de esas actividades es publicitaria.

Se evaluó y descartó un segundo caso frontera, distinto del de los Planes 0 y 1: **T3.4 clasifica 478 skills de `.copilot`, y algunas podrían ser de dominio de marketing o analítica web.** Si al clasificarlas aparecieran skills de tracking publicitario, `audit-tracking (claude-ads)` sería la herramienta indicada para juzgar si duplican lo que la suite ya cubre y deben descartarse en vez de portarse. **Queda como contingencia condicionada.** Condición de activación: que el inventario de `.copilot` en T3.4 devuelva ≥1 skill de dominio publicitario o de tracking. El inventario preliminar (Cloudflare, Wrangler, Workers, Durable Objects, Turnstile, web-perf, agents-sdk) sugiere que no las hay, pero eso se confirma al clasificar, no antes.

---

## 7. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Gate obligatorio | Gate de seguridad | Gate adicional |
|---|---|---|---|
| T3.1 | `code-reviewer` + `architect` | `security-reviewer` **crítico** (hooks, scripts) | Censo idéntico antes/después salvo lo intencional |
| T3.2 | `code-reviewer` + `refactor-cleaner` | — | Comandos conservados resuelven |
| T3.3 | `code-reviewer` + `harness-optimizer` | `security-reviewer` **crítico** (hooks) | Medición antes/después |
| T3.4 | `code-reviewer` + `license-engineer` | `security-reviewer` (código de terceros) | 478/478 clasificadas |
| T3.5 | `code-reviewer` | `security-reviewer` **crítico** (telemetría sin auditar) | 0 componentes funcionales perdidos |
| T3.6 | `database-administrator` | `security-reviewer` **crítico** (77 obs sensibles) | Respaldo verificado inmediatamente antes |
| T3.7 | `code-reviewer` | — | Baseline VSCode 5/5 |
| T3.8 | `git-workflow-manager` | `security-reviewer` | 7/7 registrados |
| T3.9 | `superpowers:verification-before-completion` | `security-reviewer` (cierre de migración) | Los 9 CE en verde |

## 8. BASELINE DE NO REGRESIÓN DEL ENTORNO

Tras **cada** tarea, las tres comprobaciones:

1. **VSCode:** abre, Claude responde.
2. **CLI:** responde; `/agents` lista 229; `/plugin` lista 2.
3. **Terceros:** Cursor, Roo y Windsurf arrancan; el MCP `claude-mem` conecta.

En este plan la tercera comprobación **sube a obligatoria**, porque es el único que borra y reorganiza archivos que esos productos referencian por ruta absoluta.

## 9. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback concreto |
|---|---|---|---|---|---|
| R3.1 | El instalador de ECC sobrescribe personalizaciones locales (`ownership: "managed"`) | **Alta** | **Crítico** | T3.1 paso 3 hace diff **antes** de instalar e identifica lo personalizado | `.claude\` completo desde `_respaldo-migracion-2026-08-15\claude\` |
| R3.2 | Instalar ECC como plugin cambia el orden de resolución de los 28 hooks en silencio | **Alta** | Alto | T3.3 fija `CLAUDE_PLUGIN_ROOT` **antes** de que T3.1 pueda alterar el orden; se verifica tras cada paso | Eliminar la variable; `hooks.json` desde el respaldo |
| R3.3 | Borrar comandos stub elimina atajos que el usuario usa a diario | Media | Medio | T3.2 se decide por uso real medido en `claude-mem`, no por tamaño de archivo | `commands\` desde el respaldo |
| R3.4 | Borrar telemetría destruye evidencia de un incidente sin auditar | Media | Medio | Auditar antes de borrar; el Plan 0 ya los movió a `secretos-extraidos\` | Están movidos, no borrados |
| R3.5 | Vaciar `sync_launch_exclusions` (11,828 filas) dispara reprocesamiento masivo | Media | Alto | T3.6 paso 4 exige entender la tabla antes de tocarla | `.db` + `-wal` + `-shm` desde el respaldo, con ambos procesos detenidos |
| R3.6 | Reindexar Chroma sobre 11,502 observaciones satura CPU o disco | Media | Medio | Decidir con estimación de coste; alternativa limpia es apagarlo del todo | Volver `CLAUDE_MEM_CHROMA_ENABLED` a `false` y borrar el índice |
| R3.7 | Desinstalar la extensión equivocada de VSCode (2.1.205 vs 2.1.233) | Media | Medio | T3.7 paso 1 confirma en la UI cuál está activa antes de tocar nada | Reinstalar desde el Marketplace |
| R3.8 | Portar skills de `.copilot` sin revisar licencia contamina el repo | Baja | Alto | `license-engineer` es gate obligatorio de T3.4 | Revertir el commit; el repo es nuevo, la historia es corta |
| R3.9 | Efecto acumulado: nueve tareas de limpieza y nadie sabe cuál rompió qué | **Alta** | Alto | Baseline **tras cada tarea**, no al final; un commit por tarea | `git revert` de la tarea concreta, no del plan entero |

---

## 10. TABLA PROGRESO

| # | Tarea | Impacto/Esfuerzo | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|---|
| T3.1 | Poner ECC bajo control de su instalador | ALTO / ALTO | PENDIENTE | | |
| T3.2 | Resolver los ~370 comandos stub | MEDIO / BAJO | PENDIENTE | | |
| T3.3 | Arreglar el resolvedor de rutas de los hooks | ALTO / MEDIO | PENDIENTE | | |
| T3.4 | Decidir el destino de los 478 skills de `.copilot` | MEDIO / MEDIO | PENDIENTE | | |
| T3.5 | Eliminar cruft (~12.5 MB) | BAJO / BAJO | PENDIENTE | | |
| T3.6 | Coherencia de la sincronización de memoria | ALTO / BAJO | PENDIENTE | | |
| T3.7 | Limpiar VSCode: extensión huérfana y ajustes | ALTO / BAJO | PENDIENTE | | |
| T3.8 | Homogeneizar los 7 proyectos | MEDIO / MEDIO | PENDIENTE | | |
| T3.9 | Verificación final del entorno optimizado | — | PENDIENTE | | |

**Avance del Plan 3: 0/9 tareas HECHAS (0%).**

**Orden de ejecución recomendado por impacto/esfuerzo:** T3.6 y T3.7 primero (alto impacto, bajo esfuerzo — victorias rápidas que además reducen ruido para el resto), luego T3.1 → T3.3 → T3.2 (la cadena de ECC, en ese orden obligado), luego T3.4 y T3.8, y T3.5 al final porque es el de menor consecuencia y el que más se beneficia de que todo lo demás ya esté estable.
