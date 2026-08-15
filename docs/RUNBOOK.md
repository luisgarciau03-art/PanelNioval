# RUNBOOK — Operación de PanelNioval + envío de catálogo

Guía operativa para el owner. Arquitectura: **panel en Railway** + **worker local** que envía el catálogo por WhatsApp Web (decisión ADR `docs/adr/2026-08-13-transporte-catalogo.md`).

## Flujo completo

1. El operador usa `/formulario` (Railway) y cierra llamadas.
2. Al cerrar con **"Pedido"** o **"Revisará el Catálogo"**, el panel encola un envío `PENDIENTE` en la worksheet `ENVIOS_CATALOGO`.
3. Al cerrar con **"Correo"**, un modal captura el correo → se guarda en la columna **T** de `LISTA DE CONTACTOS`.
4. El **worker local** (PC del owner) procesa la cola: envía por WhatsApp Web y marca `ENVIADO` / `NUMERO_INVALIDO` / `FALLO`.
5. Si un número es inválido, el operador usa **"Revisar envíos con problema"** en `/formulario` → corrige el número → se re-encola.

## Puesta en marcha del worker (PC del owner)

```powershell
# 1. Credencial de Google en la carpeta del proyecto (el .json del service account,
#    p.ej. bubbly-subject-412101-c969f4a975c5.json) — o la env GOOGLE_CREDENTIALS_JSON.

# 2. Variables de entorno persistentes (una vez):
setx WA_ENVIO_PASSWORD "<tu-contraseña>"   # gate de envío
setx WA_ENVIO_ARMADO 1                      # 1 = autoriza envío automático; 0 = pausa
setx TELEGRAM_TOKEN "<token rotado>"        # opcional (reportes)
setx TELEGRAM_CHAT_ID "5838212022"
setx PANEL_URL "https://<tu-app>.up.railway.app"   # opcional (heartbeat)

# 3. Iniciar sesión de WhatsApp Web en el perfil del worker (SOLO la primera vez o si expira):
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="C:\Users\PC 1\ChromeSeleniumProfile" --profile-directory=Default https://web.whatsapp.com
#   → escanea el QR, espera a que carguen TODOS tus chats, y CIERRA esa ventana.

# 4. Instalar como Tarea Programada (cada 15 min):
.\instalar-worker.ps1 -IntervaloMinutos 15

# 5. Probar a mano (una corrida):
python worker_catalogo_run.py

# 5b. MODO CONTINUO (recomendado para envío casi inmediato): abre WhatsApp una vez
#     y procesa la cola cada 15s. Déjalo corriendo en una ventana.
python worker_catalogo_run.py --loop
#     (intervalo configurable con  setx WORKER_LOOP_SECS 15  ; salir con Ctrl+C)
```

Quitar la tarea: `Unregister-ScheduledTask -TaskName NIOVAL_WorkerCatalogo -Confirm:$false`.

- **Modo continuo vs Tarea Programada:** en modo continuo (`--loop`) el envío ocurre a los segundos de cerrar la llamada (ideal con el validador pre-envío). La Tarea Programada (cada 15 min) sirve como respaldo si prefieres no dejar una ventana abierta. No uses ambos a la vez con la misma sesión (el perfil de Chrome no admite 2 instancias).
- **Detener el envío:** la autorización (`WA_ENVIO_ARMADO`) se evalúa al ARRANCAR el worker; para frenar un worker ya corriendo, **ciérralo (Ctrl+C / matar el proceso)** — cambiar la env var a media corrida no lo detiene.

### Notas de operación (aprendidas en la prueba real 2026-08-15)

- **El worker usa un Chrome/perfil APARTE** (`ChromeSeleniumProfile`), no tu Chrome de siempre. Su sesión de WhatsApp se inicia una vez (paso 3) y persiste.
- **Cierra cualquier Chrome que use ese perfil antes de correr el worker** (el perfil no admite 2 instancias a la vez).
- Si ves `spinner`/timeout al abrir chats, casi siempre es que **WhatsApp Web no terminó de sincronizar** o **la sesión expiró** (repite el paso 3).
- El arranque del worker tarda ~1 min en cargar dependencias (imprime `[worker] cargando dependencias...`); es normal, **no lo interrumpas**.
- **Formato de teléfono México:** `52` + 10 dígitos (ej. `526623534185`).
- **`Video1.mp4`** debe existir en `C:\Users\PC 1\Files mensajes` para enviar el video; si falta, el resto de archivos igual se envían.

## Gate de seguridad de envío (contraseña)

El worker **no envía nada** sin autorización explícita (para evitar disparos accidentales):

- Define `WA_ENVIO_PASSWORD` (ej. una contraseña fuerte) en la PC del owner.
- **Corrida manual** (`python worker_catalogo_run.py` en una terminal): el worker **solicita la contraseña** y la valida antes de abrir WhatsApp.
- **Tarea Programada** (no interactiva): además de `WA_ENVIO_PASSWORD`, se exige `WA_ENVIO_ARMADO=1` para que envíe. Sin ese flag, la corrida no envía (queda "desarmada"). Así puedes tener la tarea instalada pero pausada hasta que la armes.

## Ver estados

- **Envíos:** `GET /api/catalogo/envios?estado=PENDIENTE|ENVIADO|NUMERO_INVALIDO|FALLO`.
- **Worker vivo/muerto:** `GET /api/catalogo/worker-estado` (`vivo=true` si hubo heartbeat en los últimos 15 min).
- **Reintentar** un `FALLO`/`NUMERO_INVALIDO`: `POST /api/catalogo/reintentar {envio_row}` o el modal del formulario.

## Smoke test post-deploy

```bash
python tools/smoke_railway.py https://<tu-app>.up.railway.app [--token PANEL_DASHBOARD_TOKEN]
```
Debe imprimir `Todo OK ✅`. Railway auto-deploya `main`: correr el smoke tras cada merge.

## Verificar la hoja de contactos (antes de capturar correos)

```bash
python tools/inspeccionar_contactos.py   # confirma que la columna T está libre
```

## Qué hacer si algo falla

| Síntoma | Causa probable | Acción |
|---|---|---|
| `worker-estado` = `vivo:false` | PC apagada / tarea detenida / QR expirado | Encender PC; `python worker_catalogo_run.py` y re-escanear QR |
| Muchos `FALLO` | WhatsApp Web cambió selectores o sesión caída | Re-escanear QR; revisar `envio_catalogo.py` (selectores `data-icon`) |
| Muchos `NUMERO_INVALIDO` | Teléfonos mal capturados | Corregir número desde el modal |
| Panel 401 en todo | `PANEL_DASHBOARD_TOKEN` activo | Acceder con `?token=<valor>` una vez (queda en la sesión) |
| Envíos duplicados | Dos corridas del worker solapadas | El lock lo previene; no correr 2 instancias manuales a la vez |

## Gates del owner pendientes (seguridad)

- **Rotar** `TELEGRAM_TOKEN` (bot `8404009072`, expuesto en ~14 copias del historial) y la **Google Places key**; cargarlas en Railway.
- **Activar `PANEL_DASHBOARD_TOKEN`** para cerrar el acceso abierto del panel (FC2) antes de dejar el worker desatendido.
- **Corrida real de WhatsApp** (T5.5): 1 llamada de prueba end-to-end con un número propio.
