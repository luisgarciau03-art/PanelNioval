# Testeo del panel en el VPS — capas 1, 2 y 3

**Fecha:** 2026-08-18 · **Base:** `https://panelnioval.duckdns.org` · **Servidor:** `155.138.200.66`

Corresponde a la Task 11 del plan `2026-08-17-despliegue-vultr.md`. Ningún valor de token
aparece en este documento: las pruebas con token se ejecutaron **desde el servidor**, donde
el valor ya reside, para que no viajara a la máquina del operador ni a la transcripción.

> El plan nombraba este archivo `2026-08-17-testeo-vps.md`. Se usa la fecha real de
> ejecución, 2026-08-18.

---

## Capa 1 — suite unitaria

```
python -m pytest tests/ -q
165 passed   (exit 0)
```

Ejecutada sobre `main` ya con los merges de los PR #12-#15. El plan esperaba 164: número
stale de antes del último commit de tests. El baseline oficial es **165**.

## Capa 2 — gates desde internet, sin token

| Ruta | Código |
|---|---|
| `/` | 401 |
| `/formulario` | 401 |
| `/importador` | 401 |
| `/api/prospectos/stats` | 401 |
| `/api/debug` | 401 |
| `/api/debug/respuestas` | 401 |
| `/api/catalogo/envios` | 401 |
| `/api/catalogo/heartbeat` (POST) | 401 |

**8 de 8 en 401.** Ningún 200. El heartbeat cierra por su propia variable, `WORKER_TOKEN`.

## Capa 2 bis — el contenedor no arranca sin secretos

Verificado en un contenedor desechable, sin tocar el panel en marcha:

```
docker run --rm --entrypoint python panel-panel:latest -c "import app"

Traceback (most recent call last):
  File "/app/app.py", line 39, in <module>
    raise RuntimeError(
RuntimeError: PANEL_DASHBOARD_TOKEN no está definida. El panel expone datos de
clientes: no arranca sin token.
```

Una prueba previa quitando la variable del `.env` real dejó el contenedor en
`Restarting (1)` y se restauró solo. Se repitió con el contenedor desechable porque
`Restarting (1)` prueba que **no arrancó**, pero no prueba **por qué**: sin el traceback,
el veredicto habría sido correcto por casualidad.

## Capa 3 — rutas GET con token

23 rutas, **200 en todas**:

`/` · `/formulario` · `/importador` · `/api/prospectos/ciudades` ·
`/api/prospectos/clientes-frecuentes` · `/api/prospectos/contactos` ·
`/api/prospectos/contactos-pendientes` · `/api/prospectos/frecuentes` ·
`/api/prospectos/mensajes` · `/api/prospectos/respuestas` · `/api/prospectos/stats` ·
`/api/prospectos/ventas` · `/api/prospectos/ventas-dashboard` · `/api/seguimiento` ·
`/api/ventas/stats` · `/api/bruce/prospectos` · `/api/catalogo/envios` ·
`/api/catalogo/worker-estado` · `/api/formulario/siguiente` · `/api/importador/estado` ·
`/api/debug` · `/api/debug/respuestas` · `/api/test/ventas`

Queda fuera `/api/ventas/buscar-imagen`, que exige un identificador de venta real y se
ejercita desde el dashboard en la Capa 4.

`/api/prospectos/stats` devolvió datos reales (7,146 contactos, 6,148 respuestas), lo que
confirma que la conexión a Sheets funciona desde el contenedor y valida la corrección de
`GOOGLE_CREDENTIALS_FILE`.

## TLS

```
subject = CN = panelnioval.duckdns.org
issuer  = C = US, O = Let's Encrypt, CN = YE1
notAfter = Nov 16 19:56:43 2026 GMT
```

Emitido por desafío `tls-alpn-01` tras recargar Caddy en caliente con `caddy reload`
(no `restart`, para no cortar las conexiones de Bruce). `ssl_verify_result: 0` desde fuera.

## No regresión de Bruce

| Comprobación | Resultado |
|---|---|
| `https://bruce.nioval.duckdns.org/` | 200 |
| `https://nioval.duckdns.org/` | responde su bloque de prueba |
| Consumo de `bruce` | 63 MB, sin cambio respecto al pre-despliegue |
| Caddyfile | respaldado en `/srv/proxy/respaldos/` antes de tocarlo; `caddy validate` en verde antes de recargar |

## Railway

Apagado por el owner. `https://web-production-1d453.up.railway.app/` devuelve **404**
en la raíz y en `/api/prospectos/stats`. Antes del apagado servía 200 sin token: la
exposición está cerrada.

---

## Capa 4 — escrituras sobre producción

Ejecutada el 2026-08-18 a partir de las 20:05 hora de México, **fuera de la ventana
09:00-20:00** y con el scheduler de Bruce pausado.

### Protocolo previo

