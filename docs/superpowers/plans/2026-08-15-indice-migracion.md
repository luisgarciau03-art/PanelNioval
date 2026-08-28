# ÍNDICE — MIGRACIÓN DEL ENTORNO CLAUDE DE VSCODE A CLAUDE CODE (CLI)

**Fecha de diseño:** 2026-08-15
**Diseñado por:** sesión de Claude (Cowork, nube) con acceso de lectura al entorno vía snapshot verificado
**Repositorio canónico:** `C:\Users\PC 1\migracion-claude-code`
**Rama de trabajo:** `migracion/vscode-a-claude-code` (desde `main` actualizado, NUNCA `main`)
**Copia canónica de los planes:** este repositorio. Las copias en `docs\superpowers\plans\` de cada proyecto son **de solo lectura**.

---

## 1. RESUMEN EJECUTIVO — LO QUE CAMBIÓ RESPECTO AL ENCARGO

El encargo pedía duplicar el entorno Claude de VSCode al CLI. **El inventario en disco demuestra que ese entorno ya es el mismo.**

`C:\Users\PC 1\.claude\` no es la carpeta de la extensión de VSCode: es el directorio de configuración de Claude Code CLI. La extensión es un front-end que se conecta al CLI por WebSocket — lo prueban los **190 archivos `.lock`** en `.claude\ide\`, cada uno con `{"ideName":"Visual Studio Code","transport":"ws","pid":...,"authToken":"..."}`, que es el CLI publicando el puerto para que la extensión lo encuentre.

**Consecuencia:** los 229 agentes, 393 skills locales, 509 comandos, 114 reglas, 28 hooks y 2 plugins **ya están disponibles en terminal hoy**. No hay archivos que copiar. Lo que sí existe es trabajo real, y es otro:

| Lo que se creía | Lo que el disco dice |
|---|---|
| Hay que duplicar el entorno al CLI | Ya está duplicado; hay que **probarlo** |
| Riesgo de heredar `bypassPermissions` al CLI | El CLI **ya lo tiene** puesto, y siempre lo tuvo |
| Contradicción de permisos VSCode vs CLI | No hay contradicción: hay una postura única, abierta, y los ajustes de VSCode eran cosméticos |
| La captura de memoria está rota en `worker-service.cjs` | Está rota en **`server-service.cjs`**, que es otro script |
| Un proceso de claude-mem | **Dos**: pid 13160 (supervisor) y pid 25020 (`spawn.lock`) |
| Chroma a medio camino | Peor: **201 de 10,163** observaciones indexadas en BruceWhatsapp, **0 de 1,203** en SistemaLanzamiento |
| — | **Token de Railway en texto plano en `settings.json`** (hallazgo nuevo, crítico) |

Por eso hay **cuatro planes y no tres**: el Plan 0 no estaba pedido y es el primero que se ejecuta.

---

## 2. ORDEN DE EJECUCIÓN Y DEPENDENCIAS

```
┌──────────────────────────────────────────────────────────────┐
│ PLAN 0 — SEGURIDAD URGENTE                        6 tareas   │
│ Token vivo, secretos en el snapshot, .gitignore, 77 obs      │
│ BLOQUEANTE: ningún otro plan arranca con este abierto        │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ PLAN 1 — PARIDAD REAL Y SANEAMIENTO               9 tareas   │
│ T1.0 Tarea Cero (respaldo) ► bloquea todo lo demás           │
│ Captura de memoria · permisos · fuente de verdad · checklist │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ PLAN 2 — VALIDACIÓN Y PRUEBAS                     9 tareas   │
│ Paridad verificable, no "se ve bien". Produce los hallazgos  │
│ NO arregla nada: los hallazgos van al Plan 3                 │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ PLAN 3 — OPTIMIZACIÓN                             9 tareas   │
│ ECC sin gestionar · 370 stubs · 478 skills · cruft · memoria │
└──────────────────────────────────────────────────────────────┘
```

| Plan | Documento | Tareas | Depende de | Bloquea a |
|---|---|---|---|---|
| 0 | `2026-08-15-plan0-seguridad-urgente.md` | 6 | — | 1, 2, 3 |
| 1 | `2026-08-15-plan1-duplicar-entorno-claude-a-cli.md` | 9 | Plan 0 | 2, 3 |
| 2 | `2026-08-15-plan2-validacion-y-pruebas.md` | 9 | Planes 0, 1 | 3 |
| 3 | `2026-08-15-plan3-optimizacion.md` | 9 | Planes 0, 1, 2 | — |

**Tareas críticas de secuencia, que no se pueden reordenar:**

1. **Plan 1 T1.0 (Tarea Cero) antes que cualquier modificación.** Sin respaldo verificado no empieza nada. La base de 51.9 MiB con 11,502 observaciones de 53 días es lo único irreconstruible de toda la migración.
2. **Plan 1 T1.1 (captura de memoria) antes de usar el CLI en paralelo.** Con la captura rota, usar dos frentes replica el fallo en dos en vez de uno.
3. **Plan 3 T3.1 (ECC bajo instalador) antes de T3.2 y T3.3.** Si se limpian comandos y rutas primero, el instalador los repone y el trabajo se pierde.
4. **Plan 3 T3.8: `veo-asesores-claude` primero.** Es el único proyecto sin git; hasta que lo tenga, cualquier error ahí es irreversible.

---

## 3. RESUMEN DE ASIGNACIÓN DE HERRAMIENTAS POR FUENTE

Biblioteca de referencia: `BIBLIOTECA-HERRAMIENTAS.md` — **653 herramientas (229 agentes + 424 skills)**, 6 fuentes.

**Herramientas distintas asignadas por plan y fuente** (sin contar repeticiones dentro del mismo plan):

| Fuente | Plan 0 | Plan 1 | Plan 2 | Plan 3 | Total distintas |
|---|---:|---:|---:|---:|---:|
| **catalogo-agentes** | 9 | 16 | 15 | 17 | 33 |
| **ECC** | 5 | 7 | 6 | 6 | 15 |
| **community** | 3 | 2 | 2 | 3 | 4 |
| **claude-mem** | 2 | 3 | 3 | 3 | 5 |
| **superpowers** | 1 | 3 | 1 | 2 | 5 |
| **built-in** | 1 | 1 | 2 | 1 | 3 |
| **claude-ads** | 0¹ | 0¹ | 5² | 0¹ | 5 |
| **Fuentes distintas por plan** | **6** | **6** | **6+1²** | **6** | — |
| **Total de asignaciones** | 21 | 32 | 29 | 33 | — |

¹ Justificado por escrito en la §6.1 de cada plan, con condición de activación como contingencia — no excluido en silencio.
² En el Plan 2, claude-ads no ejecuta pero **sí es objeto de prueba**: T2.3 verifica que sus ~60 herramientas cargan igual que las de las demás fuentes.

**Contraste con la regla anti-sesgo:** superpowers aporta 14 de las 653 herramientas (2.1%). En estos planes representa **7 de 115 asignaciones (6.1%)** — presente en los cuatro, dominante en ninguno. `catalogo-agentes`, la fuente mayor, concentra el 58% de las asignaciones, que es proporcional a su peso (229 de 653 = 35%) más el hecho de que los gates de verificación obligatorios (`code-reviewer`, `security-reviewer`, `silent-failure-hunter`) salen todos de ahí y se repiten en las cuatro tareas de cierre.

---

## 4. MARCADOR DE PROGRESO GLOBAL

| Plan | Tareas HECHAS | Total | % |
|---|---:|---:|---:|
| Plan 0 — Seguridad urgente | **3** | 6 | **50%** |
| **Plan 5 — Remediación de credenciales** | 0 | 12 | 0% |
| Plan 1 — Paridad y saneamiento | **5** | 10 | **50%** |
| Plan 2 — Validación y pruebas | **1** | 9 | **11%** |
| Plan 3 — Optimización | 0 | 9 | 0% |
| **GLOBAL** | **9** | **46** | **20%** |

> **Actualizado el 2026-08-15 (decisión del owner).** 7/46 → **9/46**. Suma **T1.3** (postura de permisos: lista `deny` v2 aplicada) y **T2.3** (prueba de carga por fuente: CE-2.3 cumplido, 29/30 herramientas cargan).
>
> **Qué NO se contó, y por qué.** El número es solo lo verificable con evidencia y tabla PROGRESO actualizada:
>
> - **T3.5 sigue PENDIENTE.** Su tabla del Plan 3 lo dice, y lo ejecutado el 2026-08-15 —1,433 MB apartados de `plugins\cache`— **no es lo que T3.5 define** (~12.5 MB de cruft). Contarla exigiría antes reescribir su definición para que la evidencia case con la tarea. Además, **M-10** (automatizar la retención) va *dentro* de T3.5 y no se ha hecho.
> - **Las mejoras M-xx no entran en el denominador.** Siguen en 46. **M-11** (reducción de `hooks.json`) se ejecutó, pero está declarada *"contribución upstream, fuera de alcance"* y nunca fue una de las 46.
>
> **Inconsistencia pendiente de resolver:** M-01 propone incorporarse como **T1.9**, identificador que **ya existe** en el Plan 1 (*alinear versiones de binario*, HECHA). Si algún día se amplía el denominador con las M-xx, hay que renumerar antes.

> **✅ EL ENCARGO ORIGINAL ESTÁ CUMPLIDO (2026-08-15).** Motor alineado a **2.1.233** en las dos ventanas, atajos de terminal instalados, y paridad verificada componente por componente. Ver el bloque ★ al final del Plan 1. Lo que queda en los Planes 0, 5, 2 y 3 es saneamiento y seguridad, no migración.
>
> **La respuesta de fondo era que no había nada que copiar.** Verificado el 2026-08-15 desde ambas ventanas: 229 agentes, 393 skills, 509 comandos y 2 plugins **idénticos**; y la extensión de VSCode **no contiene agentes, skills, hooks, plugins ni reglas propios** — solo `extension.js`, la interfaz web, el esquema de `settings.json` y una copia de `claude.exe`. El sidebar es una ventana sobre el mismo motor.
>
> **La única diferencia real encontrada:** la terminal ejecuta la **2.1.141** (npm) y la extensión la **2.1.233** (empaquetada). Misma configuración, motores distintos. Se resuelve en **Plan 1 T1.9**, y es el único trabajo de migración que existía.

> **⚠ EL PLAN 5 SE ANTEPONE A LOS PLANES 1, 2 Y 3.** El triage de T0.5 clasificó las 77 observaciones sensibles y encontró **9 credenciales marcadas para rotación sin evidencia de que se rotara ninguna**, 5 archivos de credencial en disco, y 2 asuntos de PII y cumplimiento. Entre ellas: una clave de Gemini **probada activa el 2026-07-17 y re-marcada tres veces**, la `ADMIN_API_KEY` de producción descrita como *"short, guessable"*, cinco tokens de Telegram repartidos por 30+ scripts, y contactos que pidieron STOP que **pueden seguir recibiendo mensajes**.
>
> El Plan 5 reduce más riesgo real que los Planes 1, 2 y 3 juntos, que son de comodidad y orden. Ver `2026-08-15-plan5-remediacion-credenciales.md` y `2026-08-15-t05-triage-observaciones-sensibles.md`.
>
> **Nuevo orden de ejecución:** Plan 0 → **Plan 5** → Plan 1 → Plan 2 → Plan 3.

**Planes completados: 0 / 4.**

**Hito:** Tarea Cero (Plan 1 T1.0) cerrada el 2026-08-15 con veredicto `RESPALDO_VERIFICADO`. Respaldo en `C:\Users\PC 1\_respaldo-migracion-2026-08-15\`. Cuatro hallazgos de esa ejecución corrigen el diseño de T1.1, T2.2 y T3.6 — ver §11 del Plan 1.

*Actualizar esta tabla al cerrar cada tarea, junto con la tabla PROGRESO del plan correspondiente.*

---

## 5. AUTOEVALUACIÓN (Paso 4 de la plantilla)

**¿Cuántas fuentes distintas usa cada plan?**
Plan 0: **6**. Plan 1: **6**. Plan 2: **6** ejecutoras + claude-ads como objeto de prueba. Plan 3: **6**.
El mínimo exigido por el encargo era 5. Se cumple en los cuatro, y ninguna fuente se excluye en silencio: claude-ads tiene justificación escrita y condición de activación en cada plan.

**¿Aparecen ECC, claude-mem, catalogo-agentes y community además de superpowers?**
**Sí, las cuatro, en los cuatro planes.** ECC: 15 herramientas distintas. claude-mem: 5, obligatoria en etapa A de los cuatro. catalogo-agentes: 33. community: `blueprint` en los cuatro y `council` en tres, precisamente donde hay tradeoff real y no decisión obvia.

**¿Toda tarea tiene etapa D (verificación)?**
**Sí, las 33.** Cada plan tiene su tabla §7 de gates por tarea, y `code-reviewer` es gate general en todas. `security-reviewer` es obligatorio en 24 de las 33 — la mayoría, porque esta migración toca permisos, hooks, MCP o secretos en casi todo lo que hace.

**¿Toda tabla PROGRESO está pre-poblada?**
**Sí.** Los cuatro documentos cierran con su tabla, una fila por tarea, estado `PENDIENTE`, columnas de evidencia y fecha vacías para el ejecutor.

**¿Toda tarea cubre al menos C y D?**
Sí, con dos excepciones deliberadas y declaradas: **Plan 2 T2.1** (diseño de la matriz) es etapa B pura, y su gate D es la aprobación de `qa-expert` antes de escribir el primer script — diseñar las pruebas después de escribirlas produce pruebas de lo fácil, no de lo importante. **Plan 1 T1.2** es de solo lectura y su etapa D es la comparación CLI vs. sidebar, que es la verificación misma.

**Autocrítica — lo que este diseño NO resuelve:**
- El muestreo del Plan 2 T2.3 cubre **30 de 653 herramientas (4.6%)**. Es explícito en el documento y en el informe, pero sigue siendo un muestreo.
- Las **77 observaciones sensibles** se clasifican (Plan 0 T0.5), no se resuelven: la decisión de purgar destruye contexto irreemplazable y se toma caso por caso.
- **Seis carpetas de entornos IA sin inventariar** (`.claw`, `.openclaw`, `.gemini`, `.impeccable`, `.agents`, `.stitch-mcp`) quedan fuera de los cuatro planes. Ver Mejora M-07.
- El diseño se hizo sobre un **snapshot del 2026-08-14/15**, no sobre el entorno vivo. Cualquier cambio posterior invalida conteos, no conclusiones.

---

## 6. MEJORAS PROPUESTAS (no pedidas)

Optimizaciones detectadas durante el inventario que **no** están cubiertas por los cuatro planes.

| # | Mejora | Categoría | Impacto | Esfuerzo | Dónde encaja |
|---|---|---|---|---|---|
| **M-01** | **Alerta cuando aparezca `CAPTURE_BROKEN`.** El fallo de captura duró **36 días sin que nadie lo notara** porque el archivo se escribe en silencio. Un hook `SessionStart` que compruebe su existencia y avise convierte un fallo invisible en uno visible. | Telemetría / DX | **Alto** | Bajo | **Plan 1, tarea nueva T1.9** |
| **M-02** | **Detección de secretos en pre-commit** (`gitleaks` o equivalente) en `migracion-claude-code` y en los 7 proyectos. El token de Railway estaba en `settings.json` desde hacía tiempo y solo se encontró por un inventario manual. | Seguridad | **Alto** | Bajo | **Plan 0, tarea nueva T0.7** |
| **M-03** | **Censo del entorno como tarea programada.** `scripts\censo-entorno.ps1` (Plan 2 T2.2) corriendo semanalmente detecta deriva: plugins auto-actualizados, skills añadidas a mano, conteos que dejan de cuadrar con la biblioteca. Ambos marketplaces tienen `autoUpdate: true`, así que el entorno cambia solo. | Telemetría | **Alto** | Bajo | **Plan 3, tarea nueva T3.10** |
| **M-04** | **Configuración como código.** `settings.json`, `hooks.json` y la lista de MCP versionados en este repo, con un script de aplicación. Hoy la configuración del entorno vive solo en `%USERPROFILE%` y su única copia es un respaldo manual. | DX / Deuda | **Alto** | Medio | **Plan nuevo (Plan 4)** |
| **M-05** | **`CLAUDE.md` global en `.claude\`.** Existe `AGENTS.md` (8,798 B) pero no un `CLAUDE.md` de nivel usuario que fije las reglas del entorno para todas las sesiones. Sería el lugar natural para la postura de permisos decidida en Plan 1 T1.3. | DX | Medio | Bajo | **Plan 1, tarea nueva T1.10** |
| **M-06** | **Checkpoint programado del WAL de SQLite.** `claude-mem.db` en modo WAL con dos procesos escribiendo: un checkpoint periódico reduce el riesgo de que un corte deje `.db-wal` grande e inconsistente. Ya hay 8 archivos `.claude.json.backup/corrupted` en `backups\`, señal de que la corrupción no es hipotética. | Deuda / Fiabilidad | Medio | Bajo | **Plan 3, dentro de T3.6** |
| **M-07** | **Inventariar los 6 entornos IA restantes**: `.claw`, `.openclaw`, `.gemini`, `.impeccable`, `.agents`, `.stitch-mcp`. Se desconoce si alguno escribe en `claude-mem.db` o define hooks. Cursor y Roo ya lo hacen; asumir que estos no, sin comprobarlo, es la misma clase de suposición que ocultó la captura rota. | Deuda / Seguridad | Medio | Medio | **Plan nuevo (Plan 4)** |
| **M-08** | **Revisar el alcance de `.windsurf`**, registrado sobre la raíz `C:\Users\PC 1` (11 jun 2026) — el home entero, no un proyecto. Combinado con `additionalDirectories: ["C:\\Users\\PC 1"]` en `settings.json`, hay dos herramientas con alcance sobre todo el perfil de usuario. | Seguridad | Medio | Bajo | **Plan 1, dentro de T1.3** |
| **M-09** | **Documentar la divergencia de modelo.** `claude-mem` corre con `claude-sonnet-4-6` (`CLAUDE_MEM_MODEL`) mientras Claude Code corre con `effortLevel: "high"` y el modelo de la suscripción. Los resúmenes de memoria los produce un modelo distinto del que los consume, y eso no está escrito en ningún sitio. | Deuda / Documentación | Bajo | Bajo | **Plan 2, dentro de T2.6** |
| **M-10** | **Retención automática de `file-history\` y `shell-snapshots\`.** El Plan 3 T3.5 aplica retención una vez; sin automatizarla, el cruft vuelve. | DX | Bajo | Bajo | **Plan 3, dentro de T3.5** |
| **M-11** | **Reducir `hooks.json` de 49,658 B.** ~90% es el mismo resolvedor de `CLAUDE_PLUGIN_ROOT` repetido 28 veces. Con la variable fija (Plan 3 T3.3), sobra. **Requiere proponerlo aguas arriba en `affaan-m/ECC`**, porque el archivo es `ownership: "managed"` y un parche local se pierde en la siguiente instalación. | Performance / Deuda | Bajo | Alto | **Contribución upstream, fuera de alcance** |

**Recomendación de incorporación inmediata:** M-01, M-02 y M-03 son alto impacto y bajo esfuerzo, y las tres atacan el mismo patrón — **fallos que ocurren en silencio y se descubren tarde**, que es el modo de fallo dominante que reveló este inventario. Se sugiere añadirlas como tareas de los planes indicados antes de empezar la ejecución.

**Recomendación de Plan 4:** M-04 (configuración como código) y M-07 (los 6 entornos sin inventariar) no caben en los planes existentes y juntos forman un plan coherente — *"gobierno del entorno multi-herramienta"*. Se propone diseñarlo al cerrar el Plan 3, cuando el entorno ya esté estable y medido.

---

## 7. NOTA OPERATIVA — CÓMO SE EJECUTA ESTA MIGRACIÓN

La sesión que diseñó estos planes corre **en la nube** y no tiene shell en la máquina destino: `device_bash` reporta `Workspace unavailable` de forma persistente (verificado dos veces el 2026-08-15). Puede leer y escribir archivos vía el puente de escritorio, pero **no puede ejecutar `git`, `gh`, PowerShell ni consultas SQLite** en `C:\`.

**Decisión del usuario (2026-08-15):** los comandos los ejecuta el usuario; la sesión los entrega en bloques copiables y verifica las salidas antes de cerrar cada tarea.

**Sustitución de la política de merge automático:** la plantilla original pide `gh pr create` + `gh pr merge --squash` ejecutados por el agente. En este modo, la sesión **valida los gates** y el usuario **ejecuta el commit y el merge**. La regla que no cambia: **nunca se mergea con regresiones, y nunca se trabaja en `main`.**

**Cómo recuperar la ejecución autónoma de git y PR:** relanzar la tarea con la opción **"On your computer"** del selector *Run this task*, arriba a la derecha en la app de escritorio al iniciar una tarea nueva. Eso da shell real sobre las carpetas del usuario y hace ejecutable la política original sin cambios.

---

## 8. DISTRIBUCIÓN DE LOS PLANES

Al cerrar **cada** plan, copiar los cuatro documentos y este índice a `docs\superpowers\plans\` de cada proyecto que use Claude. La copia canónica es la de `migracion-claude-code`; las demás son **de solo lectura**.

| Proyecto | `.claude` | `.git` | `.superpowers` | Estado de la copia |
|---|---|---|---|---|
| BruceWhatsapp | ✅ | ✅ | ✅ | PENDIENTE |
| SistemaLanzamiento | ✅ | ✅ | ✅ | PENDIENTE |
| FinanzasAPPANDROID | ✅ | ✅ | ✅ | PENDIENTE |
| NIOVAL_ANTHROPIC | ✅ | ✅ | ✗ | PENDIENTE |
| SUPRATECHWEB | ✅ | ✅ | ✗ | PENDIENTE |
| veo-asesores-claude | ✅ | **✗** | ✗ | PENDIENTE — **`git init` primero** |
| PanelNioval | **✗** | ✅ | ✗ | PENDIENTE — **crear `.claude\` primero** |

`VSCODEP2` está vacía; no es un proyecto y no recibe copia.

---

## 9. MENSAJE DE ARRANQUE PARA LA SESIÓN EJECUTORA

```
Vas a ejecutar los planes de migración del ENTORNO CLAUDE de esta máquina.

