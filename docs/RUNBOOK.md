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
# 1. Variables de entorno del sistema (una vez):
setx TELEGRAM_TOKEN "<token rotado>"
setx TELEGRAM_CHAT_ID "5838212022"
setx PANEL_URL "https://<tu-app>.up.railway.app"
setx WORKER_TOKEN "<opcional>"
# (y GOOGLE_CREDENTIALS_JSON o el .json local del panel en la carpeta)

# 2. Instalar como Tarea Programada (cada 15 min):
.\instalar-worker.ps1 -IntervaloMinutos 15

# 3. Correr una vez a mano para escanear el QR de WhatsApp Web la primera vez:
python worker_catalogo_run.py
```

Quitar la tarea: `Unregister-ScheduledTask -TaskName NIOVAL_WorkerCatalogo -Confirm:$false`.

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
