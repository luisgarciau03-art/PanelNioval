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

# WORKER_TOKEN y PANEL_DASHBOARD_TOKEN NO se ponen con setx: iniciar-worker.bat
# los lee de tokens-panelnioval.txt en la raiz del proyecto, con el formato
# NOMBRE=valor. Copiarlos a mano fallo tres veces seguidas: son dos cadenas de
# 64 hex casi identicas y confundirlas da el mismo "no autorizado" en el panel
# que en el heartbeat. El archivo esta en .gitignore (tokens-*.txt).
#
# Para regenerarlo desde el servidor:
#   ssh root@155.138.200.66 'grep -E "^(PANEL_DASHBOARD_TOKEN|WORKER_TOKEN)=" /srv/panel/secretos/.env' > tokens-panelnioval.txt
#
# PANEL_URL ya no hace falta: el .bat lo fija a https://panelnioval.duckdns.org.

# 3. Iniciar sesión de WhatsApp Web en el perfil del worker (SOLO la primera vez o si expira):
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="C:\Users\PC 1\ChromeSeleniumProfile" --profile-directory=Default https://web.whatsapp.com
#   → escanea el QR, espera a que carguen TODOS tus chats, y CIERRA esa ventana.

# 4. OPERACION NORMAL: doble clic en iniciar-worker.bat y dejar la ventana abierta.
#    Lee los tokens de tokens-panelnioval.txt, fija PANEL_URL, limpia locks y
#    Chrome huerfanos, abre el panel autenticado y procesa la cola cada 15s.
#    Cerrar con Ctrl+C, NO con la X: con la X Chrome queda huerfano.

# 5. Probar a mano (una corrida suelta, sin el .bat):
python worker_catalogo_run.py

