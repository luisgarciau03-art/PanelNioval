# PLAN 5 — REMEDIACIÓN DE CREDENCIALES EXPUESTAS

**Fecha de diseño:** 2026-08-15
**Repositorio canónico:** `C:\Users\PC 1\migracion-claude-code`
**Rama de trabajo:** `remediacion/credenciales` (desde `main` actualizado, NUNCA `main`)
**Origen:** hallazgos de T0.5 — ver `2026-08-15-t05-triage-observaciones-sensibles.md`
**Precedencia:** **se ejecuta ANTES que los Planes 1, 2 y 3.** Reduce más riesgo real que los tres juntos.

> **Este documento no contiene ningún valor de credencial.** Solo nombres de variable, archivo y línea.

---

## 0. Por qué existe este plan

El Plan 0 se creó por un token de Railway en `settings.json`. El triage de las 77 observaciones sensibles demostró que ese era **el hallazgo menor**.

En dos meses, los agentes de este entorno detectaron y documentaron con precisión **nueve credenciales expuestas**, cinco archivos de credencial en disco y dos asuntos de cumplimiento. **Ninguna tiene observación posterior que confirme su remediación.**

El problema estructural no es ninguna clave concreta: **el pipeline de detección funciona y el de remediación no existe.** Una `security_alert` en claude-mem es una nota — sin estado, sin dueño, sin verificación, sin recordatorio. 38 alertas escritas, 0 cerradas.

Este plan existe para cerrarlas y para que la próxima no se quede abierta dos meses.

---

## 1. Objetivo

Dejar cero credenciales activas expuestas en disco, en historial de git, en variables de entorno de usuario o en la base de memoria; y montar el mecanismo que impida que vuelva a acumularse el mismo backlog.

## 2. Alcance

**SÍ entra:** rotación de 9 credenciales; reubicación de 5 archivos de credencial; reducción de privilegio de la cuenta de servicio de Google; eliminación de PII en disco; el asunto de cumplimiento de opt-outs; y la prevención (detección en pre-commit + seguimiento de alertas).

**NO entra:** refactorizar los 30+ scripts más allá de extraer credenciales a variables de entorno. Migrar código es otro trabajo.

**NO entra:** purgar observaciones de `claude-mem.db`. El triage recomienda conservarlas (§7 de T0.5): una vez rotada, una credencial en la memoria es una cadena inerte, y el contexto vale más que el riesgo residual.

## 3. Criterios de éxito (medibles)

| # | Criterio | Comprobación ejecutable | Umbral |
|---|---|---|---|
| CE-5.1 | Las claves rotadas ya no funcionan | Petición autenticada con el valor viejo, por credencial | 401/403 en las 9 |
| CE-5.2 | `~/.claude.json` sin claves en texto plano | Barrido por prefijo `AQ.` y patrones de clave | 0 coincidencias |
| CE-5.3 | Sin tokens de Telegram hardcodeados | Barrido de patrón `\d{8,10}:[A-Za-z0-9_-]{35}` en el home | 0 coincidencias fuera de `.env` y del respaldo |
| CE-5.4 | Sin archivos de credencial en la raíz del home | `Get-ChildItem "C:\Users\PC 1" -Filter "*.json"` filtrado por patrón de credencial | 0 |
| CE-5.5 | Cuenta de servicio con privilegio mínimo | Alcance declarado en el código y en la consola de Google Cloud | `auth/spreadsheets`, no `auth/drive` |
| CE-5.6 | Keystore de Play Store fuera del historial de git | `git log --all --diff-filter=A -- "*.jks" "*keystore*"` en cada repo | 0 resultados, o historial reescrito |
| CE-5.7 | Opt-outs honrados | Conteo de filas en pestañas `SUPRESION_conflict*` vs. contactos suprimidos | 0 bajas sin procesar |
| CE-5.8 | Sin PII en nombres de archivo | Barrido de `debug_invalid_*` en el home | 0 |
| CE-5.9 | Prevención activa | Commit de prueba con un secreto falso en cada repo | El hook lo bloquea en los 7 |
| CE-5.10 | Sin regresión funcional | Bruce envía un mensaje; el dashboard responde; el worker opera | 3/3 |

## 4. Dependencias

