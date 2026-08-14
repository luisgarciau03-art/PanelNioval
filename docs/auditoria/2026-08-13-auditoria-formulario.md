# Auditoría — Módulo Formulario de Llamadas

**Fecha:** 2026-08-13 · **Plan:** 2 (`plan2/evaluacion-formulario`) · **Alcance:** SOLO el formulario (`app.py`: backend `~2761-2987`, HTML/JS embebido `~2990-3404`). Análisis de solo lectura; ningún cambio de comportamiento (salvo sanitización de un secreto vivo, ver FC3).

**Método:** 4 revisores independientes en paralelo (code-reviewer, python-reviewer, security-reviewer, silent-failure-hunter — `catalogo-agentes`), consolidados y deduplicados. Matriz de flujo en `docs/analisis/2026-08-13-matriz-formulario.md`.

**Total: 20 hallazgos (4 CRITICAL · 6 HIGH · 6 MEDIUM · 4 LOW).**

## CRITICAL

| ID | Línea(s) | Hallazgo | Remediación / acción |
|---|---|---|---|
| FC1 | 2794-2812, 2815-2875, 3395-3398 | **La cola de llamadas no avanza.** `marcar_contacto_procesado` (escribe `Llamado` en RESPUESTA) es **código muerto** — su llamada se eliminó en commit `e84c1a0` (2026-05-05). `guardar_respuesta_formulario` no marca el contacto; `cargarSiguiente()` resetea `skip=0` (comentario falso "ya fue marcado", L3396) → `get_contacto_pendiente(0)` devuelve **el mismo contacto** y se acumulan filas duplicadas en `Respuestas de formulario 1`. El dashboard de pendientes nunca decrece. | ⚠️ **GATE OWNER:** la eliminación fue intencional (`e84c1a0`). ¿Cuál es el mecanismo de avance esperado (marcar RESPUESTA vs otro)? La corrección (reconectar `marcar_contacto_procesado(datos['row'], datos['col_respuesta'])` — el payload ya los envía) es de un plan futuro, no de éste (read-only). |
| FC2 | 2971, 2980, 4013 (y ~30 rutas) | **Cero autenticación** en toda la app. Cualquiera con la URL de Railway lee (`GET /api/formulario/siguiente`, iterando `skip`) y escribe (`POST /api/formulario/guardar`) las hojas de negocio. | Mejora M1: `before_request` con token `SL_DASHBOARD_TOKEN` (Plan 5). |
| FC3 | 3636 | **API key de Google Maps/Places hardcodeada** como fallback: `os.environ.get('GMAPS_API_KEY', 'AIza…')`. Secreto **vivo en `main`**, alimenta el importador que llena `LISTA DE CONTACTOS`. Coincide con el pendiente conocido "rotar Places key". | **SANITIZADO en este plan** (fallback eliminado, ver §Sanitización). Rotación = gate owner. |
| FC4 | 2823-2824, 2851-2867 | **Condición de carrera:** `ultima_fila = len(col_values(2))+1` es read-then-write sin lock. Dos operadores simultáneos calculan la misma fila y el segundo `batch_update` pisa al primero → **pérdida silenciosa** de una respuesta (ambos devuelven `{ok:true}`). | Usar `ws.append_row(...)` (atómico) o lock/lease. Plan futuro. |

## HIGH