# 5b. MODO CONTINUO (recomendado para envío casi inmediato): abre WhatsApp una vez
#     y procesa la cola cada 15s. Déjalo corriendo en una ventana.
python worker_catalogo_run.py --loop
#     (intervalo configurable con  setx WORKER_LOOP_SECS 15  ; salir con Ctrl+C)
```

## Tarea Programada: instalada pero DESACTIVADA

**Decisión del owner (2026-08-24): la operación es manual, con `iniciar-worker.bat`.**
La tarea `NIOVAL_WorkerCatalogo` sigue registrada pero desactivada; su definición está
respaldada en `respaldos/2026-08-22-tarea-worker/`.

```powershell
Enable-ScheduledTask  -TaskName NIOVAL_WorkerCatalogo    # reactivar
Disable-ScheduledTask -TaskName NIOVAL_WorkerCatalogo    # desactivar
Unregister-ScheduledTask -TaskName NIOVAL_WorkerCatalogo -Confirm:$false   # quitar
```

Por qué se desactivó: corría cada 15 minutos lanzando `worker_catalogo_run.py`
**directamente**, sin pasar por el `.bat`, así que solo heredaba las variables
persistidas con `setx`. Sin `WORKER_TOKEN` ni `PANEL_URL` el heartbeat fallaba en
silencio y el panel mostraba el worker como muerto — pero el gate de envío sí se
cumplía, o sea que **enviaba catálogos sin que nadie se enterara**. Además dejaba locks
y procesos de Chrome huérfanos que bloqueaban las corridas manuales.

`instalar-worker.ps1` ya está corregido: la tarea ejecutaría el `.bat` (mismo camino que
en manual) y se niega a instalarse si falta algo. No la reactives sin decidir antes que
quieres envíos automáticos.

**Nunca las dos a la vez:** el perfil de Chrome no admite dos instancias.

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
- **Corrida vía `iniciar-worker.bat`**: el `.bat` **solicita la contraseña** (`set /p WA_ENVIO_PASSWORD=...`) si no está ya en el entorno, antes de lanzar `worker_catalogo_run.py`, que la valida antes de abrir WhatsApp. `worker_catalogo_run.py` en sí nunca prompta: solo lee la variable de entorno.
- **Tarea Programada** (no interactiva): además de `WA_ENVIO_PASSWORD`, se exige `WA_ENVIO_ARMADO=1` para que envíe. Sin ese flag, la corrida no envía (queda "desarmada"). Así puedes tener la tarea instalada pero pausada hasta que la armes.

## Ver estados

- **Envíos:** `GET /api/catalogo/envios?estado=PENDIENTE|ENVIADO|NUMERO_INVALIDO|FALLO`.
- **Worker vivo/muerto:** `GET /api/catalogo/worker-estado` (`vivo=true` si hubo heartbeat en los últimos 15 min).
- **Reintentar** un `FALLO`/`NUMERO_INVALIDO`: `POST /api/catalogo/reintentar {envio_row}` o el modal del formulario.

## Smoke test post-deploy

```bash
python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>
```
Debe imprimir `Todo OK ✅`. Railway auto-deploya `main`: correr el smoke tras cada merge.

## Verificar la hoja de contactos (antes de capturar correos)

```bash
python tools/inspeccionar_contactos.py   # confirma que la columna T está libre
```

## Qué hacer si algo falla

| Síntoma | Causa probable | Acción |
|---|---|---|
| `worker-estado` = `vivo:false` | `WORKER_TOKEN` ausente o incorrecto (heartbeat devuelve 401) / PC apagada / tarea detenida / QR expirado | Confirmar que el `WORKER_TOKEN` del worker coincide con el del servidor; si coincide, encender PC; `python worker_catalogo_run.py` y re-escanear QR |
| Muchos `FALLO` | WhatsApp Web cambió selectores o sesión caída | Re-escanear QR; revisar `envio_catalogo.py` (selectores `data-icon`) |
| Muchos `NUMERO_INVALIDO` | Teléfonos mal capturados | Corregir número desde el modal |
| Panel 401 en todo | `PANEL_DASHBOARD_TOKEN` activo | Acceder con `?token=<valor>` una vez (queda en la sesión) |
| Envíos duplicados | Dos corridas del worker solapadas | El lock lo previene; no correr 2 instancias manuales a la vez |

## Cuando el check de CI sale en rojo (desde 2026-08-28)

`.github/workflows/tests.yml` corre en cada PR contra `main` y en cada push a `main`.
Son dos jobs independientes y **fallan por motivos distintos**.

### Job "Suite de pytest"

Es el que bloquea. Si sale rojo, hay tests en rojo.

1. Abre el resumen del PR: la linea con `N passed` / `N failed` esta ahi, no hace falta
   entrar al log. Si en vez del numero dice *"la suite no llego a imprimir resumen"*, es
   que pytest reventó antes de terminar — normalmente un error de coleccion, y entonces
   si hay que abrir el paso "Correr la suite".
2. Reproduce en local con **el mismo comando**: `python -m pytest tests/` — **sin `-q`**.
   `pytest.ini` ya trae `addopts = -q`; el segundo lo vuelve `-qq` y **suprime la linea
   del resumen**: verias los puntos y `exit 0`, nunca el numero.
3. El baseline **es por rama**. En `main` son 345 passed; la rama del Plan 2 da 357
   passed y 1 skipped porque trae 43 tests suyos. Compara contra la rama base del PR,
   no contra un numero absoluto.
4. Si falla **solo en CI y no en local**, mira primero estas dos: el runner es Linux y la
   PC del owner es Windows (separadores de ruta, mayusculas en nombres de archivo), y el
   runner no tiene **ninguna** variable de entorno de Google ni de Telegram. Si un test
   necesita un secreto, el test esta mal aislado: se arregla el test, **no** se le dan
   secretos al workflow.

### Job "Barrido de secretos sobre el diff"

**Avisa, no bloquea** en esta primera version: no puede poner el check en rojo por
encontrar algo. Si sale rojo es porque el script **se rompio**, y eso si hay que mirarlo
— un barrido que se traga su error devuelve cero hallazgos y parece un exito.

Si el resumen lista hallazgos:

| Lo que ves | Que significa | Que hacer |
|---|---|---|
| `[telegram]`, `[google_api_key]`, `[meta]`, `[openai]`, `[clave_privada]`, `[secreto_del_panel]` | Algo con forma de credencial entro en el diff | **Rotarlo en el proveedor.** Quitarlo del codigo NO lo rota: sigue vivo en el historial de git y sigue siendo valido |
| `[telefono_mx]` | Un telefono de 10 digitos sin enmascarar | Enmascarar a `+52...XXXX`. Es la regla del proyecto para logs y commits |
| `[hex_largo]` | Hexadecimal de 32-64 caracteres que no es un SHA de git | Comprobar si es una clave. Los SHA de 40 y 64 se excluyen a proposito |
| `Barrido sin material: 0 lineas anadidas` | **No es un diff limpio.** El SHA base salio mal y no se examino nada | Revisar el paso "Barrer las lineas anadidas" |

Si es un falso positivo —una fixture de test, un ejemplo en documentacion— se exceptua la
linea con un comentario `barrido-ok: <motivo>`. **El motivo es obligatorio**: sin el, la
marca no silencia nada. Se eligio una marca en linea y no excluir `tests/` entera porque
una carpeta excluida esconde para siempre lo que caiga dentro, mientras que cada uso de la
marca aparece en el diff y un revisor lo ve.

⚠️ **Gate del owner pendiente:** sin la proteccion de rama en `main` (Settings → Branches →
Require status checks), el check **informa pero no impide el merge**. Requiere permisos de
administrador del repositorio.

## Endurecimiento del panel (desde 2026-09-04, Plan 5)

### Si el panel responde 429

Significa que se pasó el límite de peticiones, **no** que algo esté roto. El cuerpo llega en
JSON con el motivo. Los límites, por si hay que ajustarlos (`app.py`, arriba del todo):

| Ámbito | Límite | Por qué ese |
|---|---|---|
| Global (todas las rutas) | 600/hora y 60/min | Holgado para un panel de pocas personas |
| `/api/importador/iniciar` | **6/hora** | Es la única ruta que gasta dinero (Google Places) |
| `/api/catalogo/heartbeat` | 600/min | Lo llama el worker cada pocos segundos: un límite corto **lo tumba** |
| `/api/importador/estado` | 240/min | El panel lo sondea cada 3 s mientras hay corrida |
| `/salud` | 600/min | Docker lo sondea cada 30 s; un 429 marcaría el contenedor enfermo |

El contador vive **en memoria del proceso** y se reinicia al reiniciar el panel. Es exacto
porque gunicorn corre `--workers 1`; **si algún día se sube a 2 workers, el límite deja de
serlo en silencio**, igual que ya pasa con el estado del importador.

Si el límite estorba en el uso normal, se sube el número en `app.py` y se reinicia. No hace
falta tocar nada más.

### Cómo leer el healthcheck

```
docker ps                      # la columna STATUS dice (healthy) o (unhealthy)
docker inspect --format '{{json .State.Health}}' panel | python -m json.tool
```

⚠️ **`unhealthy` no reinicia nada por sí solo.** `restart: unless-stopped` reacciona a que el
proceso *muera*, no a que el healthcheck falle, y Caddy hace `reverse_proxy panel:8000` sin
`health_uri`, así que sigue mandando tráfico a un contenedor enfermo. Hoy el healthcheck da
**visibilidad**, no reparación. Para cerrarlo hay dos caminos, y es decisión del owner:

- `reverse_proxy panel:8000 { health_uri /salud health_interval 10s }` en el fragmento de
  Caddy, para que deje de enrutar al contenedor enfermo.
- Un sidecar `autoheal` en `docker-compose.yml`, que sí lo reinicia.

Comprobar la ruta a mano, desde el servidor:

```
curl -s https://panelnioval.duckdns.org/salud     # {"ok":true}
```

No pide token a propósito: Docker no lo tiene. Devuelve `{'ok': true}` y nada más, porque es
la única ruta pública del panel.

### Qué pasa ahora al reiniciar el contenedor a media corrida

Antes, el hilo del importador moría donde estuviera. Ahora recibe `SIGTERM`, termina lo que
tiene entre manos y deja la corrida marcada como **`interrumpido`** (no `cancelado`, que es
lo que significa que el operador pulsó Detener). Lo ya escrito en la hoja sigue ahí y volver
a correr la ciudad continúa sin repetir lo pagado.

El margen para cerrar ordenadamente es `--graceful-timeout 120`. Si se baja, la parada
vuelve a no llegar a tiempo y el hilo muere como antes.

### Si aparece un apóstrofo al principio de una celda

Es el escape de fórmulas y **es correcto**: marca "esto es texto" y Sheets no lo muestra ni
lo cuenta como parte del valor. Solo se aplica a lo que empieza por `=`, `+`, `-` o `@`, que
Sheets interpretaría como fórmula. Si aparece en una celda que **no** empieza por uno de
esos, eso sí es un fallo: reportarlo.

### ⚠️ Si el panel arranca sin pedir contraseña

Buscar en los logs de arranque:

```
*** PANEL_AUTH_DESACTIVADA=1: panel SIN autenticacion NI rate limiting. ***
```

Esa variable apaga **las dos cosas a la vez**. Es correcta en desarrollo y en los tests; en
un despliegue real significa que el panel está **abierto a internet**. Quitarla del entorno
y reiniciar.

---

## Importador de prospectos (desde 2026-08-27)

### Qué significa cada número

El panel muestra cuatro, y **no son intercambiables**. El grande es el que
responde a la pregunta "¿cuántos contactos gané?".

| Recuadro | Significa |
|---|---|
| **Nuevos en la hoja** | Filas que de verdad se escribieron en `LISTA DE CONTACTOS`. **Es el número grande.** |
| Aprobados por filtros | Negocios distintos que pasaron los filtros de Google (≥5 reseñas, ≥3.5 ⭐, con teléfono) |
| Ya estaban | Aprobados que ya figuraban en la hoja de antes |
| Descartados | Rechazados por reseñas, calificación o falta de teléfono |

Se cumple siempre **Nuevos + Ya estaban = Aprobados**. `Descartados` va aparte:
se descartan *antes* de aprobar, no son una parte de los aprobados.

> Antes del 2026-08-27 el panel mostraba un solo número, rotulado de forma que se
> leía como "guardados". No lo era: contaba los aprobados. De ahí el "dice 20 y
> aparecen 10".

### Cómo detener una corrida

Botón **⏹ Detener** mientras la búsqueda corre. La cancelación se comprueba
**entre categorías**, nunca a mitad de una escritura, así que:

- lo que ya se guardó en la hoja **se queda** y es válido;
- volver a correr la misma ciudad **no lo duplica** (el dedup lo impide);
- la corrida queda como `cancelado`, **no** como completada — ni en el panel ni
  en el aviso de Telegram. Si el aviso dijera "Completado", nadie volvería a
  correr las categorías que faltaron.

### Si el panel se reinicia a media corrida

El trabajo se pierde (el hilo es `daemon=True`), pero **lo escrito hasta ese
momento sigue en la hoja**. Al volver a `/importador` el panel dice *"La corrida
se interrumpió"* con los contadores que había alcanzado, en vez de aparecer en
blanco como si nunca hubiera pasado nada.

Ese aviso sale de un registro en `IMPORT_ESTADO_FILE` (por defecto, el temp del
sistema). El registro **no lleva datos personales**: solo estado, contadores y
PID. Y **nunca bloquea** una corrida nueva: si el proceso que lo escribió ya no
existe, se marca como interrumpido y se sigue adelante.

### Errores que ahora se ven (y antes no)

| Síntoma | Qué pasó |
|---|---|
| `error` con "fallo al escribir en Google Sheets" | Cuota, permisos o red al escribir. **Nada se guardó de esa categoría.** Reintentar |
| `error` con "no se pudo consultar Google Places" | Clave inválida, cuota agotada o sin red. Revisar `GMAPS_API_KEY` |
| Log con "⚠ N se perdieron por errores de Places" | Algunos negocios fallaron al pedir su detalle. El resto sí entró |
| Log con "N ya vistos en otra categoría" | Solapamiento entre las dos búsquedas. Es normal e informativo |

Antes, los dos primeros terminaban en ✅ con la hoja intacta.

### Caché de detalles de Places (desde 2026-08-28)

El importador guarda los detalles que pide a Google (teléfono, sitio web, horario)
para no volver a pagarlos. **A quien más ahorra es al negocio rechazado**: uno que
pasa reseñas y calificación pero no tiene teléfono se descarta y nunca llega a la
hoja, así que sin caché se re-pagaba en cada corrida de esa ciudad, para siempre.

Medido: segunda corrida de la misma ciudad, **80 → 0** llamadas de Place Details.

| Dato | Valor |
|---|---|
| Archivo | `PLACES_CACHE_FILE`, por defecto el temp del sistema |
| Vigencia | 30 días |
| Contenido | `place_id` → teléfono, sitio web, horario, y marca de tiempo |

**Lleva teléfonos de negocios, o sea datos personales.** Está en `.gitignore` y
`.dockerignore`. No copiarlo fuera del servidor ni adjuntarlo a un reporte.

**Por defecto NO sobrevive a un redespliegue** (vive en el temp del contenedor).
Funciona igual — se pierde el ahorro, no el servicio. Para que persista, montarle
un volumen en `/srv/panel/docker-compose.yml`:

```yaml
    environment:
      - PLACES_CACHE_FILE=/datos/places_detalles.json
    volumes:
      - ./secretos/credentials.json:/app/credentials.json:ro
      - panel-datos:/datos          # <-- añadir