RAÍZ DEL ENTORNO: C:\Users\PC 1
REPOSITORIO CANÓNICO: C:\Users\PC 1\migracion-claude-code
RAMA DE TRABAJO: migracion/vscode-a-claude-code (desde main actualizado, NUNCA main)

ANTES DE TOCAR NADA, lee en este orden:
1. C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md  ← biblioteca de 653 herramientas
   (229 agentes + 424 skills; fuentes: catalogo-agentes, ECC, claude-ads, community,
   claude-mem, superpowers). Confirma que la leíste citando el total y las 6 fuentes.
2. C:\Users\PC 1\migracion-claude-code\docs\superpowers\plans\2026-08-15-indice-migracion.md
   ← este índice: orden, dependencias y autoevaluación.
3. Los cuatro planes, en orden:
   - Plan 0: .../2026-08-15-plan0-seguridad-urgente.md
   - Plan 1: .../2026-08-15-plan1-duplicar-entorno-claude-a-cli.md
   - Plan 2: .../2026-08-15-plan2-validacion-y-pruebas.md
   - Plan 3: .../2026-08-15-plan3-optimizacion.md
4. Memoria: usa claude-mem (mem-search) para recuperar contexto previo.
   Proyectos con historial: BruceWhatsapp (10,163 obs), SistemaLanzamiento (1,203),
   FinanzasAPPANDROID (136).

