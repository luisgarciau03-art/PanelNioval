# PLAN 1 — DUPLICAR EL ENTORNO CLAUDE EN EL CLI: PARIDAD REAL Y SANEAMIENTO

**Fecha de diseño:** 2026-08-15
**Repositorio canónico:** `C:\Users\PC 1\migracion-claude-code`
**Rama de trabajo:** `migracion/vscode-a-claude-code`
**Depende de:** Plan 0 cerrado (los seis criterios en verde).
**Modo:** duplicar, no reemplazar. Al terminar, VSCode y CLI funcionan en paralelo. Si un paso rompe VSCode, ese paso está mal diseñado.

---

## 0. EL HALLAZGO QUE REDEFINE ESTE PLAN

El encargo pedía "duplicar el entorno completo de VSCode a Claude Code CLI: mismos plugins, agentes, skills, MCP, hooks, reglas, settings y memoria". El inventario en disco del 2026-08-15 demuestra que **eso ya está hecho, y lo estuvo siempre**, porque VSCode y el CLI no son dos entornos: son dos interfaces sobre el mismo.

**Evidencia, no interpretación:**

1. `C:\Users\PC 1\.claude\ide\` contiene **190 archivos `.lock`**, con nombre igual al puerto y este contenido:
   ```json
   {"pid":24748,"workspaceFolders":[],"ideName":"Visual Studio Code",
    "transport":"ws","runningInWindows":true,"authToken":"<36 chars>"}
   ```
   Es el CLI publicando un WebSocket para que la extensión se conecte. **El CLI es el motor; la extensión es la ventana.**
2. `C:\Users\PC 1\.claude\ecc\install-state.json` declara el destino de instalación de ECC como
   `{"id":"claude-home","target":"claude","kind":"home","root":"C:\\Users\\PC 1\\.claude"}`.
   El instalador ya trató esa ruta como el home de Claude Code CLI.
3. `plugins\installed_plugins.json` y `plugins\known_marketplaces.json` son el registro del CLI, no de la extensión de VSCode.
4. `settings.json` contiene `defaultMode`, `enabledPlugins`, `effortLevel` — claves del CLI, no de la extensión.

**Consecuencia:** abrir una terminal y escribir `claude` da hoy, sin migrar nada, los 229 agentes, 393 skills locales, 509 comandos, 114 reglas, 28 hooks y los 2 plugins. No hay archivos que copiar.

**Lo que este plan hace, entonces:** (a) **probar** esa paridad en vez de suponerla, (b) **arreglar** lo que está roto en el entorno compartido antes de que el uso en dos frentes duplique el daño, y (c) **construir** los pocos equivalentes que sí faltan en terminal.

**Lo único genuinamente exclusivo de VSCode**, según `AppData\Roaming\Code\User\settings.json` leído en disco:

| Ajuste VSCode | ¿Equivalente en CLI? |
|---|---|
| `claudeCode.initialPermissionMode: "bypassPermissions"` | Sí: `defaultMode` en `.claude\settings.json` — **ya está en `bypassPermissions`** |
| `claudeCode.requireApproval: true` | No existe. Es UI del sidebar |
| `claudeCode.autoApprove: false` | No existe. Es UI del sidebar |
| `claudeCode.showDiffBeforeApplying: true` | No existe. En terminal el diff se imprime siempre |
| `claudeCode.preferredLocation: "sidebar"` | No aplica |
| `claudeCode.useTerminal: true` | Ya es terminal |
| `keybindings.json` → `ctrl+shift+numpad_add` | No existe. Equivalente: alias/función de shell (T1.5) |

Y aquí cae la premisa de riesgo del encargo: **no hay peligro de "heredar `bypassPermissions` al CLI", porque el CLI ya lo tiene puesto y lo ha tenido siempre.** El `requireApproval: true` de VSCode era cosmético; debajo, `.claude\settings.json` dice `"defaultMode": "bypassPermissions"`, `"skipDangerousModePermissionPrompt": true`, `Bash(*)`, `PowerShell(*)`, `Write(*)`, `Edit(*)` y `additionalDirectories: ["C:\\Users\\PC 1"]`. La contradicción no es entre VSCode y el CLI: es entre lo que el usuario creía tener y lo que tiene.

---

## 1. Objetivo

Dejar el entorno compartido sano, verificado y usable desde terminal con la misma capacidad que desde el sidebar, sin degradar en nada el funcionamiento de VSCode.

## 2. Alcance

**SÍ entra:** respaldo verificado; reparación de la captura de memoria rota desde 2026-07-09; prueba de paridad del CLI; decisión y documentación de la postura de permisos; fuente de verdad única para MCP y hooks entre Claude/Cursor/Roo; equivalente de terminal para el atajo de teclado; activación consciente de servidores MCP; checklist repetible por proyecto.

**NO entra:** mover código de proyectos (los pasa el usuario a mano). NO entra optimización del entorno (Plan 3). NO entra la batería de pruebas de paridad completa (Plan 2, este plan solo hace la prueba mínima de humo).

## 3. Criterios de éxito (medibles)

| # | Criterio | Comprobación ejecutable | Umbral |
|---|---|---|---|
| CE-1.1 | Existe respaldo verificado y restaurable | Conteo de archivos + apertura de la `.db` copiada en solo lectura | Conteo coincide; `PRAGMA integrity_check` devuelve `ok` |
| CE-1.2 | La captura de memoria vuelve a funcionar | Sesión nueva de Claude → consultar observaciones de esa sesión en la base | ≥1 observación nueva con `created_at` posterior al arreglo |
| CE-1.3 | `CAPTURE_BROKEN` deja de regenerarse | Borrarlo, correr 3 sesiones, comprobar existencia | No reaparece |
| CE-1.4 | El CLI ve lo mismo que la biblioteca declara | `/agents` y `/plugin` en `claude` interactivo | 229 agentes; 2 plugins; 393 skills locales |
| CE-1.5 | La postura de permisos está decidida y escrita | Existe `docs/decisiones/permisos.md` con el modo elegido y el porqué | Documento presente y aplicado en `settings.json` |
| CE-1.6 | Una sola fuente de verdad para MCP y hooks | Documento de arquitectura + configuración aplicada | Sin duplicación no intencional entre `.claude`, `.cursor`, `.roo` |
| CE-1.7 | Atajo de terminal operativo | Ejecutar el alias en PowerShell nuevo | Abre Claude en la carpeta actual |
| CE-1.8 | VSCode sin regresión | Abrir, lanzar Claude, petición simple | Responde, en cada tarea |

## 4. Dependencias

```
T1.0 (respaldo) ──> TODO LO DEMÁS. Sin respaldo verificado no empieza nada.
   │
   ├──> T1.1 (arreglar captura) ──> T1.4 (fuente de verdad única) ──> T1.6 (MCP)
   │                                        │
   ├──> T1.2 (probar paridad) ──────────────┤
   ├──> T1.3 (permisos) ────────────────────┤
   └──> T1.5 (atajo) ───────────────────────┴──> T1.7 (checklist) ──> T1.8 (verificación)
