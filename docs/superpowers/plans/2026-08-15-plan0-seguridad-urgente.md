# PLAN 0 — SEGURIDAD URGENTE: SECRETOS EXPUESTOS EN EL ENTORNO

**Fecha de diseño:** 2026-08-15
**Repositorio canónico:** `C:\Users\PC 1\migracion-claude-code`
**Rama de trabajo:** `migracion/vscode-a-claude-code` (desde `main` actualizado, NUNCA `main`)
**Precedencia:** este plan se ejecuta ANTES que los Planes 1, 2 y 3. Ninguna tarea de los otros planes arranca con el Plan 0 abierto.
**Modo:** duplicar, no reemplazar. Ningún paso de este plan puede dejar VSCode sin abrir Claude.

---

## 0. Por qué existe este plan

No estaba en el encargo. Se creó porque el inventario del entorno destapó secretos vivos en archivos que están a punto de entrar a un repositorio git, y un plan de migración que empieza commiteando credenciales no es una migración: es un incidente.

Hallazgo detonante, leído en disco el 2026-08-15 en `C:\Users\PC 1\.claude\settings.json`:

```json
"allow": [
  "...",
  "Bash(RAILWAY_TOKEN=\"c0d59fb0-7022-4922-a10e-425db4bf0616\" railway variables)",
  "..."
]
```

Un permiso aprobado en su día se guardó con el secreto embebido en el patrón. El token está en texto plano, en un archivo que Claude Code lee en cada arranque, y ahora también en el snapshot bajo `_inventario\`.

---

## 1. Objetivo

Dejar el entorno sin secretos expuestos y sin rutas por las que un secreto pueda llegar a la historia de git, antes de tocar cualquier otra cosa.

## 2. Alcance

**SÍ entra:** rotación del token de Railway; depuración de `settings.json` y `settings.local.json`; purga del snapshot `_inventario\`; `.gitignore` del repositorio; auditoría de las 77 observaciones marcadas como sensibles o de seguridad en `claude-mem.db`; barrido de los 190 `authToken` de `.claude\ide\`.

**NO entra:** cambiar la postura de permisos del CLI (`defaultMode`, `Bash(*)`, `additionalDirectories`) — eso es la Tarea 1.3 del Plan 1, es una decisión de diseño y no una fuga. Aquí solo se saca el secreto del archivo.

**NO entra:** mover código de proyectos.

## 3. Criterios de éxito (medibles)

| # | Criterio | Comprobación ejecutable | Umbral |
|---|---|---|---|
| CE-0.1 | El token de Railway ya no es válido | `railway whoami` con el token viejo | Falla con 401/403 |
| CE-0.2 | No queda el token en ningún archivo del entorno | `Select-String -Path "C:\Users\PC 1\.claude\*.json","C:\Users\PC 1\migracion-claude-code\**\*" -Pattern "c0d59fb0-7022-4922-a10e-425db4bf0616" -SimpleMatch` | 0 coincidencias |
| CE-0.3 | El repo no puede commitear el snapshot | `git -C "C:\Users\PC 1\migracion-claude-code" status --porcelain --ignored \| Select-String "_inventario"` | Aparece como ignorado, nunca como untracked |
| CE-0.4 | Ningún archivo con `authToken`, `credentials` o `.env` queda dentro del árbol versionable | `git -C "..." ls-files \| Select-String -Pattern "credential\|authToken\|\.env\|\.claude\.json"` | 0 coincidencias |
| CE-0.5 | Las 77 observaciones sensibles están clasificadas | Query SQL sobre la copia de respaldo (ver T0.5) | Tabla de triage con 77 filas, 0 sin decisión |
| CE-0.6 | VSCode sigue funcionando | Abrir VSCode, lanzar Claude, pedir `dime la fecha de hoy` | Responde |
| CE-0.7 | El CLI sigue funcionando | `claude -p "dime la fecha de hoy"` | Responde |

## 4. Dependencias

```
T0.1 (rotar token) ──┐
                     ├──> T0.3 (.gitignore) ──> T0.6 (verificación final)