volumes:
  panel-datos:                      # <-- añadir al final del archivo
```

Es opcional y es decisión del owner: sin el volumen el panel funciona igual.

**Si hace falta borrarla** (por ejemplo, si se sospecha que tiene teléfonos
viejos), basta con eliminar el archivo: se reconstruye sola en la siguiente
corrida, pagando los detalles una vez.

### Medidor de gasto y tope de corrida

Bajo la barra de progreso, y en el aviso de Telegram, aparece qué le costó la
corrida a la cuenta de Google:

```
Llamadas a Google: 13 búsquedas + 24 detalles · 56 evitadas
```

Las **evitadas** son las que el prefiltro y la caché se ahorraron. Ese número es
el ahorro, medido, de esta corrida.

#### Variables de entorno

Ninguna tiene valor por defecto, **a propósito**. Google cambia sus tarifas, y un
número escrito en el código empieza siendo correcto y acaba mintiendo sin que
nadie lo toque.

| Variable | Para qué | Si no se define |
|---|---|---|
| `PLACES_COSTO_TEXT_SEARCH` | Costo de una búsqueda de texto | No se muestra importe |
| `PLACES_COSTO_DETAILS` | Costo de un Place Details | No se muestra importe |
| `PLACES_PRESUPUESTO_CORRIDA` | Tope en dinero por corrida | Sin tope de dinero |
| `PLACES_MAX_LLAMADAS_CORRIDA` | Tope en número de llamadas | Sin tope de llamadas |
| `PLACES_CACHE_FILE` | Dónde vive la caché de detalles | Temp del sistema |

**Sin tarifas configuradas no se publica ningún importe.** Un `0.00` se leería
como *"esta corrida salió gratis"*, que es una afirmación falsa; no saber el
precio no es lo mismo que saber que fue cero.

**El tope de llamadas funciona sin tarifas**, y es el único utilizable mientras no
haya acceso a la consola de facturación. Es el recomendado para empezar.

Las variables se leen **al arrancar el proceso**: cambiarlas exige reiniciar el
contenedor.

#### Qué pasa al tocar el tope

La corrida se detiene y queda en estado **`presupuesto_agotado`**, con su propio
mensaje en la pantalla y en Telegram. **No es un error**: es un límite que se
respetó, y lo que ya se guardó en la hoja es válido.

Volver a correr la misma ciudad **continúa desde donde quedó** sin repetir lo
pagado: el prefiltro salta lo que ya está en la hoja y la caché sirve los
detalles ya consultados.

### ⚠️ Pendiente del owner

Estas cinco variables **no están en `.env.example`**: el entorno de trabajo tiene
bloqueada la escritura de archivos `.env*`, así que hay que añadirlas a mano
(solo los nombres, sin valores).

---

### ¿Por qué 30 días y no 90?

Lo que se cachea incluye el teléfono que el operador va a marcar. Un negocio que
añade teléfono a su ficha de Google es un prospecto nuevo, y no conviene tardar un
trimestre en verlo. Con 30 días, quien recorre una ciudad cada semana o cada mes
ya no paga nada por los rechazados.

---

### Por qué un solo worker

`--workers 1 --threads 4`. El estado del importador y la caché son globales de
módulo; con dos procesos son dos memorias distintas y la mitad de los sondeos
respondía `idle` con el trabajo corriendo. Razonamiento completo y alternativas
descartadas: `docs/adr/2026-08-27-estado-compartido-importador.md`.

**No subir `--workers` sin leer ese ADR.** Hay tres tests que fallan si se hace.

---

### Revertir el recorte de búsquedas sin desplegar código

El importador deja de consultar variaciones y páginas que no están aportando
negocios nuevos. Eso ahorra 5 búsquedas de texto por corrida y, medido contra
respuestas grabadas, **no pierde ni un prospecto**.

Si alguna vez una corrida real diera menos prospectos de los esperados, el
recorte se desactiva **cambiando dos variables del módulo**, sin tocar la lógica
y sin desplegar una versión nueva:

```python
MAX_VARIACIONES_SIN_APORTE = 99     # deja de cortar variaciones
CORTAR_PAGINAS_SIN_APORTE  = False  # deja de cortar paginas
```

Con eso el importador vuelve a consultar las 3 variaciones y todas las páginas,
como antes del Plan 2. El resto de optimizaciones —los `fields` explícitos, la
caché y la deduplicación contra la hoja— siguen activas y **no afectan a qué
negocios se encuentran**, solo a cuánto se paga por encontrarlos.

### Ojo al medir el ahorro: la caché contamina la medición

`tools/medir_llamadas_places.py` cuenta las llamadas que hace una corrida. Si se
usa para comparar antes y después, **la caché tiene que estar aislada**.

La caché vive por defecto en el temp del sistema, así que **sobrevive entre
ejecuciones del script**. Una medición de esta tanda arrastró 108 entradas de
corridas anteriores y reportó 0 Details en escenarios donde el código sí habría
pagado — con un «pagados y tirados: **-18**» que delató el problema, porque un
negativo ahí es imposible.

El script ya estrena una caché desechable por escenario. Si se mide a mano,
apuntar `PLACES_CACHE_FILE` a un archivo nuevo antes de cada corrida:

```bash
PLACES_CACHE_FILE=$(mktemp -d)/c.json python tools/medir_llamadas_places.py
```

Un ahorro que en realidad es una caché heredada se lee igual que un ahorro real,
y no lo es.


## Gates del owner pendientes (seguridad)

- **Rotar** `TELEGRAM_TOKEN` (bot `8404009072`, expuesto en ~14 copias del historial) y la **Google Places key**; cargarlas en `/srv/panel/secretos/.env` y `/srv/bruce/secretos/.env` en el VPS (ya no en Railway).
- ~~Eliminar el servicio de Railway~~ — **HECHO** (2026-08-19). `https://web-production-1d453.up.railway.app/` devuelve 404 en la raíz y en `/api/prospectos/stats`. Antes servía el panel abierto sin token: esa exposición está cerrada.
- **Corrida real de WhatsApp** (T5.5): 1 llamada de prueba end-to-end con un número propio.