| Paso | Evidencia |
|---|---|
| Respaldo de las 5 hojas | 5 XLSX válidos, verificados como ZIP legible (20 MB sin comprimir el mayor) |
| Huellas de encabezados | `huellas.json`, **65 hojas** |
| `.env` de Bruce respaldado | hash SHA-256 idéntico antes de modificar |
| Flags previos de Bruce | `WA_SCHEDULER=1` `WA_GEO_AUTO=1` `WA_BUSCADOR_AUTO=1` `WA_CAMPANA_AUTO=0` |
| Scheduler pausado | `[STARTUP] APScheduler DESACTIVADO (WA_SCHEDULER=0) — modo réplica solo-webhook` |

El respaldador tuvo que corregirse dos veces antes de servir, y ambas fallas son
instructivas:

1. **Importar `app.py` reventaba** por la propia guarda fail-closed que instalamos. Se
   resolvió con el escape hatch documentado, `PANEL_AUTH_DESACTIVADA=1`, legítimo aquí
   porque es un CLI de solo lectura que no abre puerto ni sirve rutas.
2. **429 de cuota de Sheets**: el huelleo pedía los encabezados hoja por hoja, 65
   peticiones contra un límite de 60 por minuto. Se pasó a una sola llamada
   `values_batch_get` por spreadsheet — de 65 peticiones a 5.

En ambos casos el script terminó con **código de salida 0** porque la tubería `| tail`
enmascaraba el fallo real. Se detectó comprobando los archivos producidos, no el código
de salida. Vale la pena recordarlo: `cmd | tail` devuelve el estado de `tail`.

### Rutas ejercitadas

| Ruta | Código | Resultado |
|---|---|---|
| `/api/bruce/agregar` | 200 | `append_row` en `PROSPECTOS BRUCE` fila 73 |
| `/api/bruce/actualizar` | 200 | modificó **nuestra** fila 73, no una real |
| `/api/refresh` (sin cuerpo) | 400 | error del operador, no del panel: ver nota |
| `/api/refresh` (con cuerpo) | 200 | correcto |
| `/api/catalogo/heartbeat` sin `WORKER_TOKEN` | 401 | gate cerrado |
| `/api/catalogo/heartbeat` con `WORKER_TOKEN` | 200 | correcto |
| `/api/catalogo/encolar` sin `referencia` | 400 | validación corta antes de escribir |
| `/api/importador/iniciar` | 200 | `{"ok":false,"error":"GMAPS_API_KEY no configurada"}` |

**Nota sobre `/api/refresh` (`app.py:353`):** usa `request.json.get('key','all')` sin el
`or {}` que sí emplean las demás rutas POST. Con un cuerpo vacío Flask responde 400 en vez
de aplicar el valor por defecto. Es una inconsistencia menor, no un fallo de la migración;
queda anotada por si se normaliza.

**`/api/importador/iniciar` falla por diseño:** `GMAPS_API_KEY` no venía en el archivo de
entorno del owner. Falla de forma limpia y con mensaje explícito en vez de romperse, que es
el comportamiento correcto. La ruta queda sin probar de verdad hasta que se cargue la clave.

### Limpieza y verificación estructural

Se escribió **una sola fila** de prueba, marcada `PRUEBA-2026-08-18` y con el teléfono del
owner (`+52...4185`). Búsqueda del marcador en las 4 hojas del libro compartido con Bruce:
solo apareció en `PROSPECTOS BRUCE` fila 73. `Seguimiento`, `BD` y `Dashboard` quedaron
intactas.

Comparación de huellas antes contra después:

```
hojas antes: 65 | despues: 65
huellas SHA-256 distintas:   0
conteo de columnas distinto: 0
conteo de filas distinto:    1  -> bruce-seguimiento/PROSPECTOS BRUCE: 1000 -> 999
```

**Ninguna columna se movió**, que es lo que protegía a los proyectos externos sincronizados
con estas hojas. La única diferencia fue el total de filas de la cuadrícula: `append_row`
escribió en la fila 73 que ya existía vacía, sin aumentar el total, pero `delete_rows` sí
eliminó una fila del grid. Se restauró con `add_rows(1)`, dejando la hoja en 1000 filas,
0 marcadores y encabezados idénticos (`Fecha, Nombre, Teléfono, Tipo de Interés, Casilla,
NOTA`).

### Restauración de Bruce

Los cuatro flags volvieron a sus valores previos y el log confirma
`[STARTUP] APScheduler iniciado — follow-ups automáticos activos`. Bruce estuvo en modo
solo-webhook unos 12 minutos, con dos reinicios cortos.

---

## Pendiente

- **Capas 5, 6 y 7**: worker Selenium extremo a extremo, no-regresión de Bruce bajo carga,
  y resiliencia.
- **`GMAPS_API_KEY` ausente** en el VPS: `/api/importador/iniciar` devolverá `{"ok": false}`
  hasta que se cargue. No bloquea el arranque. No venía en el archivo de entorno del owner.
- **`TELEGRAM_TOKEN` sin rotar**: sin alertas de Telegram. No bloquea el arranque.
