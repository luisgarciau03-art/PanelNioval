# ADR — Transporte de envío de catálogo por WhatsApp

**Fecha:** 2026-08-13 · **Estado:** ACEPTADA (decisión del owner) · **Contexto:** Plan 5, tanda PanelNioval 2026-08-13.

## Contexto

El panel (`app.py`) ya corre en Railway. El envío de catálogo (`envio_catalogo.py`) usa Selenium sobre WhatsApp Web con un perfil Chrome local y sesión escaneada por QR, más archivos en `C:/Users/PC 1/Files mensajes` — **no portable a Railway** (FS efímero, sin GUI/QR; ver matriz de portabilidad del Plan 1). La cola `ENVIOS_CATALOGO` (Plan 3) es transport-agnostic.

## Opciones consideradas

| Opción | Independencia de la PC | Riesgo de baneo | Costo | Validación de entrega | Esfuerzo |
|---|---|---|---|---|---|
| **A — WhatsApp Business Cloud API** | Total (100% Railway) | Nulo (oficial) | Por conversación (Meta) | Real (webhooks sent/delivered/failed) | Alto (alta Meta, plantillas, número) |
| **B — Worker local + Railway orquesta** | Ninguna (depende de la PC encendida) | Igual que hoy (WA Web) | Cero | NUMERO_INVALIDO por popup (como hoy) | Bajo (reusa el transporte actual) |
| **C — Selenium headless en Railway** | Total pero frágil | Alto (detección/baneo) | Bajo | Popup (frágil) | Medio-alto (QR + volumen persistente) |

## Decisión

**Opción B — Worker local + Railway orquesta.** (Elegida por el owner el 2026-08-13.)

- Railway mantiene el panel, la cola (`ENVIOS_CATALOGO`) y los endpoints (`/api/catalogo/*`).
- Un worker en la PC del owner (`worker_catalogo_run.py`, instalado como Tarea Programada con `instalar-worker.ps1`) hace polling de la cola, ejecuta el transporte Selenium actual y escribe el estado final. Reporta un **heartbeat** al panel (`/api/catalogo/heartbeat`) para que se vea "worker vivo/muerto".
- **Cero costo Meta, cero cambio de transporte.** Contra: sigue dependiendo de que la PC esté encendida — se acepta como operación actual/transición; migrar a la opción A (recomendada a futuro) queda documentado.

## Consecuencias

- La cola es la fuente de verdad; el transporte es inyectable (`worker_catalogo.procesar_cola(ws, transporte, ...)`), así que migrar a A en el futuro solo cambia el "enviador" (`transporte_whatsapp_api.py`) sin tocar panel ni cola.
- La validación "no le llegó" sigue siendo NUMERO_INVALIDO (popup), no entrega verificada (eso lo daría la opción A).
- **Gates del owner antes del go-live (T5.3):** rotar `TELEGRAM_TOKEN` (bot `8404009072`, ~14 copias en el historial) y la Google Places key; cargar secretos en Railway. Recomendado activar `PANEL_DASHBOARD_TOKEN` (M1) antes de dejar el worker corriendo desatendido (cierra FC2).