```

**T1.1 antes que cualquier duplicación de uso.** Razón textual del encargo, y es correcta: si se empieza a usar el CLI en paralelo con la captura rota, el fallo se replica en dos frentes en vez de uno.

---

## 5. TAREAS (formato blueprint — contexto autocontenido)

### T1.0 — TAREA CERO: respaldo verificado, con los procesos detenidos

**Contexto para una sesión fría:** `C:\Users\PC 1\.claude-mem\claude-mem.db` pesa 51.9 MiB y contiene 11,502 observaciones, 2,124 resúmenes, 1,779 prompts y 162 sesiones SDK, del 2026-06-11 al 2026-08-14, sobre BruceWhatsapp (10,163 obs), SistemaLanzamiento (1,203) y FinanzasAPPANDROID (136). **Es lo único de esta migración que no se puede reconstruir.** Copiarla con el worker escribiendo produce una copia inconsistente, porque SQLite en modo WAL tiene transacciones vivas en `.db-wal` que no están en `.db`.

**Atención — hay DOS procesos, no uno.** Leído en disco el 2026-08-15:
- `supervisor.json` → `{"worker":{"pid":13160,"startedAt":"2026-08-11T14:03:10.595Z"}}`
- `worker.pid` → `{"pid":13160,"port":38000}`
- `spawn.lock` → `{"pid":25020,"startedAt":"2026-08-15T01:45:10.499Z"}`

El pid **25020** no aparece en el supervisor. Puede ser un spawn huérfano o un segundo worker. **Detener ambos.**

**Pasos:**
1. Cerrar VSCode y toda terminal con `claude` viva.
2. Detener claude-mem por su vía oficial primero (`claude-mem stop` o el comando que exponga la versión 13.15.0). Si no existe, `Stop-Process -Id 13160` y `Stop-Process -Id 25020`.
3. Verificar que ningún proceso mantiene la base abierta: `Get-Process | Where-Object {$_.Id -in 13160,25020}` → vacío. Comprobar además que el puerto 38000 está libre: `Test-NetConnection -ComputerName localhost -Port 38000` → falla.
4. Crear `C:\Users\PC 1\_respaldo-migracion-2026-08-15\` y copiar dentro:
   - `claude-mem\` ← `.claude-mem\claude-mem.db` **+ `.db-wal` + `.db-shm`** (las tres piezas o la copia no sirve)
   - `claude\` ← `C:\Users\PC 1\.claude\` completo
   - `vscode\` ← `AppData\Roaming\Code\User\settings.json` y `keybindings.json`
   - `entornos-ia\` ← `.cursor\`, `.roo\`, `.windsurf\`, `.copilot\`
5. **Verificar el respaldo antes de continuar:**
   - Conteo: `(Get-ChildItem -Recurse -Force "<origen>").Count` vs el del destino, para cada uno de los cuatro bloques.
   - Integridad de la base: abrir la **copia** en solo lectura y correr `PRAGMA integrity_check;` → debe devolver `ok`. Y `SELECT COUNT(*) FROM observations;` → debe devolver 11,502.
6. Reiniciar claude-mem y confirmar que vuelve a levantar.

**Definition of done:** CE-1.1. Sin respaldo verificado no empieza nada — ni de este plan ni de ningún otro.

**Rollback:** no aplica; esta tarea *es* el rollback de todas las demás.

---

### T1.1 — Reparar la captura de memoria (rota desde 2026-07-09)

> ## ⚠ REDEFINIDA EL 2026-08-15 TRAS DIAGNÓSTICO EN VIVO
>
> **La captura NO está rota. Funciona en las dos ventanas.** Ver hallazgo H-5 en §11.
>
> Evidencia: sesiones de prueba con modificación de archivo generaron observaciones
> tanto desde el CLI (11524 `change`, 11525 `discovery`, proyecto `migracion-claude-code`)
> como desde el sidebar de VSCode (11526 `change`, proyecto `BruceWhatsapp`), con
> latencia de **1 segundo**, no de minutos.
>
> `CAPTURE_BROKEN` conserva su mtime del 2026-07-09 — **36 días sin regenerarse**.
> Es una lápida de un fallo que dejó de ocurrir, probablemente cuando el plugin
> se auto-actualizó (`autoUpdate: true`, `lastUpdated` 2026-08-15T00:56:51Z).
>
> **El alcance real de esta tarea, ahora:**
> 1. Confirmar que el camino de `server-service.cjs` bajo Git Bash ya no se invoca.
> 2. Archivar `CAPTURE_BROKEN` en el respaldo (no borrarlo: es evidencia) y verificar
>    que no reaparece en 3 sesiones.
> 3. Implementar la alerta **M-01**: un hook `SessionStart` que avise si el archivo
>    reaparece. El fallo original duró 36 días invisible; esa es la deuda que queda.
> 4. Averiguar la vía oficial de parada de claude-mem en esta instalación —
>    `claude-mem` no está en el PATH, y la Tarea Cero tuvo que matar con
>    `Stop-Process -Force`, dejando locks huérfanos. Está dentro de
>    `plugins\cache\thedotmack\claude-mem\13.15.0\`.
>
> **Lo que YA NO hay que hacer:** reproducir el fallo, actualizar bun, parchear el
> `.cjs`, ni cambiar el shell de los hooks. Nada de eso es necesario.
>
> El contexto original se conserva abajo porque documenta el fallo histórico y
> porque el paso 4 sigue vigente.

**Contexto:** `C:\Users\PC 1\.claude-mem\CAPTURE_BROKEN` contiene, textual:

```
[bun-runner] empty stdin payload received — issue #2188
  script: .claude/plugins/marketplaces/thedotmack/plugin/scripts/server-service.cjs
  payload byte length: 0
  payload type: null (no data event or stream error)
  platform: win32
  shell: C:\Program Files\Git\bin\bash.exe
  stdin TTY: undefined
  timestamp: 2026-07-09T09:32:00.432Z
  CLAUDE_PLUGIN_ROOT: C:\Users\PC 1\.claude\plugins\marketplaces\thedotmack\plugin