T0.2 (purgar snapshot)┘                              ^
T0.4 (barrido settings.local.json) ──────────────────┤
T0.5 (triage de observaciones sensibles) ────────────┘
```

T0.1 y T0.2 son independientes entre sí y pueden ir en paralelo. T0.3 requiere que T0.2 haya terminado, o el `.gitignore` se escribe contra un árbol que aún cambia. T0.6 cierra.

---

## 5. TAREAS (formato blueprint — contexto autocontenido)

### T0.1 — Rotar el token de Railway y sacarlo de `settings.json`

**Contexto para una sesión fría:** en `C:\Users\PC 1\.claude\settings.json`, dentro del array `permissions.allow`, existe una entrada de texto que contiene un token de API de Railway en claro. Ese archivo lo lee Claude Code CLI en cada arranque y lo lee también la extensión de VSCode, porque ambos comparten el mismo directorio de configuración. El token es `c0d59fb0-7022-4922-a10e-425db4bf0616`. Se desconoce desde cuándo está ahí y a qué proyectos de Railway da acceso.

**Pasos:**
1. Antes de borrar nada, determinar el alcance: entrar a Railway → Account Settings → Tokens, e identificar a qué workspace/proyectos pertenece ese token y qué permisos tiene.
2. Revocarlo en Railway. Emitir uno nuevo si hay automatizaciones que lo usaban.
3. Guardar el nuevo token en una variable de entorno de usuario de Windows (`setx RAILWAY_TOKEN "<nuevo>"`), NUNCA en `settings.json`.
4. Editar `settings.json` y eliminar la entrada completa `"Bash(RAILWAY_TOKEN=\"...\" railway variables)"` del array `allow`. No sustituirla por una versión con el token nuevo: el patrón correcto es `"Bash(railway variables)"` sin secreto.
5. Validar que el JSON sigue siendo válido: `Get-Content "C:\Users\PC 1\.claude\settings.json" | ConvertFrom-Json`.

**Definition of done:** `railway whoami` con el token viejo falla; el nuevo token no aparece en ningún archivo; `settings.json` parsea; VSCode y CLI arrancan.

**Rollback:** restaurar `settings.json` desde `C:\Users\PC 1\.claude\settings.json.bak` (ya existe en disco, 7,191 B) o desde el respaldo fechado de la Tarea Cero del Plan 1. La rotación del token no tiene rollback ni lo necesita: un token revocado es el estado deseado.

---

### T0.2 — Purgar el snapshot `_inventario\` de material sensible

**Contexto:** el 2026-08-14 se copió `C:\Users\PC 1\.claude\` a `C:\Users\PC 1\migracion-claude-code\_inventario\claude-snapshot\` mediante robocopy, para que una sesión sin acceso a la carpeta protegida pudiera inventariarla. Las exclusiones (`/XF ".credentials.json" "*.key" "*.pem" ".env*"`) no cubrieron varios patrones. El snapshot vive dentro de lo que será un repositorio git.

**Inventario exacto de lo que hay que sacar** (rutas relativas a `_inventario\`):

| Ruta | Tamaño | Por qué |
|---|---|---|
| `claude-snapshot\.credentials.json.tmp.ece6654c` | 524 B | El `/XF` no cubrió el sufijo `.tmp.<hash>` |
| `claude-snapshot\backups\.claude.json.backup.*` (5 archivos) | ~58 KB c/u | Copias de `~/.claude.json`: tokens OAuth y `env` de servidores MCP |
| `claude-snapshot\backups\.claude.json.corrupted.*` (3 archivos) | 44–46 KB | Lo mismo, versiones corruptas |
| `claude-snapshot\ide\*.lock` | 190 archivos, 156–193 B | Cada uno contiene un campo `authToken` de 36 caracteres |
| `claude-snapshot\settings.local.json` | 33,550 B | Permisos locales sin auditar; ver T0.4 |
| `claude-mem-config\.env` | 160 B | El `/XF` de esa copia solo excluyó `*.db*` |
| `claude-snapshot\telemetry\1p_failed_events.*` | ~12.5 MB | No es secreto, pero son eventos de telemetría fallidos con contenido de sesión sin auditar |

**Pasos:**
1. Crear `C:\Users\PC 1\_respaldo-migracion-2026-08-15\secretos-extraidos\` FUERA del repositorio.
2. Mover (no copiar) cada ruta de la tabla a esa carpeta, preservando estructura.
3. Verificar que el snapshot ya no contiene ninguna: barrido con `Get-ChildItem -Recurse -Force` filtrando por los patrones `credential`, `authToken`, `.env`, `.claude.json`.
4. Dejar en el snapshot un `LEIDO-Y-PURGADO.md` que liste qué se sacó y a dónde, para que la trazabilidad no se pierda.

**Definition of done:** CE-0.4 en verde. El snapshot conserva los 229 agentes, 393 skills, 509 comandos, 114 reglas y los 28 hooks — no se toca nada de eso, es el objeto del inventario.

**Rollback:** los archivos están movidos, no borrados. Restaurar es un `Move-Item` inverso desde `secretos-extraidos\`.

---

### T0.3 — `.gitignore` y verificación de que el repositorio no ve el snapshot

**Contexto:** `C:\Users\PC 1\migracion-claude-code` todavía no es un repositorio git, o lo es sin historia. El snapshot pesa ~521 MB y 12,292 archivos. Ni depurado debe versionarse: es un insumo de lectura de un momento concreto, no fuente.

**Contenido mínimo del `.gitignore`** (raíz del repo):

```gitignore
# Snapshot de inventario — insumo de lectura, nunca fuente de verdad
_inventario/