CONTEXTO CRÍTICO QUE NO DEBES RE-DERIVAR:
- C:\Users\PC 1\.claude\ ES el directorio de Claude Code CLI. VSCode y el CLI
  comparten entorno; la extensión se conecta al CLI por WebSocket (.claude\ide\*.lock).
  NO hay archivos que copiar. Lee el §0 del Plan 1 antes de dudarlo.
- Hay un token de Railway en texto plano en .claude\settings.json. Plan 0, tarea T0.1.
- La captura de memoria está rota desde 2026-07-09 en server-service.cjs (NO en
  worker-service.cjs). Plan 1, tarea T1.1.
- Hay DOS procesos de claude-mem: pid 13160 y pid 25020. Detén ambos en la Tarea Cero.

REGLAS DE EJECUCIÓN:
- Cada tarea usa las herramientas de su tabla de asignación (Herramienta + Fuente).
  NO las sustituyas por Superpowers u otra por comodidad; si una no está disponible,
  repórtalo y usa la alternativa de su misma categoría en la biblioteca.
- Gates de verificación antes de cerrar cada tarea: reviewer del stack + code-reviewer;
  security-reviewer OBLIGATORIO en todo lo que toque permisos, hooks, MCP o secretos.
- Baseline de no regresión del ENTORNO tras cada tarea:
  (a) VSCode abre Claude y responde a una petición simple;
  (b) el CLI responde y lista 229 agentes y 2 plugins.
  Si una de las dos falla, no avanza nada.