```

Lectura del fallo: el runner de **bun** recibe el payload por **stdin** y llega vacío (`byte length: 0`, `type: null`), corriendo bajo **Git Bash en Windows** con `stdin TTY: undefined`. Es un problema de pipe de stdin en la combinación bun + Git Bash + win32, no un fallo de la base ni del modelo.

**Dato que corrige el inventario previo:** el script que falla es **`server-service.cjs`**. Los hooks de Cursor (`.cursor\hooks.json`) invocan **`worker-service.cjs`**, que es otro. No son el mismo fichero y no hay que suponer que fallan igual.

**Pasos:**
1. **Reproducir antes de arreglar.** Lanzar el script a mano con un payload conocido por stdin, desde los tres shells, y anotar cuál pasa:
   - `C:\Program Files\Git\bin\bash.exe` (el del fallo)
   - PowerShell 7
   - `cmd.exe`
   Si funciona en PowerShell y falla en Git Bash, el arreglo es cambiar el shell que invoca el hook, no parchear el script.
2. Comprobar la versión de bun (`bun --version`) contra la que corrige el issue #2188 del repo `thedotmack/claude-mem`. El plugin está en 13.15.0, commit `a697e4a2`, con `autoUpdate: true`: puede que ya exista fix aguas arriba.
3. Elegir el arreglo por orden de menor invasividad:
   a. Actualizar bun y/o el plugin (menos invasivo).
   b. Cambiar el shell del hook a PowerShell 7 si la reproducción lo señala.
   c. Pasar el payload por archivo temporal o argumento en vez de stdin, si el pipe es irrecuperable.
   d. Parche local en el `.cjs` — **último recurso**, porque `autoUpdate: true` lo sobrescribirá en la próxima actualización. Si se toma esta vía, documentarlo y desactivar `autoUpdate` para ese marketplace.
4. Borrar `CAPTURE_BROKEN`, correr 3 sesiones reales de Claude y comprobar en la base que aparecen observaciones nuevas.

**Definition of done:** CE-1.2 y CE-1.3.

**Rollback:** restaurar `plugins\marketplaces\thedotmack\` desde `_respaldo-migracion-2026-08-15\claude\plugins\marketplaces\thedotmack\`. Si se cambió el shell del hook, restaurar `hooks\hooks.json` desde `_respaldo-migracion-2026-08-15\claude\hooks\hooks.json`.

---

### T1.2 — Probar la paridad del CLI (no suponerla)

**Contexto:** §0 argumenta con evidencia de archivos que el CLI ya lee el mismo entorno. Argumentar no es probar. Esta tarea convierte la afirmación en una comprobación ejecutable, y es la que decide si el resto del plan tiene sentido o si hay una sorpresa.

**Pasos:**
1. Terminal nueva (PowerShell 7), en `C:\Users\PC 1\BruceWhatsapp`. Ejecutar `claude`.
2. Dentro de la sesión, recoger la salida de:
   - `/agents` → contar. Esperado: **229**.
   - `/plugin` → esperado: `claude-mem@thedotmack` 13.15.0 y `superpowers@obra` 6.3.0.
   - `/mcp` → anotar qué servidores aparecen realmente conectados.
   - Invocar una skill de cada fuente para probar que cargan, no solo que se listan:
     · `superpowers:brainstorming` (superpowers)
     · una skill de ECC presente en disco, p. ej. `ecc-guide` (ECC)
     · `blueprint` (community)
     · `mem-search` (claude-mem)
     · un agente de catálogo, p. ej. `code-reviewer` (catalogo-agentes)
3. Repetir lo mismo desde el sidebar de VSCode y **comparar las dos salidas**. Diferencia esperada: ninguna, salvo lo relacionado con `ide\*.lock`.
4. Registrar el resultado en `docs/evidencia/paridad-cli-vs-vscode-2026-08-15.md`, con las salidas pegadas.

**Definition of done:** CE-1.4, más el documento de evidencia. Si aparece cualquier diferencia, **se documenta y se convierte en tarea nueva de este plan** antes de seguir.

**Rollback:** tarea de solo lectura. No hay nada que revertir.

---

### T1.3 — Decidir y documentar la postura de permisos

**Contexto:** el encargo lo planteaba como "contradicción entre VSCode y CLI". El inventario muestra que no hay tal contradicción: hay una postura única, y es abierta. `C:\Users\PC 1\.claude\settings.json`:

```json
"permissions": {
  "allow": ["Bash(*)", "PowerShell(*)", "Write(*)", "Edit(*)", "Read(//c/Users/PC 1/**)", ...],
  "defaultMode": "bypassPermissions",
  "additionalDirectories": ["C:\\Users\\PC 1", "\\tmp", ...]
},
"skipDangerousModePermissionPrompt": true
```

Es decir: cualquier comando de shell, cualquier escritura, sobre el home entero del usuario, sin diálogo y con el aviso de modo peligroso silenciado. Los ajustes `claudeCode.requireApproval: true` y `autoApprove: false` de VSCode no cambian esto — son de la UI de la extensión, no del motor.

**El punto que sí es real:** en el sidebar hay un diff visible antes de aplicar (`showDiffBeforeApplying: true`). **En terminal no lo hay.** Así que la misma postura de permisos tiene consecuencias distintas según la ventana, y usar el CLI en paralelo aumenta la superficie sin que ningún archivo haya cambiado.

**Pasos:**
1. Presentar al usuario las tres opciones reales, con su consecuencia, y que elija:
   - **(a) Dejarlo como está.** Máxima velocidad, cero fricción, cero red de seguridad. Es el statu quo.
   - **(b) `defaultMode: "acceptEdits"`** y conservar `allow` amplio. Edits automáticos, comandos de shell nuevos preguntan. Es el punto medio.
   - **(c) Modo por proyecto**: `bypassPermissions` solo en los repos con git y respaldo (BruceWhatsapp, SistemaLanzamiento, FinanzasAPPANDROID, NIOVAL_ANTHROPIC, SUPRATECHWEB, PanelNioval) y modo estricto fuera de ellos. `veo-asesores-claude` **no tiene git**, así que ahí un edit equivocado no tiene rollback.
2. Limpiar el `allow` con independencia de la opción: contiene **~90 entradas**, muchas obsoletas (rutas de `AgenteVentas`, bucles `for f in ...`, fragmentos como `Bash(do echo "=== $f ===")` que no son comandos sino trozos de un bucle). Un `allow` con basura es un `allow` que nadie audita.
3. Escribir `docs/decisiones/permisos.md`: qué se eligió, por qué, qué se descartó y cómo se revierte.
4. Aplicar y verificar en ambas ventanas.

**Definition of done:** CE-1.5. Decisión tomada por el usuario, no por el ejecutor: es su máquina y su tolerancia al riesgo.

**Rollback:** `settings.json` desde `settings.json.bak` o desde el respaldo fechado.

---

### T1.4 — Fuente de verdad única para MCP, hooks y reglas

**Contexto:** **tres entornos escriben en la misma base `claude-mem.db`**, y ninguno sabe de los otros:

| Entorno | Config | Qué invoca |
|---|---|---|
| Claude Code | `.claude\hooks\hooks.json` (28 hooks) | `scripts\hooks\*.js` de ECC |
| Cursor | `.cursor\mcp.json` + `.cursor\hooks.json` (5 hooks) | `bun.exe` sobre `...thedotmack\plugin\scripts\worker-service.cjs` |
| Roo | `.roo\mcp.json` | `node.exe` sobre el mismo `mcp-server.cjs` |

Cursor invoca el worker de claude-mem con **bun**; Roo lo invoca con **node**. La captura rota (T1.1) es un fallo de bun bajo Git Bash. Es decir: **hay dos runtimes distintos escribiendo la misma base, y uno de ellos está roto.** Eso explica por qué el diagnóstico es confuso — la base sigue recibiendo escrituras de un camino mientras el otro falla en silencio.

**Pasos:**
1. Dibujar el mapa actual completo: quién escribe, con qué runtime, disparado por qué evento, en `docs/arquitectura/fuentes-de-verdad.md`.
2. Decidir la fuente de verdad. Propuesta a validar con el usuario: **`.claude\` es la fuente de verdad; Cursor y Roo son consumidores**. Justificación: es el directorio del CLI, es donde ECC instaló el runtime de hooks, y es lo que ambos ya referencian por ruta absoluta.
3. Decidir si Cursor y Roo deben **seguir escribiendo** en la base. Argumento a favor: contexto unificado entre herramientas. Argumento en contra: 77 observaciones sensibles en una base que tres productos distintos leen, y ninguna forma de saber cuál escribió qué. Documentar la decisión.
4. Si se decide unificar runtime: alinear Cursor y Roo al mismo (node o bun, el que sobreviva a T1.1).
5. Verificar que Cursor y Roo siguen funcionando después del cambio. **Duplicar, no reemplazar** aplica también a ellos.

**Definition of done:** CE-1.6, con documento de arquitectura y decisión escrita.

**Rollback:** restaurar `.cursor\`, `.roo\` desde `_respaldo-migracion-2026-08-15\entornos-ia\`.

---

### T1.5 — Equivalente de terminal para el atajo de teclado

**Contexto:** `AppData\Roaming\Code\User\keybindings.json` contiene:

```json
[{ "key": "ctrl+shift+numpad_add", "command": "claude-vscode.sidebar.open" }]
```

El namespace `claude-vscode.*` es de una extensión anterior. La instalada es `anthropic.claude-code`. **Ese atajo ya no hace nada**: no es algo que migrar, es algo que arreglar en VSCode y replicar en terminal.

**Pasos:**
1. Averiguar el ID real del comando en la extensión actual: en VSCode, `Ctrl+Shift+P` → *Preferences: Open Keyboard Shortcuts* → buscar "Claude". Anotar el ID exacto.
2. Corregir `keybindings.json` con el ID correcto, manteniendo la misma tecla. **Esto arregla VSCode, no lo degrada** — cumple el modo duplicar-no-reemplazar en su versión fuerte: VSCode termina mejor que como empezó.
3. Crear el equivalente de terminal en el perfil de PowerShell (`$PROFILE`):
   ```powershell
   function cc { claude @args }
   function ccp { param([string]$p) Set-Location $p; claude }
   ```
   Y documentar que `claude` a secas ya funciona desde cualquier carpeta.
4. Probar en una terminal nueva (el perfil no se recarga en la sesión actual).

**Definition of done:** CE-1.7, más el atajo de VSCode funcionando.

**Rollback:** `keybindings.json` desde el respaldo; el `$PROFILE` se edita quitando las dos funciones.

---

### T1.6 — Activar conscientemente los servidores MCP

**Contexto:** `.claude\mcp-configs\mcp-servers.json` (9,178 B) define **33 servidores MCP**, todos con credenciales `YOUR_*_HERE`. **Es un catálogo de ECC, no una configuración activa.** Los `_comments` del propio archivo lo dicen: *"Copy the servers you need to your ~/.claude.json mcpServers section"*, y advierten: *"Keep under 10 MCPs enabled to preserve context window"*.

Los que sí están activos hoy viven en `~/.claude.json` (no en el snapshot: se excluyó por contener tokens) y en `.cursor\mcp.json` / `.roo\mcp.json`, que solo declaran `claude-mem`.

**Pasos:**
1. Listar los MCP realmente conectados: `/mcp` en sesión del CLI y en el sidebar. Comparar.
2. Contrastar contra el catálogo de 33 y decidir cuáles se quieren activos. Candidatos con valor claro para este entorno, a evaluar: `context7` (documentación viva, ya referenciado por skills de ECC), `github`, `playwright`. Candidatos a descartar por coste de contexto: el resto.
3. Respetar el límite de 10 que advierte el propio archivo.
4. Para cada MCP que se active: la credencial va a variable de entorno, **nunca al JSON** — es la lección del Plan 0.
5. Verificar `/mcp` en ambas ventanas tras el cambio.

**Definition of done:** lista escrita de MCP activos con justificación, ≤10, sin secretos en archivos.

**Rollback:** `~/.claude.json` desde `_respaldo-migracion-2026-08-15\claude\` (nota: el respaldo de T1.0 sí lo incluye, porque copia `.claude\` completo con el worker detenido).

---

### T1.7 — Checklist repetible por proyecto

**Contexto:** el encargo excluye mover código de proyectos, pero **sí pide el checklist repetible** que cada proyecto seguirá para quedar alineado. El estado actual es desparejo:

| Proyecto | `.claude` | `.git` | `.superpowers` |
|---|---|---|---|
| BruceWhatsapp | ✅ | ✅ | ✅ |
| SistemaLanzamiento | ✅ | ✅ | ✅ |
| FinanzasAPPANDROID | ✅ | ✅ | ✅ |
| NIOVAL_ANTHROPIC | ✅ | ✅ | ✗ |
| SUPRATECHWEB | ✅ | ✅ | ✗ |
| veo-asesores-claude | ✅ | **✗** | ✗ |
| PanelNioval | **✗** | ✅ | ✗ |

**Entregable:** `docs/checklist-alineacion-proyecto.md`, ejecutable sin contexto previo, con estos puntos:

1. ¿Tiene `.git`? Si no → `git init` + commit inicial **antes de cualquier otra cosa**. Sin control de versiones, ningún agente con `bypassPermissions` debería tocar la carpeta. Aplica hoy a `veo-asesores-claude`.
2. ¿Tiene `.claude\`? Si no, crearlo con `CLAUDE.md` mínimo. Aplica a `PanelNioval`.
3. ¿Necesita `.superpowers`? Decidir por proyecto: no es obligatorio, y hoy solo 3 de 7 lo tienen. Documentar el criterio en vez de uniformar por inercia.
4. Copiar los planes: `docs\superpowers\plans\` con la copia de solo lectura de los documentos de esta migración.
5. Verificar que el CLI abre en esa carpeta y `claude -p "lista los archivos"` responde.
6. Verificar que VSCode sigue abriendo Claude en esa carpeta.

**Definition of done:** documento escrito y **probado en un proyecto piloto**. Piloto recomendado: `PanelNioval`, porque es el que más le falta y tiene git, así que cualquier error tiene rollback.

**Rollback:** por proyecto, `git checkout` en el repo correspondiente. En `veo-asesores-claude` no hay rollback hasta que el punto 1 se cumpla — motivo por el que es el punto 1.

---

### T1.8 — Verificación final y no regresión

**Pasos:**
1. Correr los ocho criterios de éxito y pegar la salida.
2. Baseline de no regresión completo (§8) en ambas ventanas.
3. Confirmar que la captura de memoria lleva ≥3 sesiones grabando sin reaparecer `CAPTURE_BROKEN`.
4. Actualizar la tabla PROGRESO y el marcador global del índice.

---

## 6. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

Fuentes usadas: **claude-mem, catalogo-agentes, ECC, community, superpowers, built-in** — 6 fuentes. Justificación de claude-ads en §6.1.

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T1.1, T1.4 | `claude-mem:mem-search` | skill | claude-mem | **Obligatorio.** Hay historial real: 11,502 observaciones, 162 sesiones, 53 días. La captura se rompió el 2026-07-09; las sesiones de junio y principios de julio contienen el estado del entorno antes del fallo y muy probablemente el cambio que lo causó. Ninguna otra herramienta puede recuperar eso. |
| A | T1.1 | `claude-mem:timeline` | skill | claude-mem | Ubicar qué pasó alrededor del 2026-07-09: actualización de bun, de plugin, o cambio de shell. La fecha exacta del fallo está en `CAPTURE_BROKEN`; timeline la cruza con la actividad. |
| A | T1.2, T1.4 | `Explore` | agente | built-in | Barridos amplios sobre `.claude\`, `.cursor\`, `.roo\` sin quemar contexto de la sesión principal. |
| A | T1.1 | `docs-lookup` / `context7-mcp` | agente/skill | catalogo-agentes / ECC | Issue #2188 de `thedotmack/claude-mem` y estado de bun en Windows: documentación actualizada, no memoria del modelo. Obligatorio antes de proponer el arreglo. |
| A | T1.3, T1.6 | `repo-scan` | skill | ECC | Inventario del estado real de configuración antes de decidir qué cambiar. |
| B | T1.3, T1.4 | `council` | skill | community | Dos decisiones genuinamente ambiguas con tradeoff real: postura de permisos (velocidad vs. red de seguridad) y si Cursor/Roo siguen escribiendo la base compartida. Panel de 4 voces, no opinión única. |
| B | Todas | `blueprint` | skill | community | Cada tarea debe ejecutarse por una sesión fría sin este documento delante. Es el estándar de la plantilla. |
| B | T1.7 | `superpowers:writing-plans` | skill | superpowers | El checklist por proyecto es en sí un plan ejecutable tarea por tarea. Complementa a blueprint. |
| B | T1.4 | `mcp-developer` | agente | catalogo-agentes | Diseño de la arquitectura MCP: quién es servidor, quién cliente, qué runtime. Especialista, no genérico. |
| B | T1.3 | `architect` | agente | catalogo-agentes | [OPCIONAL] Si la opción (c) de permisos por proyecto se elige, hay que diseñar la jerarquía de settings user/project. Condición de uso: solo si se elige (c). |
| C | T1.0, T1.5 | `powershell-7-expert` | agente | catalogo-agentes | Todo T1.0 y T1.5 es PowerShell: `Stop-Process`, `Test-NetConnection`, `Copy-Item`, `$PROFILE`. Especialista del stack real. |
| C | T1.0 | `windows-infra-admin` | agente | catalogo-agentes | Detener dos procesos, verificar puerto 38000 libre y confirmar que ningún handle mantiene la base abierta es administración de Windows, no scripting. |
| C | T1.1 | `debugger` + `superpowers:systematic-debugging` | agente + skill | catalogo-agentes + superpowers | Bug real con síntoma claro y causa desconocida. **Reproducir antes de arreglar** es el paso 1 de T1.1 precisamente por esta asignación. |
| C | T1.1 | `build-error-resolver` | agente | catalogo-agentes | [OPCIONAL] Si el arreglo pasa por actualizar bun o el plugin y eso rompe la carga. Condición de uso: solo si la vía (a) de T1.1 falla al construir. |
| C | T1.0, T1.5 | `dependency-manager` | agente | catalogo-agentes | [OPCIONAL] Versión de bun vs. la que corrige el issue. Condición de uso: si T1.1 vía (a). |
| C | T1.4, T1.6 | `mcp-builder` | skill | ECC | Convenciones MCP de ECC ya presentes en esta máquina; el catálogo de 33 servidores viene de ahí, así que sus reglas son las que aplican. |
| C | T1.3 | `hookify-rules` | skill | ECC | [OPCIONAL] Si la limpieza del `allow` de ~90 entradas se quiere convertir en reglas mantenibles. Condición de uso: si el usuario elige la opción (b) o (c) de permisos. |
| C | T1.7 | `git-workflow-manager` | agente | catalogo-agentes | El punto 1 del checklist es `git init` en `veo-asesores-claude`, que hoy no tiene control de versiones. |
| C | T1.0 | `database-administrator` | agente | catalogo-agentes | Copia consistente de SQLite en modo WAL: las tres piezas, procesos detenidos, `integrity_check` sobre la copia. Es lo que distingue un respaldo de un archivo copiado. |
| D | Todas | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio en toda tarea. |
| D | T1.0, T1.1, T1.3, T1.4, T1.6 | `security-reviewer` | agente | catalogo-agentes | **Obligatorio**: estas cinco tareas tocan permisos, hooks, MCP o secretos. |
| D | T1.1, T1.4 | `silent-failure-hunter` | agente | catalogo-agentes | El fallo de captura llevaba **36 días sin detectarse**. Ese es el patrón exacto que este agente caza: error tragado, sin propagación, sin alerta. Es la asignación más importante del plan. |
| D | T1.2, T1.8 | `superpowers:verification-before-completion` | skill | superpowers | Gate final. Nada se declara terminado sin salida pegada. |
| D | T1.2 | `qa-expert` | agente | catalogo-agentes | Diseño de la comparación CLI vs. sidebar como prueba y no como impresión. |
| D | T1.8 | `verification-loop` | skill | ECC | Itera hasta verde en vez de reportar y parar. |
| D | T1.0 | `database-reviewer` | agente | catalogo-agentes | Verificación del respaldo: `integrity_check` + conteo esperado de 11,502 observaciones. |
| E | Cierre | `pr` / `git-workflow` | skill | ECC | PR con historial completo, commits convencionales en español. |
| E | Cierre | `doc-updater` | agente | catalogo-agentes | Los documentos de decisión (`permisos.md`, `fuentes-de-verdad.md`, checklist) son entregables del plan, no notas. |
| E | Cierre | `claude-mem:standup` | skill | claude-mem | Persistir qué se arregló y qué se decidió. Con la captura ya reparada (T1.1), esta vez sí se guarda. |
| E | Distribución | `handoff` | skill | ECC | Copia de los planes a `docs\superpowers\plans\` de los 7 proyectos + contexto para el Plan 2. |

### 6.1 — Evaluación de claude-ads (justificación obligatoria por escrito)

**claude-ads NO aplica al Plan 1.** La suite cubre campañas publicitarias: planeación (`ads-plan`), auditoría de cuentas (`ads-audit`, `audit-meta`, `audit-google`), tracking (`audit-tracking`), presupuesto (`audit-budget`, `audit-compliance`, `audit-creative`) y creatividades (`copy-writer`, `creative-strategist`, `visual-designer`, `format-adapter`). El Plan 1 repara un pipeline de captura de memoria, decide permisos, unifica configuración MCP y escribe checklists de entorno. No hay campaña, ni pieza creativa, ni píxel, ni cuenta de anuncios involucrada.

Se evaluó un caso frontera y se descartó: `SistemaLanzamiento` (1,203 observaciones, 28 sesiones) es un proyecto de lanzamiento y su contenido probablemente sí toca marketing. **Pero el Plan 1 no interviene el contenido de ningún proyecto** — solo el entorno de herramientas. Si más adelante se ejecutan planes *sobre* SistemaLanzamiento, la suite claude-ads será obligatoria allí. Aquí no.

---

## 7. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Gate obligatorio | Gate de seguridad | Gate adicional |
|---|---|---|---|
| T1.0 | `code-reviewer` | `security-reviewer` (respalda secretos) | `database-reviewer`: `integrity_check` = ok, 11,502 obs |
| T1.1 | `code-reviewer` + `debugger` | `security-reviewer` (toca hooks) | `silent-failure-hunter`; 3 sesiones sin `CAPTURE_BROKEN` |
| T1.2 | `qa-expert` | — (solo lectura) | Salidas de `/agents`, `/plugin`, `/mcp` pegadas |
| T1.3 | `code-reviewer` | `security-reviewer` **crítico** (permisos) | Decisión firmada por el usuario |
| T1.4 | `code-reviewer` + `mcp-developer` | `security-reviewer` **crítico** (MCP + hooks) | Cursor y Roo siguen funcionando |
| T1.5 | `code-reviewer` | — | Atajo probado en terminal nueva y en VSCode |
| T1.6 | `code-reviewer` + `mcp-developer` | `security-reviewer` **crítico** (MCP + credenciales) | ≤10 MCP activos; 0 secretos en JSON |
| T1.7 | `code-reviewer` | `security-reviewer` | Probado en proyecto piloto |
| T1.8 | `superpowers:verification-before-completion` | `security-reviewer` (cierre) | Los 8 CE en verde |

## 8. BASELINE DE NO REGRESIÓN DEL ENTORNO

Tras **cada** tarea, las dos comprobaciones. Si una falla, no avanza nada:

1. **VSCode:** abre, Claude responde a una petición simple desde el sidebar.
2. **CLI:** `claude -p "dime la fecha de hoy"` responde; `/agents` lista **229**; `/plugin` lista los **2** plugins.

Adicional a partir de T1.1: **Cursor y Roo siguen arrancando** y su MCP `claude-mem` conecta. Son parte del entorno aunque no del encargo, y "duplicar, no reemplazar" también les aplica.

## 9. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback concreto |
|---|---|---|---|---|---|
| R1.1 | Copiar `claude-mem.db` con el worker vivo produce respaldo inconsistente | Alta si se omite el paso | **Crítico** | T1.0 detiene **ambos** pids (13160 y 25020) y verifica puerto 38000 libre | No hay: por eso el respaldo se verifica con `integrity_check` antes de continuar |
| R1.2 | El pid 25020 de `spawn.lock` es un worker vivo que sigue escribiendo tras detener el 13160 | Media | Alto | T1.0 paso 3 verifica explícitamente ambos | Repetir T1.0 completa |
| R1.3 | El parche de T1.1 se pierde con `autoUpdate: true` del marketplace `thedotmack` | Alta si se elige vía (d) | Medio | Preferir vías (a)/(b)/(c); si se usa (d), desactivar `autoUpdate` y documentarlo | Reaplicar parche desde `_respaldo-migracion-2026-08-15\claude\plugins\` |
| R1.4 | Cambiar el shell del hook rompe los otros 27 hooks | Media | Alto | T1.1 cambia solo el hook de captura, no el grafo; baseline tras el cambio | `hooks\hooks.json` desde `_respaldo-migracion-2026-08-15\claude\hooks\hooks.json` |
| R1.5 | Restringir permisos rompe flujos de trabajo del usuario | Media | Medio | La decisión es del usuario (T1.3 paso 1), con las tres opciones y su consecuencia | `settings.json` desde `settings.json.bak` |
| R1.6 | Unificar la fuente de verdad deja a Cursor o Roo sin memoria | Media | Medio | T1.4 paso 5 verifica ambos antes de cerrar | `.cursor\` y `.roo\` desde `_respaldo-migracion-2026-08-15\entornos-ia\` |
| R1.7 | `veo-asesores-claude` sufre un edit destructivo sin git durante el plan | Baja | **Alto** | El punto 1 del checklist (T1.7) es `git init` ahí, antes que nada | **No hay rollback** mientras no tenga git. Es el motivo de que sea el punto 1 |
| R1.8 | T1.2 revela que la paridad NO es completa y el plan cambia de forma | Baja | Medio | T1.2 va temprano, justo por eso | No aplica: es un descubrimiento, no un daño. Se abre tarea nueva |

---

## 10. TABLA PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T1.0 | TAREA CERO: respaldo verificado con procesos detenidos | **HECHA** | `_respaldo-migracion-2026-08-15\tarea-cero-resumen.json` · veredicto `RESPALDO_VERIFICADO` · `integrity_check: ok` · 7/7 bloques con conteo idéntico · 19,342 archivos / 2,621 MB en `claude\` · **Baseline de no regresión 2/2**: CLI `claude -p` → `[PONG]`, exit 0; sidebar de VSCode → respondió la fecha correctamente | 2026-08-15 |
| T1.1 | Reparar la captura de memoria (rota desde 2026-07-09) | PENDIENTE | | |
| T1.2 | Probar la paridad del CLI | **HECHA** | Verificado desde ambas ventanas: **229 agentes / 393 skills / 509 comandos** idénticos, `installed_plugins.json` con los 2 plugins en `scope: user`. Contenido de la extensión inspeccionado: **sin `agents\`, `skills\`, `hooks\`, `plugins\` ni `rules\` propios** — solo `extension.js`, `webview\`, el esquema de settings y `claude.exe`. **Paridad de configuración: total.** Hallazgo H-7: brecha de versión de binario | 2026-08-15 |
| T1.9 | **Alinear versiones de binario** (2.1.141 npm vs 2.1.233 extensión) | **HECHA** | `npm install -g @anthropic-ai/claude-code@latest` → *"changed 2 packages in 43s"* · `claude --version` → **2.1.233 (Claude Code)**, idéntica a la empaquetada en la extensión. Rollback disponible: `npm install -g @anthropic-ai/claude-code@2.1.141` | 2026-08-15 |
| T1.3 | Decidir y documentar la postura de permisos | **HECHA** — *reverificación v2 pendiente de reinicio* | **v1 (20 reglas)** instalada 17:03 y verificada en vivo con control bidireccional: `docs\entorno\2026-08-15-verificacion-en-vivo-deny-hooks.md`. **v2 (26 reglas)** aplicada 17:58 desde `docs\entorno\settings.deny.propuesto.json`: JSON válido, **deny=26 · allow=93**, `defaultMode` y los 8 `additionalDirectories` intactos. Respaldo `settings.json.bak-20260815-175855`. **Criterio de salida NO verificable en la sesión que aplicó el cambio** (permisos cacheados desde antes de las 17:03): `.claude.json` y `.claude.json.bak` se leyeron ambos. Requiere reinicio + reprueba — ver `docs\entorno\2026-08-15-aplicacion-deny-v2.md` | 2026-08-15 |
| T1.4 | Fuente de verdad única para MCP, hooks y reglas | PENDIENTE | | |
| T1.5 | Equivalente de terminal para el atajo de teclado | **HECHA** | `scripts\instalar-atajos-claude.ps1` ejecutado. Perfil creado en `C:\Users\PC 1\Documents\WindowsPowerShell\profile.ps1` (no existía). Instalados `cc`, `ccc`, `ccp <ruta>` y el atajo de teclado **`Ctrl+Alt+C`** vía PSReadLine. Bloque delimitado por marcas `BEGIN`/`END`, desinstalable. **El atajo de VSCode NO requería arreglo**: `claude-vscode.sidebar.open` es el comando vigente en 2.1.233 (ver corrección en §11) | 2026-08-15 |
| T1.6 | Activar conscientemente los servidores MCP | PENDIENTE | | |
| T1.7 | Checklist repetible por proyecto | PENDIENTE | | |
| T1.8 | Verificación final y no regresión | **PARCIAL** | **Baseline 2/2 tras la actualización a 2.1.233**: terminal (`cc` → sesión interactiva, primer arranque, respondió la fecha correctamente) y sidebar de VSCode (respondió idéntico). Confirmado por el usuario: *"ambas coinciden"*. Pendiente el resto de la verificación del plan (T1.3, T1.4, T1.6, T1.7) | 2026-08-15 |

**Avance del Plan 1: 5/10 tareas HECHAS (50%).**

> ## ★ EL ENCARGO ORIGINAL ESTÁ CUMPLIDO — 2026-08-15
>
> *"Migrar-duplicar el entorno Claude completo de VSCode a Claude Code (CLI): mismos plugins, agentes, skills, MCP, hooks, reglas, settings y memoria, sin desmontar VSCode."*
>
> | Componente | Estado |
> |---|---|
> | Agentes | **229**, compartidos. Verificado desde ambas ventanas |
> | Skills | **393** locales + 31 de plugins = 424, compartidos |
> | Comandos | **509**, compartidos |
> | Reglas | **114** en 21 lenguajes, compartidas |
> | Hooks | **28** en 7 eventos, compartidos |
> | Plugins | **2** (`claude-mem@thedotmack` 13.15.0, `superpowers@obra` 6.3.0), `scope: user`, compartidos |
> | Marketplaces | **2** (`thedotmack`, `obra`), compartidos |
> | MCP | Mismo `~/.claude.json`, compartido |
> | Settings | Mismo `.claude\settings.json`, con el mismo esquema de validación |
> | Memoria | Misma `claude-mem.db`, 11,525 observaciones, captura viva en ambas |
> | **Motor** | **`claude.exe` 2.1.233 en las dos** ← lo único que hubo que alinear |
> | Atajo | `Ctrl+Shift+Num+` en VSCode · `Ctrl+Alt+C`, `cc`, `ccc`, `ccp` en terminal |
>
> **VSCode no se desmontó ni se degradó.** No se modificó `AppData\Roaming\Code\User\settings.json`, ni `keybindings.json`, ni la extensión, ni `.claude\settings.json`. Los únicos cambios en el sistema fueron: actualizar el paquete npm, y **crear** un `profile.ps1` que no existía.
>
> **Por qué costó tan poco:** porque no había dos entornos. `C:\Users\PC 1\.claude\` es el directorio de configuración de Claude Code, y la extensión de VSCode es una ventana web que ejecuta el mismo binario sobre la misma carpeta. La migración consistió en **descubrir que ya estaba hecha** y corregir la única divergencia real: la versión del binario.

---

## 12. T1.9 — ALINEAR VERSIONES DE BINARIO [tarea nueva, deriva de H-7]

**Contexto:** `claude` en terminal resuelve a `C:\Users\PC 1\AppData\Roaming\npm\claude.cmd`, una instalación global de npm en la **2.1.141**. La extensión de VSCode ejecuta su propio `claude.exe` en la **2.1.233**. Misma configuración, motores distintos.

**Pasos:**
1. Anotar la versión actual para poder volver: `claude --version` → `2.1.141`.
2. Actualizar la instalación global de npm:
   ```powershell
   npm install -g @anthropic-ai/claude-code@latest
   claude --version
   ```
3. Comprobar que la versión resultante iguala o supera la de la extensión (2.1.233).
4. Baseline completo: `claude -p "responde exactamente: PONG"` en terminal, y una petición simple en el sidebar.
5. Verificar que los 28 hooks siguen ejecutándose y que la captura de memoria sigue viva (`verificar-captura.py --antes` / sesión con edición / `--vigilar 5`).

**Riesgo:** bajo. La actualización **converge** hacia la versión que el sidebar ya ejecuta sin problemas desde hace tiempo; no introduce un motor no probado en esta máquina.

**Rollback:** `npm install -g @anthropic-ai/claude-code@2.1.141`.

**Nota aparte:** hay **dos versiones de la extensión en disco** — `anthropic.claude-code-2.1.205-win32-x64` y `-2.1.233-win32-x64` — con un `claude.exe` de 320 MB cada una: **~640 MB duplicados** por una desinstalación incompleta. `extensions.json` registra la 2.1.205 pese a que la 2.1.233 es la instalada. Limpieza para el Plan 3, T3.7.

---

## 11. HALLAZGOS DE LA EJECUCIÓN DE T1.0 (2026-08-15)

El respaldo verificado destapó cuatro datos que **corrigen el diseño** de tareas posteriores. Se registran aquí porque cambian lo que esas tareas deben hacer.

### H-1 — La captura de memoria NO está muerta: está a medias

Conteos del inventario del 2026-08-14 vs. los de la base respaldada el 2026-08-15:

| Tabla | 2026-08-14 | 2026-08-15 | Δ |
|---|---:|---:|---:|
| `observations` | 11,502 | **11,523** | **+21** |
| `session_summaries` | 2,124 | **2,130** | +6 |
| `user_prompts` | 1,779 | **1,782** | +3 |
| `sdk_sessions` | 162 | **164** | +2 |
| `sync_outbox` | 1,238 | **1,240** | +2 |

**La base recibió 21 observaciones nuevas en 24 horas.** `CAPTURE_BROKEN` es del 2026-07-09 y sigue en disco, pero algo está escribiendo.

**Consecuencia para T1.1:** el diagnóstico no es "la captura está rota". Es **"un camino de captura está roto mientras otro funciona"**, que es exactamente la hipótesis de T1.4 (dos runtimes sobre la misma base: `bun` en los hooks de Cursor, `node` en el MCP de Roo, y `server-service.cjs` bajo Git Bash fallando). El paso 1 de T1.1 —reproducir antes de arreglar— pasa de recomendable a **imprescindible**: hay que identificar **qué** camino escribe y **cuál** falla, no arreglar "la captura".

### H-2 — El índice de texto completo está íntegro; Chroma es menos grave de lo estimado

`observations_fts` = **11,523**, idéntico a `observations`. Lo mismo en `session_summaries_fts` (2,130) y `user_prompts_fts` (1,782).

**La búsqueda de `mem-search` funciona sobre FTS5 de SQLite, no sobre Chroma.** Es decir: la etapa A de los cuatro planes —que depende de `mem-search`— **no está degradada**. Chroma solo aportaría búsqueda semántica por embeddings encima de una búsqueda léxica que sí está completa.

**Consecuencia para T3.6:** la opción "apagar Chroma limpiamente" sube de aceptable a **recomendada por defecto**. Reindexar 11,523 observaciones tiene coste real y el beneficio marginal es menor de lo que parecía cuando se creía que la búsqueda estaba coja.

### H-3 — `.claude\` es 4.6× lo inventariado: 2,392 MB (corregido)

> **CORRECCIÓN 2026-08-15 (medición en vivo).** La versión anterior de este hallazgo decía *"`.claude\` es 2,621 MB y 19,342 archivos"*. **Esa cifra es el total del RESPALDO**, no de `.claude\`. El respaldo contiene `claude` + `claude-mem` + `entornos-ia` + `vscode`.
>
> | Medición | MB |
> |---|---:|
> | Respaldo completo (lo que decía 2,621) | 2,603 |
> | └ `respaldo\claude` (copia del 14/08) | 2,430.6 |
> | └ `respaldo\claude-mem` | 171.3 |
> | └ `respaldo\entornos-ia` | 1.7 |
> | **`.claude\` vivo, antes del saneamiento** | **2,392** |
> | **`.claude\` vivo, tras apartar cache obsoleto** | **959** |
>
> Los ~38 MB entre `respaldo\claude` (2,430.6) y el vivo (2,392) son lo que el entorno soltó entre el respaldo y la medición — coherente con los 30 MB de `file-history` + telemetría.
>
> **El hallazgo de fondo no cambia:** el snapshot de diseño subestimaba el entorno por 4.6×. Lo que cambia es la cifra, y la lección es la misma que el propio hallazgo enuncia — no reutilizar un número medido sobre un universo para describir otro.

El snapshot del 2026-08-14 sobre el que se diseñaron estos planes copió 521 MB y 12,292 archivos, porque excluía `node_modules`, `.git`, `cache` y `Cache`. El respaldo completo tiene **19,342 archivos y 2,603 MB**.

**~7,050 archivos y ~2.1 GB nunca se inventariaron.** Son los clones de los marketplaces `obra` y `thedotmack` con su `.git` y sus dependencias.

Los conteos que sí se verificaron (229 agentes, 393 skills, 509 comandos, 114 reglas, 28 hooks) están en carpetas que el snapshot sí cubrió, así que **las conclusiones no cambian**. Lo que cambia es lo que se puede afirmar: cualquier frase del tipo "el entorno son 521 MB" es falsa.

**Consecuencia para T2.2:** `censo-entorno.ps1` debe medir sobre el entorno vivo y reportar **ambos** números —con y sin `node_modules`/`.git`— o volverá a producir una cifra engañosa.

### H-4 — `.claude-mem\` pesa 171 MB, de los cuales la base es 52

88 archivos, 171.3 MB. `claude-mem.db` son 51.91 MB. **Quedan ~119 MB sin identificar** en una carpeta que se creía de ~52 MB. Candidato principal: un índice de Chroma que sigue en disco pese a `CLAUDE_MEM_CHROMA_ENABLED: "false"`.

**Consecuencia para T3.6:** antes de decidir sobre Chroma hay que saber qué son esos 119 MB. Si es el índice, la decisión "apagar limpiamente" incluye liberarlos.

### Nota operativa sobre el WAL

`claude-mem.db-wal` quedó en **4,096 KB** tras la parada. El worker se detuvo con `Stop-Process -Force`, no con un cierre limpio, así que SQLite no hizo checkpoint: hay hasta 4 MB de transacciones en el WAL que no están en el `.db`. **El respaldo es válido porque copió las tres piezas** (`.db`, `-wal`, `-shm`) y el `integrity_check` se ejecutó sobre el conjunto. Pero si alguien copia solo el `.db` de ese respaldo, pierde esas transacciones. Queda advertido en el rollback de todas las tareas que restauren la base.

### H-5 — La captura funciona en las dos ventanas. `CAPTURE_BROKEN` es una lápida

Diagnóstico ejecutado en vivo el 2026-08-15, cuatro sesiones de prueba:

| Ventana | Acción | Observaciones generadas |
|---|---|---|
| CLI (`claude -p`) | preguntar la fecha | 0 |
| CLI (`claude -p`) | responder `PONG` | 0 |
| CLI (`claude -p`) | **crear** un archivo y leerlo | **+2** (11524 `change`, 11525 `discovery`) |
| VSCode sidebar | **leer** un archivo | 0 |
| VSCode sidebar | **crear** un archivo y leerlo | **+1** (11526 `change`) |

**Conclusión doble:**

1. **Las observaciones se derivan de modificación de archivos, no de conversación.** Una sesión que solo lee, o que solo responde una pregunta, produce cero observaciones **de forma legítima**. Cualquier prueba de memoria que no modifique un archivo dará un falso negativo.
2. **Los dos caminos —CLI y sidebar— escriben correctamente.** La latencia real es de **1 segundo** (`user_prompts` sube a las 00:33:40 local, la observación 11526 tiene `created_at` 06:33:41Z), no de minutos.

**Sobre `CAPTURE_BROKEN`:** mtime del 2026-07-09, **36 días sin regenerarse**. El fallo dejó de ocurrir. Hipótesis más probable: se resolvió con una auto-actualización del plugin (`autoUpdate: true` en el marketplace `thedotmack`, `lastUpdated` 2026-08-15T00:56:51Z). Queda por confirmar en T1.1 paso 1.

**Coste metodológico de este hallazgo, para que no se repita:** tres veredictos consecutivos de "captura muerta" fueron falsos, por tres causas distintas — medir sin esperar el cierre de sesión, medir con la sesión aún abierta, y comparar una prueba de escritura contra una de lectura. La sonda `scripts\verificar-captura.py` se reescribió (v2) para que no pueda afirmar que algo está muerto: solo distingue `CAPTURA VIVA`, `SIN CIERRE DETECTADO` y `SIN CAMBIOS TODAVÍA`. **Esa disciplina es requisito del Plan 2 T2.6.**

### H-6 — Atribución de proyecto: verificar

La observación 11526 se generó desde el sidebar de VSCode y quedó atribuida a `project: BruceWhatsapp`. Queda por confirmar si VSCode había restaurado ese workspace al reabrirse (los lockfiles de `.claude\ide\` registran `"workspaceFolders": ["c:\\Users\\PC 1\\BruceWhatsapp"]`, así que es plausible) o si la atribución de proyecto es incorrecta.

**Si fuera incorrecta, es grave:** `mem-search` filtra por proyecto, y la etapa A de los cuatro planes depende de esa herramienta. Verificación: localizar dónde quedó `prueba-captura-vscode.txt`. **Pasa al Plan 2 como comprobación obligatoria de T2.6.**

### H-7 — DOS INSTALACIONES DE CLAUDE CODE, 92 VERSIONES DE DIFERENCIA ★

**Este es el único trabajo de migración real que existe en todo el encargo.**

Verificado el 2026-08-15 ejecutando el mismo bloque de comprobación desde las dos ventanas:

| Ventana | Binario | Versión |
|---|---|---|
| **Terminal** (`claude`) | `C:\Users\PC 1\AppData\Roaming\npm\claude.cmd` — instalación global de **npm** | **2.1.141** |
| **VSCode sidebar** | `…\.vscode\extensions\anthropic.claude-code-2.1.233-win32-x64\resources\native-binary\claude.exe` (320 MB, empaquetado en la extensión) | **2.1.233** |

**Configuración: idéntica y compartida.** Confirmado desde el sidebar: 229 agentes, 393 skills, 509 comandos, y `installed_plugins.json` con `claude-mem@thedotmack` 13.15.0 y `superpowers@obra` 6.3.0, ambos con `"scope": "user"` e `installPath` bajo `.claude\plugins\cache\`. Los mismos números que el censo en disco.

**Prueba estructural de que no hay nada que copiar:** el contenido completo de la extensión es `extension.js` (2.8 MB, pegamento con VSCode), `webview/` (5.3 MB, la interfaz), `claude-code-settings.schema.json` (212 KB, el esquema de `.claude\settings.json`), recursos gráficos, y `claude.exe`. **No hay `agents\`, `skills\`, `hooks\`, `plugins\`, `rules\` ni `commands\` dentro de la extensión.** El sidebar es una ventana web sobre el mismo programa; toda la capacidad viene de `~/.claude`.

**Qué implica la brecha de versión:** ambas ventanas comparten configuración pero la interpretan con motores distintos. Diferencias posibles en el esquema de `settings.json`, en el contrato de hooks, en la resolución de plugins y en las correcciones acumuladas en 92 versiones. Es una fuente de "en el sidebar funciona y en terminal no" difícil de diagnosticar precisamente porque la configuración es la misma.

**Acción:** alinear la instalación de npm a la versión de la extensión. Ver T1.9.

### Corrección — el atajo de VSCode NO estaba roto

En una versión anterior de este documento se afirmó que `keybindings.json` apuntaba a `claude-vscode.sidebar.open`, "namespace de una extensión anterior", y que el atajo estaba muerto. **Era falso.**

El `package.json` de la extensión 2.1.233 declara ese comando como vigente:

```
claude-vscode.sidebar.open        Claude Code: Open in Side Bar
```

Se confundió el **ID de la extensión** (`anthropic.claude-code`) con el **prefijo de sus comandos** (`claude-vscode.`). Son cosas distintas. El atajo `Ctrl+Shift+Num+` es correcto y debería funcionar.

Dato relacionado: los atajos por defecto de la extensión son casi todos `cmd+…` (macOS). En Windows solo quedan `alt+k` y `ctrl+alt+f`, lo que explica que hiciera falta uno personalizado.

**Comandos disponibles para atajos, por si se quieren más:** `claude-vscode.sidebar.open`, `.editor.open`, `.editor.openLast`, `.window.open`, `.terminal.open`, `.newConversation`, `.reopenClosedSession`, `.createWorktree`, `.toggleFocusView`, `.insertAtMention`, `.installPlugin`.

### Estado del worker

`workerReiniciado: "n/a"` — `claude-mem` no está en el PATH, así que el worker **quedó detenido**. Debe arrancar solo con la próxima sesión de Claude. **Verificarlo antes de dar T1.0 por completamente cerrada.**