# Nunca, bajo ninguna circunstancia
*.credentials.json*
.credentials.json*
.claude.json*
*.lock
.env
.env.*
*.key
*.pem
*token*.json

# Ruido
node_modules/
*.log
```

**Pasos:**
1. Escribir `.gitignore` antes del primer `git add`.
2. `git init` si hace falta, `git add .gitignore`, commit inicial en `main`.
3. Crear la rama de trabajo: `git checkout -b migracion/vscode-a-claude-code`.
4. Comprobar: `git status --porcelain` no debe listar nada de `_inventario/`; `git status --porcelain --ignored` sí debe listarlo como ignorado.
5. Comprobar que ningún archivo prohibido quedó ya trackeado: `git ls-files | Select-String -Pattern "credential|authToken|\.env|\.claude\.json"` → vacío.

**Definition of done:** CE-0.3 y CE-0.4 en verde, rama creada, `main` con un único commit que contiene solo `.gitignore`.

**Rollback:** si el `git add` capturó algo indebido antes del commit, `git reset`. Si ya se commiteó, `git checkout main && git branch -D` la rama y rehacer desde cero — la historia es de un commit, no vale la pena `filter-repo`.

---

### T0.4 — Auditar `settings.local.json` (33 KB) y el resto de configuración

**Contexto:** `C:\Users\PC 1\.claude\settings.local.json` pesa 33,550 B y no se ha revisado nunca. `settings.json` demostró contener un secreto embebido en una regla de permiso; el archivo `local` es cinco veces más grande y sigue el mismo formato, así que es candidato natural a contener más de lo mismo. Existen además `settings.json.bak` (7,191 B) y `settings.json.bak-claudemem` (4,459 B).

**Pasos:**
1. Sobre la **copia** en `secretos-extraidos\` (no sobre el original), buscar patrones de secreto: cadenas tipo UUID, `sk-`, `ghp_`, `Bearer `, `token=`, `password`, `api_key`, `AIza`, `xoxb-`.
2. Para cada hallazgo: identificar el servicio, rotar la credencial, y eliminar la entrada del archivo original.
3. Repetir el barrido sobre `settings.json.bak` y `settings.json.bak-claudemem`.
4. Registrar en el documento de plan cuántos secretos se encontraron y cuáles se rotaron. Si son cero, escribirlo explícitamente: un cero verificado es un resultado.

**Definition of done:** informe de barrido con número de hallazgos y estado de rotación de cada uno. CE-0.2 extendido a todos los archivos de configuración.

**Rollback:** los `.bak` originales se conservan intactos en el respaldo fechado.

---

### T0.5 — Triage de las 77 observaciones sensibles de `claude-mem.db`

**Contexto:** la base `C:\Users\PC 1\.claude-mem\claude-mem.db` (51.9 MiB) contiene 11,502 observaciones de 162 sesiones sobre tres proyectos. De ellas, 38 están tipificadas `security_alert`, 28 `security_note` y 11 `sensitive` — 77 en total. Esa misma base la escriben **tres** entornos distintos (Claude Code, Cursor vía `.cursor\mcp.json`, y Roo vía `.roo\mcp.json`), todos apuntando al mismo `mcp-server.cjs`. Nunca se ha revisado qué contienen esas 77 filas.

**Pasos:**
1. **No trabajar sobre la base viva.** Usar la copia que produce la Tarea Cero del Plan 1 (T1.0). Si el Plan 1 aún no ha corrido, hacer aquí una copia puntual con los procesos detenidos (pids 13160 y 25020) y las tres piezas: `.db`, `.db-wal`, `.db-shm`.
2. Abrir la copia en solo lectura y extraer las 77 filas:
   ```sql
   SELECT id, project, session_id, type, created_at, substr(content,1,400)
   FROM observations
   WHERE type IN ('security_alert','security_note','sensitive')
   ORDER BY created_at;
   ```
   (Verificar antes los nombres reales de tabla y columnas con `.schema`; el esquema de claude-mem 13.15.0 no está documentado en este plan y no debe suponerse.)
3. Clasificar cada fila en: **(a) secreto real que sigue vivo** → rotar; **(b) secreto ya rotado o caduco** → anotar; **(c) alerta de seguridad sobre código, sin secreto** → dejar, es contexto útil; **(d) falso positivo** → dejar.
4. Para las de categoría (a), rotar la credencial y decidir si se purga la fila de la base viva. Purgar destruye contexto histórico irreemplazable, así que la decisión se documenta caso por caso, no en bloque.

**Definition of done:** tabla de 77 filas con categoría asignada a cada una, 0 sin decidir. CE-0.5.

**Rollback:** ninguna escritura sobre la base viva salvo las purgas explícitamente aprobadas en el paso 4; el respaldo de la Tarea Cero es el punto de restauración.

---

### T0.6 — Verificación final y no regresión

**Contexto:** el Plan 0 tocó `settings.json`, que es el archivo que comparten el CLI y la extensión de VSCode. Un JSON mal formado ahí deja ciegos a los dos entornos a la vez. Esta tarea existe para probar que no pasó.

**Pasos:**
1. `Get-Content "C:\Users\PC 1\.claude\settings.json" | ConvertFrom-Json` → sin excepción.
2. Abrir VSCode, abrir Claude en el sidebar, pedir `dime la fecha de hoy`. Debe responder. (CE-0.6)
3. En terminal nueva: `claude -p "dime la fecha de hoy"`. Debe responder. (CE-0.7)
4. `claude` interactivo → `/agents` y `/plugin` deben seguir listando lo mismo que antes del Plan 0.
5. Correr los barridos de CE-0.2, CE-0.3 y CE-0.4 y pegar la salida como evidencia en la tabla PROGRESO.

**Definition of done:** los siete criterios de éxito en verde, con salida pegada.

---

## 6. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

Fuentes usadas en este plan: **catalogo-agentes, ECC, community, claude-mem, superpowers, built-in** — 6 fuentes. Ver §6.1 para la justificación de claude-ads.

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T0.1, T0.5 | `claude-mem:mem-search` | skill | claude-mem | **Obligatorio.** 11,502 observaciones de 162 sesiones incluyen el momento en que se aprobó el permiso con el token. Buscar `railway`, `RAILWAY_TOKEN`, `c0d59fb0` recupera cuándo y para qué se creó, que es lo que decide si hay automatizaciones que romper al rotarlo. |
| A | T0.2, T0.4 | `Explore` | agente | built-in | Barrido de 12,292 archivos del snapshot buscando patrones de secreto sin quemar el contexto de la sesión principal. |
| A | T0.4 | `production-audit` | skill | community | Auditoría de evidencia local orientada a "qué está expuesto ahora mismo", que es exactamente la pregunta de T0.4. |
| A | T0.5 | `claude-mem:timeline` | skill | claude-mem | [OPCIONAL] Si el triage necesita reconstruir en qué sesión apareció cada observación sensible. Condición de uso: solo si `mem-search` devuelve filas ambiguas sin fecha clara. |
| B | T0.3 | `blueprint` | skill | community | El `.gitignore` y el orden de `init`/`add`/`commit` deben quedar autocontenidos para que otra sesión los ejecute sin este documento delante. Es el estándar de planes de esta plantilla. |
| B | T0.5 | `council` | skill | community | [OPCIONAL] Decisión ambigua real: purgar una observación sensible destruye contexto irreemplazable; conservarla mantiene el riesgo. Condición de uso: activar solo si aparecen filas de categoría (a) cuya purga sea discutible. |
| C | T0.1, T0.2, T0.4 | `powershell-7-expert` | agente | catalogo-agentes | Toda la ejecución es PowerShell sobre Windows: `setx`, `Move-Item`, `Select-String`, `ConvertFrom-Json`. Es el especialista del stack real de esta máquina, no un genérico. |
| C | T0.1, T0.4 | `powershell-security-hardening` | agente | catalogo-agentes | Específico para endurecer configuración en Windows sin romper lo que ya corre. Aplica literalmente al caso: sacar un secreto de un archivo de permisos sin invalidar el archivo. |
| C | T0.2 | `opensource-sanitizer` | agente | catalogo-agentes | Su función es exactamente esta: separar de un árbol de archivos lo que no puede publicarse. Se aplica al snapshot antes de que exista historia git. |
| C | T0.3 | `git-workflow-manager` | agente | catalogo-agentes | `init`, rama desde `main`, primer commit y verificación de que nada indebido quedó trackeado. |
| C | T0.5 | `database-reviewer` | agente | catalogo-agentes | Consultas de solo lectura sobre SQLite con esquema desconocido: primero `.schema`, después el `SELECT`. Evita el error de suponer nombres de columna. |
| C | T0.2, T0.3 | `gateguard` | skill | ECC | Skill de ECC ya instalada en esta máquina (hook `pre:edit-write:gateguard-fact-force` activo en el grafo). Fuerza que las afirmaciones del ejecutor estén respaldadas por hechos verificados, que es lo que hace falta cuando alguien declara "ya no hay secretos". |
| D | Todas | `security-reviewer` | agente | catalogo-agentes | **Obligatorio en todo el plan.** Cada tarea toca permisos, secretos o configuración de MCP/hooks. Ninguna tarea cierra sin su visto bueno. |
| D | T0.1, T0.4, T0.5 | `security-auditor` | agente | catalogo-agentes | Segundo par de ojos independiente sobre el barrido: `security-reviewer` revisa el cambio, `security-auditor` revisa si el barrido fue completo. No se sustituyen. |
| D | T0.2, T0.3 | `security-review` | skill | ECC | Checklist de review de seguridad de ECC, complementaria al agente: cubre el "qué mirar", el agente cubre el "cómo juzgarlo". |
| D | Todas | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio sobre todo cambio de archivo, incluidos JSON de configuración. |
| D | T0.6 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: nada se declara terminado sin la salida pegada de los siete criterios. |
| D | T0.6 | `silent-failure-hunter` | agente | catalogo-agentes | Riesgo concreto: un `settings.json` con JSON válido pero una regla `allow` rota degrada permisos en silencio, sin error visible. Este agente caza exactamente eso. |
| D | T0.6 | `verification-loop` | skill | ECC | [OPCIONAL] Si algún criterio falla, itera hasta verde en vez de reportar y parar. Condición de uso: solo si T0.6 falla en el primer intento. |
| E | Cierre | `pr` / `git-workflow` | skill | ECC | PR con historial y formato convencional en español (`fix:`). |
| E | Cierre | `claude-mem:standup` | skill | claude-mem | Deja registrado en la memoria persistente qué se rotó y qué se purgó, para que la siguiente sesión no vuelva a descubrir el mismo token. |
| E | Cierre | `handoff` | skill | ECC | Contexto para la sesión que ejecute el Plan 1. |

### 6.1 — Evaluación de claude-ads (justificación obligatoria por escrito)

**claude-ads NO aplica a este plan.** La suite (`ads-plan`, `ads-audit`, `ads-meta`, `ads-tiktok`, `ads-google`, `audit-meta`, `audit-google`, `audit-tracking`, `copy-writer`, `creative-strategist`, `visual-designer`, `format-adapter`) cubre planeación, auditoría y creatividades de campañas publicitarias. El Plan 0 no toca campañas, ni píxeles, ni cuentas de anuncios, ni contenido publicable.

Se evaluó explícitamente un caso frontera y se descartó: `audit-tracking` audita píxeles y tokens de plataformas de anuncios, y si el barrido de T0.4 o el triage de T0.5 destapara credenciales de Meta Ads, Google Ads o TikTok Ads, esa skill sería la indicada para medir el alcance del compromiso. **Se deja como contingencia condicionada, no como asignación.** Condición de activación: que T0.4 o T0.5 encuentren al menos una credencial de plataforma publicitaria. Si eso ocurre, `audit-tracking (claude-ads)` entra a etapa D de la tarea correspondiente.

---

## 7. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Gate obligatorio | Gate adicional |
|---|---|---|
| T0.1 | `security-reviewer` + `code-reviewer` | Confirmación en Railway de que el token viejo está revocado |
| T0.2 | `security-reviewer` + `code-reviewer` | Conteo de archivos del snapshot antes/después; los 229+393+509+114 componentes intactos |
| T0.3 | `security-reviewer` + `code-reviewer` | `git ls-files` vacío de patrones prohibidos |
| T0.4 | `security-reviewer` + `security-auditor` | Informe con número de hallazgos, aunque sea cero |
| T0.5 | `security-reviewer` + `database-reviewer` | 77 filas clasificadas, 0 sin decisión |
| T0.6 | `superpowers:verification-before-completion` + `silent-failure-hunter` | Baseline de no regresión (§8) |

**Regla transversal:** `security-reviewer` es obligatorio en las seis tareas. Este plan entero toca permisos, hooks, MCP o secretos.

## 8. BASELINE DE NO REGRESIÓN DEL ENTORNO

Tras **cada** tarea, ambas comprobaciones deben pasar. Si una falla, no avanza nada:

1. **VSCode:** abre, Claude responde a una petición simple.
2. **CLI:** `claude -p "dime la fecha de hoy"` responde, y `/agents` lista 229 agentes y `/plugin` lista `claude-mem@thedotmack` y `superpowers@obra`.

## 9. RIESGOS Y ROLLBACK

| # | Riesgo | Probabilidad | Impacto | Mitigación | Rollback concreto |
|---|---|---|---|---|---|
| R0.1 | Al editar `settings.json` se rompe el JSON y ni VSCode ni el CLI arrancan | Media | Alto | Validar con `ConvertFrom-Json` antes de cerrar la tarea | Restaurar `C:\Users\PC 1\.claude\settings.json` desde `settings.json.bak` (existe en disco, 7,191 B) o desde `_respaldo-migracion-2026-08-15\claude\settings.json` |
| R0.2 | Rotar el token de Railway rompe un despliegue o automatización que lo usaba | Media | Medio | T0.1 paso 1 identifica el alcance ANTES de revocar; `mem-search` sobre `railway` recupera para qué se usó | Emitir token nuevo y ponerlo en variable de entorno; el rollback no es restaurar el viejo (está revocado) sino repoblar la variable |
| R0.3 | La purga del snapshot mueve por error archivos del inventario (agentes, skills) | Baja | Medio | T0.2 mueve solo rutas de la tabla explícita, nunca por patrón amplio; se cuenta antes y después | `Move-Item` inverso desde `_respaldo-migracion-2026-08-15\secretos-extraidos\` |
| R0.4 | Purgar observaciones de `claude-mem.db` destruye contexto irreemplazable | Media | **Alto** | T0.5 no purga en bloque: decisión documentada fila por fila, y solo categoría (a) | Restaurar `.db` + `.db-wal` + `.db-shm` desde el respaldo de T1.0 con ambos procesos detenidos |
| R0.5 | El primer `git add` captura el snapshot de 521 MB antes del `.gitignore` | Media | Medio | T0.3 escribe `.gitignore` ANTES de cualquier `git add` | `git reset` si no hay commit; `git checkout main && git branch -D <rama>` si lo hay |
| R0.6 | Hay más secretos de los detectados en archivos no barridos | **Alta** | Alto | El barrido cubre `settings*.json`, `.bak`, snapshot y la base; se documenta explícitamente qué NO se barrió | No aplica rollback; es deuda declarada que hereda el Plan 3 |

**Respaldos de referencia para todo rollback de este plan:**
`C:\Users\PC 1\_respaldo-migracion-2026-08-15\` (lo produce T1.0 del Plan 1; si el Plan 0 corre antes, T0.2 paso 1 lo crea).

---

## 10. TABLA PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T0.1 | Rotar token de Railway y sacarlo de `settings.json` | **HECHA** (alcance reducido, ver §12) | Token `logs-api` (`…-0616`) revocado en Railway. Identificado entre 3 tokens de la cuenta por coincidencia de sufijo con `c0d59fb0-…-425db4bf0616`; `LOGS` (`…-bd82`) y `LOGS2` (`…-ec77`) no tocados. Etapa A con `buscar-memoria.py railway`: sesión del CLI caducada desde 2026-08-13, despliegues por push a GitHub → riesgo de revocación bajo, confirmado. `settings.json` **no modificado** por decisión del usuario | 2026-08-15 |
| T0.2 | Purgar el snapshot `_inventario\` de material sensible | PENDIENTE | | |
| T0.3 | `.gitignore` y verificación de árbol versionable limpio | **HECHA** | `main` commit `4a7f655` (.gitignore) · rama `migracion/vscode-a-claude-code` commit `babf9b8` (9 archivos, 2,543 líneas) · `git status --porcelain --ignored` → `!! _inventario/` (521 MB excluidos) · **CE-0.4 en verde**: `git ls-files` filtrado por `credential\|authToken\|.env\|.claude.json\|token` devuelve 0 coincidencias | 2026-08-15 |
| T0.4 | Auditar `settings.local.json` y `.bak` | PENDIENTE | | |
| T0.5 | Triage de las 77 observaciones sensibles | **HECHA** | `docs\superpowers\plans\2026-08-15-t05-triage-observaciones-sensibles.md` · **77/77 clasificadas, 0 sin decisión** · Ejecutado sobre la copia del respaldo en solo lectura · Resultado: 9 credenciales sin evidencia de rotación, 5 archivos de credencial en disco, 2 asuntos de PII/cumplimiento, 61 resueltas o sin acción · **17 acciones de remediación derivadas, 6 en P0** | 2026-08-15 |
| T0.6 | Verificación final y no regresión | PENDIENTE | | |

**Avance del Plan 0: 3/6 tareas HECHAS (50%).**

---

## 12. NOTA DE EJECUCIÓN — T0.1 REVISADA A LA BAJA (2026-08-15)

La etapa A de T0.1 (obligatoria: recuperar contexto histórico antes de revocar) se ejecutó con `scripts\buscar-memoria.py railway`, sustituto SQL de `claude-mem:mem-search` — el MCP de claude-mem no estaba conectado en la sesión de diseño. **Sustitución declarada, no omisión.**

Resultado: **revocar el token es de riesgo bajo**, y la evidencia es explícita en la memoria:

| Observación | Fecha | Qué dice |
|---|---|---|
| `[11434]` | 2026-08-13 22:30 | *Railway CLI Installed but Session Expired/Unauthorized* |
| `[11415]` | 2026-08-13 21:57 | *Railway CLI Not Authenticated and Not Linked to SistemaLanzamiento Project* |
| `[11465]` | 2026-08-14 02:00 | *Plan 2 PR #2 squash-merged to main — Railway auto-deploy triggered* |

La sesión del CLI de Railway ya estaba caducada dos días antes, y los despliegues se disparan por **push a GitHub**, no por el token. No hay automatización que romper.

**Cambio de método por decisión del usuario (2026-08-15):** T0.1 se reduce a **revocar el token en Railway y NO editar `settings.json`**. Un token revocado es una cadena inerte; dejarlo en el archivo no es un riesgo. La limpieza del archivo queda como higiene diferida, sin urgencia, porque `settings.json` es el archivo que comparten el CLI y la extensión de VSCode y el usuario prioriza no tocar nada que pueda degradar VSCode. **Criterio rector: si un paso puede romper VSCode y no es necesario, no se ejecuta.**

Esto anula los pasos 3, 4 y 5 de T0.1 tal como estaban escritos en §5. CE-0.2 queda **diferido**, no incumplido: se marcará como tal en el cierre del plan.

---

## 13. HALLAZGO FUERA DE ALCANCE — PanelNioval expuesto

La búsqueda de etapa A destapó una alerta sin atender, ajena al alcance de esta migración (es un proyecto, no el sistema), pero de severidad mayor que el motivo original del Plan 0:

> **`[11460]` · `security_alert` · BruceWhatsapp · 2026-08-13 22:44**
> *PanelNioval: Todos los Endpoints Flask Sin Autenticación — URL Railway Pública Expone Datos de Clientes*

Un servicio accesible desde internet, sin autenticación, con datos de clientes. Lleva **al menos desde el 13 de agosto** registrado en la memoria sin que nadie actuara.

Contexto que lo agrava: `PanelNioval` es el único de los 7 proyectos **sin `.claude\`** — el menos atendido por herramientas.

**Estado: RESUELTO el 2026-08-15.**

Verificación ejecutada. El gate de autenticación **existía en el código** (`app.py:47`, con `hmac.compare_digest`, sesión persistente y una sola ruta exenta) desde los commits `35b5d13` y `faacce7`. Pero es **fail-open**:

```python
token = os.environ.get('PANEL_DASHBOARD_TOKEN')
if not token:
    return  # auth desactivada