## Operación en el VPS (desde 2026-08-17)

El panel corre en `155.138.200.66` (Vultr), servido en
`https://panelnioval.duckdns.org` por Caddy con TLS automático. Comparte
servidor con Bruce.

| Acción | Comando |
|---|---|
| Ver logs | `ssh root@155.138.200.66 'docker logs -f panel'` |
| Reiniciar | `ssh root@155.138.200.66 'docker restart panel'` |
| Desplegar cambios | `ssh root@155.138.200.66 'cd /srv/panel/app && git pull && cd /srv/panel && docker compose up -d --build'` |
| Smoke test | `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <token>` |
| Consumo | `ssh root@155.138.200.66 'docker stats --no-stream'` |

Los secretos viven en `/srv/panel/secretos/.env` (chmod 600). El panel **no
arranca** sin `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY`: si el contenedor
reinicia en bucle, revisar ese archivo primero con `docker logs panel`.

Tres variables adicionales son **de función, no de arranque**: sin ellas el
panel levanta y sirve normalmente, pero la función asociada falla en el
momento de usarse:

| Variable | Sin ella | Ruta afectada |
|---|---|---|
| `IMGBB_API_KEY` | 500 al subir el comprobante | `/api/ventas/upload-pago` |
| `GMAPS_API_KEY` | `{"ok": false}` sin arrancar la búsqueda | `/api/importador/iniciar` |
| `PAGO_FOLDER_ID` | falla `get_pago_folder_id()` (`app.py:158`) si algo la invoca; hoy ninguna ruta activa la llama (el comprobante de pago usa `IMGBB_API_KEY`, no Drive) | ninguna ruta activa hoy |

⚠️ Bruce corre en el mismo servidor y lee las mismas hojas. Antes de escribir
filas de prueba en `seguimiento` o `PROSPECTOS BRUCE`, pausar su scheduler
(`WA_SCHEDULER=0` en `/srv/bruce/secretos/.env` + `docker compose up -d`) o un
job le enviará un WhatsApp real al número de la fila.