| ID | Línea(s) | Hallazgo | Remediación |
|---|---|---|---|
| FH1 | 3291-3293, 3296-3298 | **XSS almacenado** en `renderContacto`: `info-grid.innerHTML = campos.map(...f.v...)` inyecta nombre de tienda/contacto (datos de Google Places, controlables por el dueño del negocio) sin escape. Vector secundario: `onclick="abrirVentana('${maps}')"` solo escapa comillas simples. Combinado con FC2 (sin auth), ejecuta en el navegador del operador. | `textContent` o `esc()` de `&<>"'`; construir links con `createElement`+`addEventListener`. |
| FH2 | 2788-2791, 2872-2875 | `except Exception → None/False` **oculta errores de Sheets** (cuota 429, auth, red) como estados de negocio: `get_contacto_pendiente` → `None` = "sin pendientes" (`{'fin':true}`); `guardar` → `False` = "reintenta". Indistinguible de fallo real. | Distinguir `gspread.exceptions.APIError` (5xx) de "sin filas"; `logging` estructurado. |
| FH3 | 2980-2987, 3365-3367 | Payload envía `row`/`col_respuesta` que el backend **descarta**. Causa raíz técnica de FC1 (los datos para marcar ya viajan en cada request). | Leerlos en `formulario_guardar` y pasar a `marcar_contacto_procesado`. |
| FH4 | 2771-2774, 2803-2806 | **Duplicación DRY** de la resolución de columna RESPUESTA en 2 funciones, con fallbacks inconsistentes (5 0-indexed vs 6 1-indexed). | Extraer helper único `_resolver_col_respuesta(headers)`. |
| FH5 | 2773, 2794, 2801 | **Números mágicos** de columna F: `5` (0-idx) y `6` (1-idx) sin constante; `col_respuesta=6` usado además como sentinel de "auto". | Constante `COL_RESPUESTA_FALLBACK`; firma `Optional[int]=None`. |
| FH6 | 2838-2848 | Mapa `col_j`: 8 `if/elif` con precedencia implícita, sin validación backend de exclusividad (hoy los valores son mutuamente excluyentes solo por construcción del frontend). Docstring referencia `llenar_formularios.py` (**archivo inexistente** en el repo). | Tabla de reglas explícita/`match`; validar exclusividad; corregir la referencia. |

## MEDIUM

| ID | Línea(s) | Hallazgo | Remediación |
|---|---|---|---|
| FM1 | 2827-2836, 2983 | Sin validación server-side del payload (`datos.get` sin tipo/tamaño; `request.json` puede ser `None`). Nota positiva: `batch_update` usa `RAW` → sin inyección de fórmulas. | `isinstance(datos,dict)`, whitelist de valores, límite de longitud, 400 explícito. |
| FM2 | 2987, 2941, 2967 | Fuga de `str(e)` al cliente (puede incluir IDs de hoja/rutas). Combinado con FC2 es cosechable. | Log interno + mensaje genérico al cliente. |
| FM3 | 2853-2864 | **Inconsistencia lectura/escritura:** la lectura resuelve RESPUESTA por header, pero la escritura usa letras de columna hardcodeadas (A,B,C-E,G-I,J,S,T). Reordenar una columna corrompe silenciosamente. | Documentar el contrato de columnas o resolver por header también al escribir. |
| FM4 | 2788-2791, 2810-2812, 2872-2875 | `except Exception` + `print`/`traceback.print_exc()` en vez de `logging` con niveles. | `logging.getLogger(__name__).exception(...)`; excepciones específicas. |
| FM5 | 2771-2775 | Fallback silencioso a col F (idx 5) si no existe header `RESPUESTA` → lee/escribe columna equivocada sin error visible. | Fallar explícito si el header no está. |
| FM6 | 2980-2987 | `try/except` del endpoint siempre responde `200` con `{ok:false}` → pierde semántica HTTP (debería 400/500). | Códigos HTTP correctos. |

## LOW

| ID | Línea(s) | Hallazgo | Remediación |
|---|---|---|---|
| FL1 | 3396 | Comentario `// el contacto anterior ya fue marcado` afirma un invariante falso (ver FC1). | Corregir comentario / arreglar el bug. |
| FL2 | 2762, 2816 | Docstrings referencian `llenar_formularios.py`, inexistente en el repo. | Actualizar o eliminar. |
| FL3 | 2777-2786 | Escaneo lineal O(n) por cada `skip` (`get_all_values` + contador manual). | Filtrar pendientes y `islice`. |
| FL4 | 2866 | `print` del nombre de negocio (`tienda`) a los logs de Railway (no teléfono). | Truncar/quitar de logs. |

## Sanitización aplicada en este plan

| Acción | Detalle | Verificación |
|---|---|---|
| FC3 — Places key | Eliminado el fallback hardcodeado en `app.py:3636`: `os.environ.get('GMAPS_API_KEY', 'AIza…')` → `os.environ.get('GMAPS_API_KEY')` con guard (`if not gmaps_api_key: return error`). | `grep 'AIzaSy'` en el árbol = 0 |

**Pendiente owner:** rotar la Google Places key (ya expuesta en el historial) tras la sanitización. Y decidir el mecanismo de avance de cola de FC1.