- MODO DUPLICAR, NO REEMPLAZAR: si un paso rompe VSCode, ese paso está mal diseñado.

PROGRESO (obligatorio):
- Al cerrar cada tarea, actualiza la tabla PROGRESO del plan (estado + evidencia:
  commit/test/PR + fecha) y el marcador global de la §4 de este índice.
- En cada reporte incluye: % del plan actual (HECHAS/totales), % global y bloqueos.

MERGE:
- Al terminar cada plan, crea el PR con gh pr create --base main y, SI Y SOLO SI todos
  los gates están en verde, mergéalo con gh pr merge --squash.
- Si algún gate falla: NO mergees. Deja el PR abierto, documenta qué falta en la tabla
  PROGRESO y notifica. Nunca mergees con regresiones ni trabajes en main.
- Commits convencionales (feat:/fix:/test:/refactor:) en español.
- Si no tienes shell en la máquina (sesión en la nube), entrega los comandos en bloques
  copiables, valida las salidas, y deja el commit y el merge al usuario.

NOTIFICACIÓN (obligatoria):
- Al terminar cada plan y al terminar la migración completa: qué se mergeó (PR y SHA),
  estado de gates, % de progreso global y pendientes.

AL CERRAR: guarda contexto para la siguiente sesión (claude-mem / handoff).

EMPIEZA POR: Plan 0, tarea T0.1 (rotar el token de Railway). Es lo único de esta
migración que está activamente expuesto ahora mismo.
```