```
T5.0 (inventario en vivo) ──> BLOQUEA TODO. Sin saber qué está donde, rotar es a ciegas.
   │
   ├── P0, en paralelo entre sí:
   │   ├──> T5.1 Gemini + Stitch
   │   ├──> T5.2 ADMIN_API_KEY
   │   ├──> T5.3 Telegram (el mayor)
   │   ├──> T5.4 Meta / WhatsApp
   │   ├──> T5.5 Keystore en historial git
   │   └──> T5.6 Opt-outs (cumplimiento)
   │
   ├── P1: T5.7 (rotaciones restantes) · T5.8 (archivos) · T5.9 (PII)
   │
   └──> T5.10 (prevención) ──> T5.11 (verificación final)
```

**T5.0 bloquea todo.** El triage se basa en observaciones de hace hasta dos meses; el estado actual del disco puede diferir. Rotar sin verificar el estado real es cómo se rompe producción.

---

## 5. TAREAS (formato blueprint — contexto autocontenido)

### T5.0 — Inventario en vivo: dónde está cada credencial HOY [BLOQUEANTE]

**Contexto para una sesión fría:** las observaciones que originan este plan van del 2026-06-25 al 2026-08-14. Algunas pueden estar ya resueltas sin que se registrara. Antes de rotar nada hay que saber (a) si la credencial sigue en disco, (b) **qué consume cada credencial** — porque rotar sin conocer los consumidores rompe producción, y Bruce está enviando mensajes reales a clientes.

