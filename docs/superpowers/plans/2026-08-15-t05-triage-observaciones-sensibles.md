# T0.5 — TRIAGE DE LAS 77 OBSERVACIONES SENSIBLES Y DE SEGURIDAD

**Plan 0, tarea T0.5** · Ejecutado el 2026-08-15
**Fuente:** `_respaldo-migracion-2026-08-15\claude-mem\claude-mem.db` (copia verificada, solo lectura)
**Método:** consulta SQL directa. `claude-mem:mem-search` no disponible (MCP no conectado); sustitución declarada.

> **Este documento no contiene ningún valor de credencial.** Las referencias son a nombre de variable, archivo y línea. Cualquier valor concreto se omite deliberadamente, incluso los que aparecen en claro en la base de origen.

---

## 1. Censo

| Métrica | Valor |
|---|---|
| Total | **77** |
| `security_alert` | 38 |
| `security_note` | 28 |
| `sensitive` | 11 |
| Proyecto BruceWhatsapp | 73 |
| Proyecto SistemaLanzamiento | 4 |
| Rango temporal | 2026-06-11 → 2026-08-14 |

**Ninguna sin clasificar. 77/77 con categoría asignada.**

---

## 2. Veredicto general

El token de Railway que motivó el Plan 0 **era el hallazgo menor**. La memoria documenta una acumulación de credenciales expuestas a lo largo de dos meses, muchas señaladas repetidamente y **ninguna con evidencia de rotación**.

El patrón que se repite: un agente detecta la exposición, la registra correctamente, recomienda rotar — y ahí muere. La observación queda escrita y nadie vuelve a ella. **Nueve credenciales distintas fueron marcadas como "rotación requerida" o "rotación pendiente" y en ningún caso hay una observación posterior que confirme la rotación.**

Tres casos ilustran la gravedad:

- **`GEMINI_API_KEY`**: el 2026-07-17 se probó en vivo y devolvió *HTTP 200 con acceso completo a la lista de modelos*. Se volvió a marcar el 26, 27 y 28 de julio. **Cuatro alertas en once días sobre la misma clave activa.**
- **`ADMIN_API_KEY`**: descrita como *"short, guessable static string used in both local and Railway production"*. Es la llave de administración del sistema en producción, y es adivinable.
- **Token de Telegram en `22.PY`**: marcado el 12, 13 y 14 de agosto. *"presente en ~14 proyectos"*, y una auditoría más amplia encontró *"5 distinct Telegram bot tokens hardcoded across 30+ local scripts"*.

---

## 3. Categoría (a) — SECRETO REAL, SIN EVIDENCIA DE ROTACIÓN → **rotar**

Ordenadas por urgencia. Ninguna tiene observación posterior que confirme rotación.

| # | Obs. | Credencial | Dónde | Detectado | Nota |
|---|---|---|---|---|---|
| a1 | `6891` `6897` `6898` `9398` `9404` `9464` | **`GEMINI_API_KEY`** y **`STITCH_API_KEY`** | `~/.claude.json`, bloque `env` del MCP nanobanana, en texto plano | 07-17 → 07-28 | **Probada viva el 07-17: HTTP 200.** Marcada 4 veces. Ambas con prefijo `AQ.` |
| a2 | `593` `10540` | **`ADMIN_API_KEY`** | Compartida en chat; usada en local **y en producción Railway** | 06-25, 07-31 | *"short, guessable static string"*. Confirmada funcionando el 07-31 |
| a3 | `11181` `11205` `11216` `11219` `11223` `11294` `11452` `11453` `11462` `11469` | **Token de bot de Telegram** (ID `84040…`) | `22.PY` líneas 62-63, más *~14 proyectos* y *30+ scripts*; también verbatim en 5 documentos de plan | 08-12 → 08-14 | **10 observaciones en 3 días.** La auditoría encontró **5 tokens distintos** de Telegram hardcodeados |
| a4 | `11416` | **Tokens de Meta API, WhatsApp API key y dashboard token** | Variables de entorno de usuario de Windows | 08-13 | *"Live"*, *"production secrets"* |
| a5 | `6464` | **Token de API de Cloudflare** | Pegado en sesión junto a un `curl` de verificación | 07-16 | *"live Cloudflare Bearer token"* |
| a6 | `3183` | **Clave de API de OpenAI** | Enviada como contenido íntegro de un mensaje de usuario | 07-03 | |
| a7 | `6374` | **Google Places API key** | BruceWhatsapp | 07-16 | *"Rotation Still Pending"*. `11463` (08-14) confirma que se quitó de `app.py`, **pero eso no es rotar** |
| a8 | `8075` | **`SL_META_ADLIB_TOKEN`** | Viajó en la URL de un request y quedó en traceback de log | 07-21 | |
| a9 | `11269` | **`SL_DASHBOARD_TOKEN`** | Impreso en stdout de PowerShell | 08-13 | |