```

Y la comprobación en Railway confirmó que **esa variable no estaba definida**: solo existían `GOOGLE_CREDENTIALS_JSON`, `IMGBB_API_KEY`, `PAGO_FOLDER_ID` y las 8 de Railway. **La protección estaba apagada en producción y las rutas —ya 38, no 31— abiertas.**

**Corrección aplicada:** se añadieron `PANEL_DASHBOARD_TOKEN` y `SECRET_KEY` en Railway, con valores generados localmente. Sin modificar código. Confirmado funcionando por el usuario.

**Deuda que queda abierta, para un plan propio de PanelNioval:**

1. **El gate falla abierto.** Una exposición total depende de que alguien recuerde una variable de entorno. Debería fallar cerrado, o abortar el arranque con un error visible.
2. **`WORKER_TOKEN` sigue sin definir** (`app.py:3309`). Si el worker de WhatsApp llama a rutas distintas de `/api/catalogo/heartbeat` —la única exenta— recibirá 401.
3. **IDs de Google Sheets en claro** en `app.py:66-83`, dentro de un repo con `origin/main`. Si ese remoto es público, es exposición independiente del gate.

**Lección de método:** este hallazgo salió de cumplir la etapa A obligatoria (`mem-search`) antes de tocar el token. Sin esa consulta, la migración habría avanzado con datos de clientes abiertos a internet y nadie se habría enterado. **La etapa A no es burocracia.**

---

## 11. NOTA OPERATIVA SOBRE LA EJECUCIÓN

La sesión que diseñó este plan corre en la nube y **no tiene shell en la máquina destino** (`device_bash` reporta `Workspace unavailable` de forma persistente). Puede leer y escribir archivos vía el puente de escritorio, pero no puede ejecutar `git`, `gh`, PowerShell ni consultas SQLite en `C:\`.

En consecuencia, y por decisión del usuario del 2026-08-15: **los comandos los ejecuta el usuario**, la sesión los entrega en bloques copiables y verifica las salidas antes de dar por cerrada cada tarea. La política de merge automático con gates de la plantilla queda sustituida por: la sesión valida los gates, el usuario ejecuta el `commit` y el `merge`.

Si en algún momento se quiere recuperar la ejecución autónoma de git y PR, la vía es relanzar la tarea con la opción **"On your computer"** del selector *Run this task* de la app de escritorio, que da shell real sobre las carpetas del usuario.
