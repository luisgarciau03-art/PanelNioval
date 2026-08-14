# Plan 3 — Diseño de la cola de envío de catálogo (contrato aprobado)

**Fecha:** 2026-08-13 · **Rama:** `plan3/integracion-catalogo` · **Decisión owner T3.1:** "Pedido" **Y** "Revisará el Catálogo" disparan envío. **Transporte (Plan 5):** B = worker local.

## 1. Almacenamiento

Worksheet **`ENVIOS_CATALOGO`** en el spreadsheet de respuestas (`SHEET_IDS['respuestas']`). Encabezados (orden fijo, `nucleo_catalogo.COLUMNAS_ENVIOS`):

`fecha_solicitud · tienda · telefono · fila_respuesta · conclusion · estado · intentos · timestamp_estado · detalle`

- **`fila_respuesta`** guarda la **fila del contacto en LISTA DE CONTACTOS** (`O.contacto._row`), que es el identificador estable que el cliente conoce y la **clave de idempotencia**.
- La worksheet se crea automáticamente con encabezados la primera vez (`_abrir_ws_envios`).

## 2. Máquina de estados

```
PENDIENTE ──(worker toma)──► EN_PROCESO ──► ENVIADO        (terminal)
                                        ├──► NUMERO_INVALIDO ──(corregir nº)──► PENDIENTE
                                        └──► FALLO ──────────(reintentar)─────► PENDIENTE
```

`nucleo_catalogo.TRANSICIONES` es la fuente de verdad. `ENVIADO` es terminal. `NUMERO_INVALIDO`/`FALLO` son reintentables (→ PENDIENTE).

**Honestidad de estados (limitación de WhatsApp Web):** la "entrega" real (doble check) NO es detectable de forma fiable. `NUMERO_INVALIDO` (popup "número no válido" detectado) es el caso "no le llegó" que dispara la corrección; `ENVIADO` = el mensaje salió del chat; `FALLO` = el chat no cargó / error de envío. Se comunica así al owner.

## 3. Contrato de endpoints (todos en `app.py`)

| Endpoint | Entrada | Efecto |
|---|---|---|
| `POST /api/catalogo/encolar` | `{tienda, telefono, referencia(int), conclusion}` | Si `conclusion` elegible y `referencia` no encolada → fila PENDIENTE. Idempotente. `{ok, estado\|motivo}` |
| `GET /api/catalogo/envios?estado=` | query `estado` opcional | Lista los envíos (dict + `_row`), filtrada |
| `POST /api/catalogo/corregir-numero` | `{envio_row(int), telefono, contacto_row?}` | Valida nº (10-13 díg), actualiza `telefono` + estado→PENDIENTE + intentos+1 en ENVIOS; si `contacto_row`, actualiza también el teléfono en LISTA DE CONTACTOS |
| `POST /api/catalogo/reintentar` | `{envio_row(int)}` | Si transición válida → estado PENDIENTE |

**Decisión encolado (council backend-inline vs endpoint-aparte):** se eligió **endpoint aparte** (`/api/catalogo/encolar`, llamado por el JS tras un guardado exitoso). Razón: NO acopla la cola a `guardar_respuesta_formulario` (preserva intactos sus tests de caracterización del Plan 2), es transport-agnostic y testeable en aislamiento; el costo (1 request extra) es aceptable y el encolado es no-bloqueante para el operador (si falla, se avisa con una nota, no se pierde el guardado de la respuesta).

## 4. Worker (transporte = B, worker local)

`worker_catalogo.py` (lógica pura + orquestación) + transporte inyectable:
- `seleccionar_pendientes(filas)` / `procesar_envio(reg, transporte, mensajes, archivos)` / `procesar_cola(ws, transporte, ...)`.
- **Transporte real:** el owner lo corre en su PC (donde vive la sesión de WhatsApp Web), envolviendo `envio_catalogo.py`. Un `ResultadoEnvio(estado, detalle)` honesto por intento.
- Toda excepción del transporte se convierte en `FALLO` con detalle (los `except: pass` del script original NO sobreviven al worker).

**Cómo lo corre el owner (Plan 5, worker local):**
```bash
set TELEGRAM_TOKEN=...   &  set TELEGRAM_CHAT_ID=...
python -m worker_catalogo_run   # (script de arranque que conecta gspread + transporte Selenium)
```
El arranque real (`worker_catalogo_run.py`) queda como entregable operativo del Plan 5; en Plan 3 se entrega la lógica testeada con transporte FAKE.

## 5. Idempotencia y anti-duplicados

- Clave: `fila_respuesta` (= fila del contacto). Encolar dos veces la misma → `ya_encolado`, no duplica (`indice_por_fila_respuesta`).
- `EN_PROCESO` actúa como lock lógico: `worker_catalogo.procesar_cola` marca cada fila `EN_PROCESO` **antes** de invocar el transporte, y `seleccionar_pendientes` solo toma `PENDIENTE`.
- El worker escribe estado final por fila; el panel refleja el estado.

## 6. Review (4 revisores) — hallazgos y estado

Auditado por code/python/security/silent-failure. **Fixes aplicados en este plan:**
- **CRITICAL** — `corregir-numero` bypassaba la FSM (podía re-encolar un `ENVIADO`) → ahora valida `transicion_valida(estado, PENDIENTE)` (solo `NUMERO_INVALIDO`/`FALLO`). ✅
- **HIGH** — `_abrir_ws_envios` capturaba `Exception` amplio → ahora solo `WorksheetNotFound`. ✅
- **HIGH** — mapa de columnas hardcodeado vs headers reales → `nucleo_catalogo.columnas_indexadas(headers_reales)` en endpoints y worker. ✅
- **HIGH** — `corregir-numero` reportaba éxito con contacto no actualizado → devuelve `contacto_actualizado`/`aviso`. ✅
- **HIGH** — `catalogo_envios` colapsaba "hoja no existe" y error de API en `{envios:[]}` sin log → distingue `WorksheetNotFound` (benigno) de error real (log + 500). ✅
- **MEDIUM** — `envio_row` sin cota (podía pisar encabezados) → valida `2 ≤ envio_row ≤ nº filas`. ✅
- **MEDIUM** — `EN_PROCESO` lock no implementado → implementado en `procesar_cola`. ✅
- **LOW** — `ResultadoEnvio` usaba `assert` → `raise ValueError`; `update_cell` (USER_ENTERED) → `batch_update` RAW; `enmascarar_telefono` ahora se usa en logs; rama muerta `validar_numero` → devuelve `numero_valido`. ✅

**Diferido (documentado, no bloqueante):**
- **HIGH (code)** — `/api/catalogo/encolar` es superficie de abuso (envío WhatsApp a números arbitrarios) porque **toda la app carece de auth (FC2)**. Mitigación real = token `SL_DASHBOARD_TOKEN` (mejora M1) + validar `referencia` contra fila real de `LISTA DE CONTACTOS`. → **Plan 5 T5.3**, ANTES de correr el worker desatendido.
- **MEDIUM** — TOCTOU en encolar (mismo patrón que FC4): con 1 operador por cierre el riesgo es bajo; upsert atómico queda pendiente si hay 2+ operadores simultáneos.
- **NOTA owner** — idempotencia sin ventana temporal: un contacto que legítimamente vuelve a cerrar "Pedido" meses después dirá `ya_encolado` y no re-enviará. Confirmar si es el comportamiento deseado.