**Acción recomendada:** rotar las nueve. Empezar por a1 (probada activa), a2 (producción y adivinable) y a3 (extensión masiva).

---

## 4. Categoría (b) — CREDENCIALES EN ARCHIVO, EN DISCO → **mover y restringir**

| # | Obs. | Qué | Dónde |
|---|---|---|---|
| b1 | `11177` `11226` | JSON de cuenta de servicio de Google, sin cifrar | **Raíz del directorio home** (`C:\Users\PC 1\`) y en `LlamadasSistema` |
| b2 | `11245` | La misma cuenta de servicio usa alcance **`auth/drive`** (todo Drive) en lugar de `auth/spreadsheets` | Sobreprivilegio: da escritura sobre todos los archivos de Drive accesibles, no solo las 3 hojas de negocio |
| b3 | `7601` | **6 archivos** `client_secret*.json` de OAuth de Google, de dos proyectos distintos | Raíz del repo `FinanzasAPPANDROID` (sin trackear) |
| b4 | `8006` `7929` | `android/key.properties` con contraseña de keystore **commiteada** | Placeholder nunca rotado, en control de versiones |
| b5 | `5804` `5857` | `upload-keystore.jks`, `keystore.properties`, `local.properties` de firma de Play Store | Presentes en árbol de trabajo; **verificación del historial de git nunca completada** |

**b5 es la de mayor consecuencia irreversible**: si el keystore de firma de Play Store está en el historial de git y ese repo se publica, se pierde el control de la identidad de firma de la app.

---

## 5. Categoría (c) — PII Y CUMPLIMIENTO → **acción legal/operativa, no técnica**

| # | Obs. | Qué |
|---|---|---|
| c1 | `11242` | **Números de teléfono reales de 6 clientes** embebidos en nombres de archivo `debug_invalid_*.html/png`, en la raíz del home. De una corrida de producción de octubre de 2025 |
| c2 | `11356` | **`SUPRESION_conflict`: contactos que pidieron STOP pueden seguir recibiendo mensajes.** Los conflictos de edición concurrente en Google Sheets crean pestañas `SUPRESION_conflict*` que el código de Bruce nunca lee, descartando silenciosamente las bajas |

**c2 no es una fuga: es un incumplimiento.** Enviar mensajes a quien pidió no recibirlos infringe las políticas de WhatsApp Business y, según jurisdicción, normativa de protección de datos. **Es la observación con más consecuencia legal de las 77**, y no está marcada como `sensitive` sino como `security_alert`, por lo que pasa desapercibida en cualquier filtro por tipo.

---

## 6. Categoría (d) — RESUELTAS O SIN ACCIÓN → **conservar, no tocar**

Las 28 `security_note` y varias `security_alert` documentan trabajo hecho y son contexto valioso:

- `1061` `.env` de FinanzasAPP confirmado en gitignore · `7926` keystore correctamente excluido · `8042` regla de `.gitignore` antes de `git init` · `11254` política estricta de secretos y PII en SistemaLanzamiento
- `6688` validación MIME por magic-bytes · `6698` `usesCleartextTraffic` eliminado, `allowBackup=false` · `11498` escrituras RAW previenen inyección de fórmulas · `11246` sin riesgo de inyección JS en Selenium
- `6597` `CLAVE_PULL` movido a Cloudflare Secrets · `6189` `ELEVENLABS_API_KEY` extraída a `.env` · `8207` IDs de Meta quitados de documentación · `11295` `11459` `11463` gates pre-commit funcionando
- `8` `11` falsos positivos confirmados en la auditoría inicial de repos

**Ninguna de estas debe purgarse.** Documentan decisiones y arreglos, y son exactamente el contexto que `mem-search` debe devolver en la etapa A de futuros planes.

---

## 7. Sobre purgar filas de la base

**Recomendación: no purgar ninguna de las 77.**

El Plan 0 contemplaba purgar las de categoría (a) tras rotar. Tras el triage, la recomendación cambia: **el valor de contexto supera al riesgo residual.** Razones:

1. La base es local, en el disco del usuario, no sincronizada a ningún servicio (`sync_state` vacía, Chroma apagado).
2. Los títulos y subtítulos —que es lo que devuelve `mem-search`— **no contienen valores de credencial** salvo excepciones puntuales. El riesgo está en el campo `text`/`facts` de unas pocas.
3. Purgar destruye la trazabilidad de qué se detectó y cuándo, que es justo lo que ha permitido este triage.
4. **Una vez rotadas, las credenciales de categoría (a) son cadenas inertes**, igual que el token de Railway.

**Excepción a evaluar caso por caso:** `593` contiene el valor literal de `ADMIN_API_KEY` en el subtítulo. Tras rotarla, deja de importar. Si no se rota, esa fila es un riesgo por sí misma.

---

## 8. Lo que este triage dice del sistema, no de las credenciales

El hallazgo estructural no es ninguna clave concreta: es que **el pipeline de detección funciona perfectamente y el de remediación no existe.**

Los agentes detectaron todo. Escribieron alertas precisas, con archivo, línea y recomendación. Lo hicieron 38 veces. Y **ninguna alerta tiene un mecanismo que la persiga hasta cerrarla**: no hay estado, ni responsable, ni recordatorio, ni verificación posterior. Una `security_alert` en claude-mem es una nota, no un ticket.

Es el mismo patrón que `CAPTURE_BROKEN`: el sistema detectó el fallo, escribió el archivo, y pasaron 36 días sin que nadie lo mirara.

**Propuesta:** un plan propio de remediación de credenciales, fuera del alcance de esta migración, con una tarea por credencial y verificación de rotación como gate. Nueve rotaciones, cinco movimientos de archivo y dos acciones de cumplimiento. Ese plan tiene más impacto sobre el riesgo real que los Planes 1, 2 y 3 juntos.

---

## 9. Tabla PROGRESO de la remediación (para el plan futuro)

| # | Acción | Prioridad | Estado | Evidencia | Fecha |
|---|---|---|---|---|---|
| a1 | Rotar `GEMINI_API_KEY` y `STITCH_API_KEY`; sacarlas de `~/.claude.json` | **P0** | PENDIENTE | | |
| a2 | Rotar `ADMIN_API_KEY` por un valor largo y aleatorio; actualizar local y Railway | **P0** | PENDIENTE | | |
| a3 | Rotar los 5 tokens de Telegram; migrar `22.PY` y los 30+ scripts a variables de entorno | **P0** | PENDIENTE | | |
| a4 | Rotar tokens de Meta y WhatsApp API; revisar variables de entorno de usuario | **P0** | PENDIENTE | | |
| a5 | Rotar token de Cloudflare | P1 | PENDIENTE | | |
| a6 | Rotar clave de OpenAI | P1 | PENDIENTE | | |
| a7 | Rotar Google Places API key (quitarla del código no la rota) | P1 | PENDIENTE | | |
| a8 | Rotar `SL_META_ADLIB_TOKEN` | P1 | PENDIENTE | | |
| a9 | Rotar `SL_DASHBOARD_TOKEN` | P1 | PENDIENTE | | |
| b1 | Mover los JSON de cuenta de servicio fuera de la raíz del home | P1 | PENDIENTE | | |
| b2 | Reducir alcance de la cuenta de servicio a `auth/spreadsheets` | P1 | PENDIENTE | | |
| b3 | Retirar los 6 `client_secret*.json` de la raíz de FinanzasAPPANDROID | P1 | PENDIENTE | | |
| b4 | Rotar la contraseña de keystore y sacarla de `key.properties` | P1 | PENDIENTE | | |
| b5 | **Verificar si el keystore de Play Store está en el historial de git** | **P0** | PENDIENTE | | |
| c1 | Eliminar los artefactos de debug con teléfonos de clientes | P1 | PENDIENTE | | |
| c2 | **Leer las pestañas `SUPRESION_conflict` y honrar las bajas pendientes** | **P0** | PENDIENTE | | |

**17 acciones. 6 en P0.**