**Pasos:**
1. Barrido de patrones de secreto sobre el home, excluyendo `_respaldo-migracion-2026-08-15\`, `node_modules` y `.git`:
   - Prefijo `AQ.` (claves de Google/Gemini)
   - `sk-` (OpenAI) · `ghp_`/`github_pat_` (GitHub) · `xoxb-` (Slack)
   - `\d{8,10}:[A-Za-z0-9_-]{35}` (bot de Telegram)
   - `EAA[A-Za-z0-9]{20,}` (Meta) · `Bearer ` en archivos de código
2. Inventario de variables de entorno de usuario: `Get-ChildItem Env:` y las de ámbito usuario en el registro. **Anotar solo nombres, nunca valores.**
3. Para cada credencial encontrada, listar sus **consumidores**: qué scripts, servicios de Railway, MCP o automatizaciones la usan. Fuente: `buscar-memoria.py <nombre>` más el barrido de código.
4. Producir `docs\credenciales\inventario-2026-08-15.md` con: credencial, ubicaciones, consumidores, estado (viva/rotada/desconocida) y quién puede rotarla.

**Definition of done:** el inventario cubre las 9 de categoría (a) y los 5 archivos de categoría (b) de T0.5, cada uno con sus consumidores identificados. **Ninguna rotación empieza sin su fila completa.**

**Rollback:** tarea de solo lectura.

---

### T5.1 — [P0] Rotar `GEMINI_API_KEY` y `STITCH_API_KEY`

**Contexto:** ambas viven en `~/.claude.json`, en el bloque `env` del servidor MCP `nanobanana`, en texto plano. Ambas con prefijo `AQ.`. La observación `6897` (2026-07-17) registra una **prueba en vivo: HTTP 200 con acceso completo a la lista de modelos**. Se volvió a marcar el 26, 27 y 28 de julio (`9398`, `9404`, `9464`). `STITCH_API_KEY` se descubrió en el mismo barrido (`6898`) y nunca se había reportado antes.

**Pasos:**
1. Google AI Studio / Cloud Console → identificar ambas claves y su proyecto.
2. Crear claves nuevas **con restricción de API y de referente/IP** si el uso lo permite. Las viejas no tenían restricción, y eso es parte del problema.
3. Actualizar `~/.claude.json`. **`~/.claude.json` no es versionable y no debe salir del disco** — recordar que el respaldo lo contiene, y ese respaldo está fuera del repo por diseño.
4. Revocar las viejas.
5. Verificar: petición con la clave vieja → 400/403. Petición con la nueva desde el MCP `nanobanana` → funciona.

**Definition of done:** CE-5.1 y CE-5.2 para estas dos.

**Rollback:** `~/.claude.json` desde `_respaldo-migracion-2026-08-15\claude\`. **Advertencia:** ese respaldo contiene las claves viejas; si se restaura, hay que volver a aplicar las nuevas.

---

### T5.2 — [P0] Rotar `ADMIN_API_KEY`

**Contexto:** `593` (2026-06-25) registra que el valor se compartió en el chat. `10540` (2026-07-31) lo describe como *"short, guessable static string used in both local and Railway production"* y confirma que funciona. **Es la llave de administración de Bruce en producción y es adivinable por fuerza bruta.**

**Pasos:**
1. Identificar todos los consumidores (T5.0): endpoints de Bruce, dashboard, scripts locales, variables en Railway.
2. Generar valor nuevo largo y aleatorio: `python -c "import secrets;print(secrets.token_urlsafe(32))"`.
3. **Actualizar primero todos los consumidores, después invalidar el viejo** — en ese orden, o Bruce deja de responder entre ambos pasos.
4. Verificar que el admin sigue funcionando y que el valor viejo devuelve 401.
5. **La observación `593` contiene el valor literal en su subtítulo.** Una vez rotado deja de importar; si por alguna razón no se rota, esa fila es un riesgo por sí misma y hay que decidir sobre ella.

**Definition of done:** CE-5.1 para esta credencial, más CE-5.10 (Bruce operativo).

**Rollback:** revertir la variable en Railway y en local al valor previo, que se conserva hasta cerrar la tarea.

---

### T5.3 — [P0] Rotar y migrar los tokens de Telegram [LA MAYOR]

**Contexto:** diez observaciones entre el 12 y el 14 de agosto (`11181`, `11205`, `11216`, `11219`, `11223`, `11294`, `11452`, `11453`, `11462`, `11469`). El token principal está en `22.PY` líneas 62-63. `11452` dice *"presente en ~14 proyectos"*. `11223` amplía: ***"5 distinct Telegram bot tokens hardcoded across 30+ local scripts"***. `11219` añade que el token aparece **verbatim en 5 documentos de plan**.

Es la de mayor extensión del plan: no es una credencial en un sitio, son cinco en decenas.

**Pasos:**
1. Del inventario de T5.0, listar los 5 tokens y todos sus archivos.
2. Para cada bot en BotFather: `/revoke` y emitir token nuevo.
3. Migrar **todos** los puntos de uso a `os.environ.get('TELEGRAM_TOKEN_<BOT>')`. Sin valores por defecto en el código: si falta la variable, que falle ruidosamente. **Un default silencioso es cómo el gate de PanelNioval acabó desactivado en producción.**
4. Los 5 documentos de plan con el token verbatim: redactar el valor, dejando la referencia.
5. Verificar que cada bot sigue enviando.

**Definition of done:** CE-5.3.

**Rollback:** los archivos están en git salvo `22.PY` (untracked, según `11452`). **Copiar `22.PY` al respaldo antes de tocarlo** — no tiene control de versiones.

---

### T5.4 — [P0] Rotar tokens de Meta, WhatsApp y dashboard en variables de entorno

**Contexto:** `11416` (2026-08-13): *"Live Meta API Tokens, WhatsApp API Key, and Dashboard Token Exposed in User Env Vars"* — un volcado de PowerShell los mostró. Están en variables de ámbito usuario de Windows, que es donde deben estar; **el problema no es dónde viven, sino que quedaron impresos en una sesión y por tanto en la memoria y en los logs.**

**Pasos:**
1. Identificar el alcance: qué permisos tiene cada token de Meta, y si la WhatsApp API key es de sistema o de usuario.
2. Rotar en el panel de Meta for Developers. Los tokens de WhatsApp Business tienen caducidad; comprobar si ya expiraron por sí solos.
3. Actualizar las variables de entorno de usuario.
4. **Regla operativa que sale de aquí:** nunca volcar `Get-ChildItem Env:` completo en una sesión. Si hace falta comprobar que una variable existe, comprobar solo su presencia, no su valor. Añadir la regla a `CLAUDE.md` global (mejora M-05 del índice).
5. Verificar que Bruce envía por WhatsApp y que el dashboard responde.

**Definition of done:** CE-5.1 y CE-5.10.

**Rollback:** restaurar las variables previas, conservadas hasta cerrar.

---

### T5.5 — [P0] Verificar si el keystore de Play Store está en el historial de git

**Contexto:** `5804` y `5857` (2026-07-12) registran que `upload-keystore.jks`, `keystore.properties` y `local.properties` aparecen en el árbol de trabajo de AgendaNiovalANDROID, y que **la verificación del historial de git era "prioridad máxima en Task 4" — que nunca se completó**. `7926` (07-20) dice que están correctamente excluidos, pero eso se refiere a `.gitignore`, **no al historial**: un archivo excluido hoy puede seguir en commits anteriores.

**Esta es la única de todo el plan con consecuencia irreversible.** Si el keystore de firma está en el historial y ese repositorio se publica o ya se publicó, se pierde el control de la identidad de firma de la app: cualquiera puede firmar actualizaciones que Play acepte como legítimas. **No se puede rotar un keystore de Play Store sin publicar una app nueva.**

**Pasos:**
1. En cada repo Android (AgendaNiovalANDROID, FinanzasAPPANDROID, AICHATROL y cualquier otro):
   ```
   git log --all --full-history --diff-filter=A -- "*.jks" "*.keystore" "*keystore.properties" "*key.properties" "local.properties"
   ```
2. Si hay resultados: determinar si el repo tiene remoto y si es público.
3. Si está en historial **y el remoto es público**: es un incidente. Hay que evaluar Play App Signing (si Google tiene la clave de firma real, la de upload es reemplazable) antes de asumir lo peor.
4. Si está en historial y el remoto es privado o no existe: reescribir historial con `git filter-repo` y forzar el push, coordinando con cualquier clon existente.
5. Documentar el resultado incluso si es negativo. **Un cero verificado es un resultado.**

**Definition of done:** CE-5.6, con la salida del `git log` pegada por repositorio.

**Rollback:** antes de cualquier `filter-repo`, clonar el repo completo al respaldo fechado. La reescritura de historial no se deshace.

---

### T5.6 — [P0] Honrar los opt-outs pendientes [CUMPLIMIENTO]

**Contexto:** `11356` (2026-08-13): *"SUPRESION_conflict Sheets May Contain Unread Opt-Outs — Contacts Who Requested STOP Could Still Receive Messages"*. Los conflictos de edición concurrente en Google Sheets crean pestañas `SUPRESION_conflict*` que el código de Bruce **nunca lee**, descartando en silencio las solicitudes de baja.

**No es una fuga de datos: es un incumplimiento.** Enviar mensajes a quien pidió no recibirlos infringe las políticas de WhatsApp Business —con riesgo de suspensión de la cuenta— y, según jurisdicción, normativa de protección de datos. **Es la observación con más consecuencia legal de las 77.**

Detalle que la hace peligrosa: está clasificada como `security_alert`, no como `sensitive`, así que no aparece en un filtro por PII.

**Pasos:**
1. Listar todas las pestañas `SUPRESION_conflict*` en las hojas afectadas y contar filas.
2. Consolidar esas bajas en la lista de supresión principal, deduplicando.
3. Verificar que ningún contacto de esa lista ha recibido mensajes **después** de su fecha de baja. Si los ha recibido, dimensionar cuántos y desde cuándo: eso determina si hay que notificar algo.
4. Corregir el código de Bruce para que lea todas las pestañas que casen con `SUPRESION*`, no solo la principal.
5. Añadir prueba de regresión: crear una pestaña de conflicto artificial y comprobar que la baja se respeta.

**Definition of done:** CE-5.7, más la prueba de regresión en verde.

**Rollback:** no aplica a las supresiones — suprimir de más es seguro; suprimir de menos es el fallo. El cambio de código se revierte con git.

---

### T5.7 — [P1] Rotaciones restantes

| Obs. | Credencial | Detalle |
|---|---|---|
| `6464` | Token de API de Cloudflare | Pegado en sesión junto a un `curl` de verificación (07-16) |
| `3183` | Clave de API de OpenAI | Enviada como contenido íntegro de un mensaje (07-03) |
| `6374` | Google Places API key | *"Rotation Still Pending"*. `11463` confirma que se quitó de `app.py` — **quitar del código no es rotar** |
| `8075` | `SL_META_ADLIB_TOKEN` | Viajó en la URL de un request y quedó en traceback (07-21) |
| `11269` | `SL_DASHBOARD_TOKEN` | Impreso en stdout de PowerShell (08-13) |

**Pasos:** para cada una — identificar consumidores (T5.0), rotar, actualizar consumidores, verificar que la vieja falla, y verificar que el consumidor sigue funcionando.

**Definition of done:** CE-5.1 para las cinco.

---

### T5.8 — [P1] Archivos de credencial en disco y privilegio mínimo

| Obs. | Qué | Acción |
|---|---|---|
| `11177` `11226` | JSON de cuenta de servicio de Google, sin cifrar, en la raíz del home y en `LlamadasSistema` | Mover a una ruta fuera de cualquier repo y de la raíz; apuntar el código por variable de entorno |
| `11245` | La cuenta de servicio usa **`auth/drive`** (todo Drive) en vez de `auth/spreadsheets` | Reducir alcance en Google Cloud. Da escritura sobre todos los archivos de Drive accesibles, no solo las 3 hojas necesarias |
| `7601` | **6 archivos** `client_secret*.json` de OAuth, de dos proyectos, en la raíz de `FinanzasAPPANDROID` | Retirar y, si alguno se usó, rotar el secreto de cliente |
| `8006` `7929` | `android/key.properties` con contraseña de keystore **commiteada** (un placeholder nunca rotado) | Rotar la contraseña, sacarla del archivo, añadir al `.gitignore` |

**Ojo con `11226`:** dice que `22.PY` **espera** las credenciales en el directorio de trabajo. Mover los archivos sin ajustar el código rompe `22.PY`. Ajustar primero, mover después.

**Definition of done:** CE-5.4 y CE-5.5.

---

### T5.9 — [P1] Eliminar PII en nombres de archivo

**Contexto:** `11242` (2026-08-12): archivos `debug_invalid_*.html/png` en la raíz del home **con números de teléfono completos de 6 clientes**, de una corrida de producción de octubre de 2025. Llevan ahí diez meses.

**Pasos:**
1. Localizarlos y confirmar el número exacto de archivos y de teléfonos distintos.
2. **Mover al respaldo fechado, no borrar** — pueden ser evidencia si el asunto de opt-outs (T5.6) resulta tener alcance.
3. Corregir el código que genera esos nombres para que use un hash o un identificador interno, no el teléfono.
4. Barrido de PII en nombres de archivo por todo el home: teléfonos, correos, nombres de cliente.

**Definition of done:** CE-5.8.

---

### T5.10 — Prevención: que esto no se vuelva a acumular

**Contexto:** el hallazgo estructural de T0.5. Los agentes detectaron todo correctamente —38 alertas precisas, con archivo, línea y recomendación— y **ninguna se cerró**, porque una `security_alert` en claude-mem es una nota: sin estado, sin dueño, sin verificación, sin recordatorio.

**Pasos:**
1. **Detección en pre-commit** (mejora M-02 del índice): `gitleaks` o equivalente en los 7 proyectos con git. Probar con un secreto falso en cada uno.
2. **Seguimiento de alertas:** un informe periódico que liste las `security_alert` y `sensitive` de los últimos N días sin observación de cierre asociada. `buscar-memoria.py --sensibles` ya da el insumo; falta el estado. Encaja con la mejora M-03 (censo programado).
3. **Regla en `CLAUDE.md` global** (mejora M-05): nunca volcar variables de entorno completas, nunca pegar credenciales en sesión, nunca poner valores por defecto silenciosos en gates de autenticación. Las tres reglas salen de fallos reales de este entorno, no de teoría.
4. **Convención de gates:** todo control de acceso falla **cerrado**. Si falta la variable, el servicio no arranca o devuelve 401 — nunca abre. Es la lección directa de PanelNioval.

**Definition of done:** CE-5.9, más las tres reglas escritas.

---

### T5.11 — Verificación final

1. Ejecutar los diez criterios de éxito y pegar la salida.
2. `buscar-memoria.py --sensibles` de nuevo: comprobar que las alertas nuevas generadas durante este plan documentan cierres, no aperturas.
3. Baseline funcional completo: Bruce envía, dashboard responde, worker opera, VSCode y CLI arrancan.
4. Actualizar la tabla PROGRESO y el marcador global del índice.

---

## 6. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

Fuentes usadas: **catalogo-agentes, ECC, community, claude-mem, superpowers, claude-ads, built-in** — **7 fuentes.** Es el único plan donde claude-ads aplica como ejecutora; ver §6.1.

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T5.0, todas | `claude-mem:mem-search` (vía `buscar-memoria.py`) | skill | claude-mem | **Obligatorio y decisorio.** Este plan entero existe porque una consulta a la memoria destapó el backlog. Cada tarea necesita saber qué se dijo antes sobre su credencial: quién la usaba, si ya se intentó rotar, qué se rompió. |
| A | T5.0 | `claude-mem:timeline` | skill | claude-mem | Reconstruir cuándo apareció cada credencial y en qué sesión, para acotar la ventana de exposición de cada una. |
| A | T5.0 | `Explore` | agente | built-in | Barrido de patrones de secreto sobre el home completo sin quemar contexto de la sesión principal. |
| A | T5.5 | `repo-scan` | skill | ECC | Estado real de los repos Android antes de tocar historial. |
| A | T5.0, T5.7 | `production-audit` | skill | community | "¿Qué se rompe si roto esto?" — la pregunta que decide el orden de cada rotación. |
| B | T5.5, T5.6 | `council` | skill | community | Dos decisiones con tradeoff real y consecuencias legales: reescribir historial de git vs. asumir la exposición, y cómo dimensionar el incumplimiento de opt-outs. Panel de 4 voces, no criterio único. |
| B | Todas | `blueprint` | skill | community | Cada tarea ejecutable por sesión fría. Estándar de la plantilla. |
| B | T5.10 | `superpowers:brainstorming` | skill | superpowers | Explorar qué mecanismo de seguimiento encaja de verdad en este entorno antes de fijar el diseño. Montar el mecanismo equivocado deja el problema igual con más ceremonia. |
| B | T5.6 | `legal-advisor` | agente | catalogo-agentes | El asunto de opt-outs tiene dimensión normativa (WhatsApp Business y protección de datos). Especialista, no criterio de ingeniero. |
| B | T5.10 | `architect` | agente | catalogo-agentes | La convención de "todo gate falla cerrado" es decisión de arquitectura transversal a los 7 proyectos. |
| C | T5.1-T5.4, T5.7 | `security-engineer` | agente | catalogo-agentes | Rotación de credenciales con consumidores vivos: el orden importa (actualizar consumidores → invalidar viejo), y equivocarlo tira producción. |
| C | T5.0, T5.9 | `powershell-7-expert` | agente | catalogo-agentes | Barridos, variables de entorno de usuario, movimientos de archivo en Windows. |
| C | T5.0 | `powershell-security-hardening` | agente | catalogo-agentes | Inventariar variables de entorno **sin volcar valores** — que es exactamente el fallo que originó `11416`. |
| C | T5.5 | `git-workflow-manager` | agente | catalogo-agentes | `git log --all --full-history --diff-filter=A` y, si procede, `filter-repo` con clon previo. La operación más delicada del plan. |
| C | T5.3 | `python-pro` | agente | catalogo-agentes | Migrar 30+ scripts a variables de entorno de forma idiomática, sin defaults silenciosos. |
| C | T5.3, T5.8 | `refactor-cleaner` | agente | catalogo-agentes | Extraer credenciales sin arrastrar refactorizaciones que este plan no autoriza. |
| C | T5.6 | `database-reviewer` | agente | catalogo-agentes | Consolidar y deduplicar las pestañas `SUPRESION_conflict` sin perder filas. |
| C | T5.8 | `cloud-architect` | agente | catalogo-agentes | Reducir el alcance de la cuenta de servicio de `auth/drive` a `auth/spreadsheets` sin romper los consumidores. |
| C | T5.10 | `gateguard` | skill | ECC | Ya activa en el grafo de hooks (`pre:edit-write:gateguard-fact-force`). Fuerza que las afirmaciones estén respaldadas por hechos — necesario cuando alguien declare "ya no hay secretos". |
| C | T5.10 | `hookify-rules` | skill | ECC | Convertir las tres reglas nuevas en hooks aplicables, no en párrafos de un documento que nadie relee. |
| C | T5.10 | `security-scan` | skill | ECC | Barrido reutilizable, base del informe periódico del paso 2. |
| C | T5.4, T5.7 | **`audit-tracking`** | skill | **claude-ads** | Los tokens de Meta Ad Library y de Meta API son credenciales de plataforma publicitaria. Esta skill audita píxeles y tokens de tracking: es la que sabe qué permisos concede cada token de Meta y qué se expone al rotarlo mal. **Aquí sí aplica.** |
| C | T5.4 | **`audit-meta`** | agente | **claude-ads** | Alcance y permisos de la cuenta de anuncios de Meta tras la rotación: comprobar que no se conceden más permisos de los necesarios al emitir el token nuevo. |
| D | Todas | `security-reviewer` | agente | catalogo-agentes | **Obligatorio en las 12 tareas.** Este plan es íntegramente credenciales y permisos. |
| D | Todas | `code-reviewer` | agente | catalogo-agentes | Gate general sobre todo cambio de código o configuración. |
| D | T5.1-T5.4, T5.7 | `security-auditor` | agente | catalogo-agentes | Segundo par de ojos independiente: `security-reviewer` juzga el cambio, `security-auditor` juzga si la rotación fue **completa** — si quedó un consumidor sin actualizar. |
| D | Todas | `silent-failure-hunter` | agente | catalogo-agentes | El modo de fallo dominante de este plan: se rota una credencial, un consumidor sigue con la vieja, falla en silencio y se descubre semanas después. Es el patrón que produjo las 38 alertas sin cerrar. |
| D | T5.3, T5.8 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack: los scripts migrados son Python. |
| D | T5.6 | `pr-test-analyzer` | agente | catalogo-agentes | ¿La prueba de regresión de opt-outs cubre el caso real —pestaña de conflicto creada por edición concurrente— o solo el feliz? |
| D | T5.10 | `penetration-tester` | agente | catalogo-agentes | [OPCIONAL] Validar que los gates fallan cerrados intentando saltárselos. Condición de uso: tras aplicar la convención del paso 4. |
| D | T5.11 | `superpowers:verification-before-completion` | skill | superpowers | Gate final. Ninguna credencial se declara rotada sin la prueba de que la vieja falla. |
| D | T5.11 | `verification-loop` | skill | ECC | Itera hasta verde en los 10 criterios. |
| E | Cierre | `pr` / `git-workflow` | skill | ECC | PR con commits `fix:` y `chore:` convencionales en español. |
| E | Cierre | `claude-mem:standup` | skill | claude-mem | **Crítico aquí:** persistir qué se rotó y cuándo, para que el próximo triage distinga una alerta cerrada de una abierta. Es lo que faltaba y lo que permitió que 38 alertas se acumularan. |
| E | Cierre | `doc-updater` + `technical-writer` | agente | catalogo-agentes | El inventario de credenciales y las tres reglas nuevas son entregables permanentes. |
| E | Cierre | `handoff` | skill | ECC | Contexto para retomar la migración (Planes 1-3) una vez cerrado este. |

### 6.1 — Evaluación de claude-ads: **SÍ aplica**

A diferencia de los Planes 0, 1, 2 y 3 —donde se justificó por escrito que no aplicaba y se dejó como contingencia condicionada—, **aquí la condición de activación se cumple.**

`11416` documenta *"Live Meta API Tokens"* expuestos, y `8075` un `SL_META_ADLIB_TOKEN` filtrado en un traceback. Son credenciales de plataforma publicitaria, y `audit-tracking` y `audit-meta` son las herramientas de la biblioteca que entienden qué concede cada token de Meta, qué permisos pedir al emitir el nuevo y qué queda expuesto si se rota mal.

La contingencia declarada en los planes anteriores era exactamente esta. Se activa.

---

## 7. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Gate obligatorio | Gate de seguridad | Gate adicional |
|---|---|---|---|
| T5.0 | `code-reviewer` | `security-reviewer` **crítico** | Inventario sin ningún valor de credencial escrito |
| T5.1 | `security-reviewer` + `security-auditor` | — | Clave vieja → 403; MCP `nanobanana` operativo |
| T5.2 | `security-reviewer` + `security-auditor` | — | Bruce operativo **antes** de invalidar la vieja |
| T5.3 | `python-reviewer` + `code-reviewer` | `security-reviewer` **crítico** | Los 5 bots envían; `22.PY` respaldado antes de tocarlo |
| T5.4 | `security-reviewer` + `audit-meta` | — | WhatsApp envía; dashboard responde |
| T5.5 | `git-workflow-manager` | `security-reviewer` **crítico** | Clon completo al respaldo **antes** de cualquier reescritura |
| T5.6 | `legal-advisor` + `pr-test-analyzer` | `security-reviewer` | Prueba de regresión con pestaña de conflicto artificial |
| T5.7 | `security-reviewer` + `security-auditor` | — | Consumidor de cada credencial verificado |
| T5.8 | `code-reviewer` + `cloud-architect` | `security-reviewer` **crítico** | `22.PY` ajustado **antes** de mover archivos |
| T5.9 | `code-reviewer` | `security-reviewer` | Archivos movidos, no borrados |
| T5.10 | `architect` + `code-reviewer` | `security-reviewer` **crítico** | Commit de prueba bloqueado en los 7 repos |
| T5.11 | `superpowers:verification-before-completion` | `security-reviewer` | Los 10 CE en verde |

## 8. BASELINE DE NO REGRESIÓN

Este plan toca producción viva. Tras **cada** tarea:

1. **Bruce envía un mensaje de WhatsApp** de prueba correctamente.
2. **El dashboard de PanelNioval responde** con el token (y 401 sin él).
3. **El worker local opera.**
4. VSCode abre Claude y el CLI responde.

Si una falla, se revierte esa tarea antes de seguir. **A diferencia de los Planes 0-3, aquí una regresión afecta a clientes reales, no a comodidad.**

## 9. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback concreto |
|---|---|---|---|---|---|
| R5.1 | Rotar una credencial deja un consumidor sin actualizar y algo falla en silencio | **Alta** | **Alto** | T5.0 identifica consumidores **antes**; orden obligatorio: actualizar consumidores → invalidar viejo; `silent-failure-hunter` como gate | Restaurar el valor previo, conservado hasta cerrar cada tarea |
| R5.2 | `git filter-repo` en un repo Android destruye historial o rompe clones | Media | **Crítico** | Clon completo al respaldo antes; evaluar Play App Signing antes de asumir lo peor | Restaurar desde el clon del respaldo. **La reescritura no se deshace de otro modo** |
| R5.3 | Mover los JSON de cuenta de servicio rompe `22.PY`, que los espera en el CWD | **Alta** | Medio | T5.8 ajusta el código **antes** de mover | Devolver los archivos a su ruta original |
| R5.4 | Rotar el token de Meta con permisos distintos rompe el envío de WhatsApp | Media | **Alto** | `audit-meta` verifica permisos del token nuevo antes de sustituir | Restaurar variable previa; los tokens de WhatsApp Business caducan solos, así que puede no haber vuelta atrás — motivo para verificar antes |
| R5.5 | Consolidar opt-outs suprime contactos de más | Baja | Bajo | Suprimir de más es seguro; suprimir de menos es el fallo que se está corrigiendo | Ninguno necesario; la asimetría del riesgo es intencional |
| R5.6 | Se rota todo y la memoria conserva los valores viejos, dando falsa sensación de fuga | Media | Bajo | T0.5 §7 ya lo resuelve: rotada, la credencial en memoria es inerte. **No purgar** | No aplica |
| R5.7 | El plan se ejecuta a medias y quedan credenciales sin rotar sin que nadie lo note | **Alta** | Alto | Es literalmente lo que ya pasó 38 veces. T5.10 monta el seguimiento; la tabla PROGRESO es el registro | No aplica: es el riesgo que el plan existe para eliminar |
| R5.8 | `22.PY` no tiene control de versiones y un cambio lo rompe sin vuelta atrás | Media | Medio | T5.3 lo copia al respaldo antes de tocarlo | Restaurar desde el respaldo fechado |

---

## 10. TABLA PROGRESO

| # | Tarea | Prioridad | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|---|
| T5.0 | Inventario en vivo de credenciales y consumidores | **BLOQUEANTE** | PENDIENTE | | |
| T5.1 | Rotar `GEMINI_API_KEY` y `STITCH_API_KEY` | **P0** | PENDIENTE | | |
| T5.2 | Rotar `ADMIN_API_KEY` | **P0** | PENDIENTE | | |
| T5.3 | Rotar y migrar los 5 tokens de Telegram | **P0** | PENDIENTE | | |
| T5.4 | Rotar tokens de Meta, WhatsApp y dashboard | **P0** | PENDIENTE | | |
| T5.5 | Verificar keystore de Play Store en historial de git | **P0** | PENDIENTE | | |
| T5.6 | Honrar los opt-outs pendientes (cumplimiento) | **P0** | PENDIENTE | | |
| T5.7 | Rotaciones restantes (Cloudflare, OpenAI, Places, Meta AdLib, SL Dashboard) | P1 | PENDIENTE | | |
| T5.8 | Archivos de credencial en disco y privilegio mínimo | P1 | PENDIENTE | | |
| T5.9 | Eliminar PII en nombres de archivo | P1 | PENDIENTE | | |
| T5.10 | Prevención: pre-commit, seguimiento de alertas y reglas | — | PENDIENTE | | |
| T5.11 | Verificación final | — | PENDIENTE | | |

**Avance del Plan 5: 0/12 tareas HECHAS (0%).**

**Orden recomendado:** T5.0 primero y sin excepción. Después las seis P0 en paralelo si hay capacidad, o en este orden si es secuencial: **T5.5** (única con consecuencia irreversible — saber cuanto antes si hay incidente), **T5.6** (cumplimiento, se acumula cada día que pasa), **T5.1** (probada activa), **T5.2** (producción y adivinable), **T5.3** (mayor extensión), **T5.4**. Luego P1, y T5.10 al final para que las reglas que se escriban recojan lo aprendido ejecutando.
