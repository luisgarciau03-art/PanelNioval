# Diseño — Alta de PanelNioval en Vultr

**Fecha:** 2026-08-17
**Estado:** aprobado en diseño, pendiente de plan de implementación
**Rama:** `feat/despliegue-vultr`

---

## 1. Contexto verificado

Todo lo de esta sección está comprobado contra el servidor y el DNS reales, no supuesto.

### 1.1 El servidor Vultr ya existe

| Hecho | Valor |
|---|---|
| Host | `nioval`, VM Ubuntu en Vultr |
| IP | `155.138.200.66` |
| RAM | 1.9 GB total · ~1.3 GB disponible · 5.4 GB swap |
| Disco | 52 GB · 37 GB libres |
| Contenedores | `bruce` (:8001, interno) · `caddy:2-alpine` (:80/:443) |
| Consumo actual | `bruce` 64 MB · `caddy` 13 MB |
| Acceso | SSH por clave `id_ed25519`, host en `known_hosts` |

Patrón de despliegue existente, que este diseño replica:

```
/srv/proxy/{Caddyfile,docker-compose.yml}   ← red Docker externa "web", TLS automático
/srv/bruce/{app/,secretos/,docker-compose.yml}
```

`/srv/bruce/app` es un clon de `git@github.com:luisgarciau03-art/BruceWhatsapp.git`.
El único servicio con puertos publicados es Caddy.

### 1.2 Estado del DNS

| Host | Resuelve a | Responde |
|---|---|---|
| `bruce.nioval.duckdns.org` | `155.138.200.66` (Vultr) | sí |
| `panelnioval.duckdns.org` | `189.203.107.137` (IP residencial MX) | **no**, timeout en :80 y :443 |

El registro de `panelnioval` apunta a un destino muerto.

### 1.3 Hallazgo de seguridad: el panel de Railway está vivo y abierto

`https://web-production-1d453.up.railway.app/` (URL en texto plano en `iniciar-worker.bat:14`)
devuelve **HTTP 200 con el dashboard completo, 84 KB de HTML, sin exigir token**.

`PANEL_DASHBOARD_TOKEN` no está definido en Railway. Cualquiera con esa URL lee y escribe
las hojas de ventas, contactos y seguimiento **ahora mismo**. Es una exposición activa,
independiente de esta migración.

*Alcance de la comprobación: una petición GET a `/`. No se barrieron las demás rutas; no
hace falta, el gate es global (`@app.before_request`) y está en `off`.*

### 1.4 Los dos gates son fail-open

- [`app.py:47-62`](../../../app.py) — `if not token: return  # auth desactivada`. Sin la
  variable, las 39 rutas quedan abiertas.
- [`app.py:3491-3498`](../../../app.py) — `/api/catalogo/heartbeat` está exento del gate del
  panel, y su `WORKER_TOKEN` también es condicional (`if esperado:`). Sin la variable es un
  endpoint de escritura abierto.
- [`app.py:34-36`](../../../app.py) — `SECRET_KEY` ausente solo imprime una advertencia; con
  2 workers de gunicorn eso rompe las cookies de sesión de forma intermitente.

Esto es exactamente el patrón que las reglas globales prohíben: *ningún gate de
autenticación con valor por defecto silencioso*.

### 1.5 Superficie del panel

39 rutas: **24 GET** (lectura) y **15 POST** (escriben en Sheets, suben a Drive, encolan
envíos de WhatsApp). Incluye `/api/debug`, `/api/debug/respuestas` y `/api/test/<key>`.

### 1.6 Las hojas son compartidas con otros proyectos

Decisión del owner: **se trabaja sobre los spreadsheets de producción**, respetando el orden
de columnas, porque están sincronizados con proyectos externos.

Bruce es uno de esos consumidores y corre en el mismo servidor con:

```
WA_SCHEDULER=1    WA_GEO_AUTO=1    WA_BUSCADOR_AUTO=1    WA_CAMPANA_AUTO=0
```

25 archivos de Bruce leen o escriben el spreadsheet `seguimiento`, entre ellos
`motor_recontacto.py`, `cadencias_wa.py`, `campana_inicial.py` y `seguimiento_adapter.py`.

**Consecuencia operativa:** una fila escrita en `seguimiento` / `PROSPECTOS BRUCE` puede
hacer que Bruce envíe un WhatsApp real a ese número, dentro de la ventana 09:00–20:00 MX.
Esto condiciona el protocolo de pruebas de escritura (§7, capa 4).

---

## 2. Objetivo y no-objetivos

**Objetivo:** poner PanelNioval en producción en el servidor Vultr existente, servido por TLS
en `panelnioval.duckdns.org`, con autenticación fail-closed, apagar Railway, y validar el
sistema completo — panel, worker y no-regresión de Bruce.

**No-objetivos** (fuera de alcance, explícitamente):

- Trocear `app.py` (3.6k líneas, viola el límite de 800 de las reglas globales). Es refactor
  no relacionado con el despliegue. Queda como deuda registrada.
- Tocar el importador de prospectos o la lógica de negocio del panel.
- Migrar el worker Selenium al VPS: necesita Chrome real y la sesión de WhatsApp Web. Se
  queda en la PC del owner; solo cambia a dónde apunta.
- Crear hojas espejo de prueba (descartado por §1.6).

---

## 3. Arquitectura destino

Segundo servicio en la red Docker `web`, calcado del patrón de Bruce:

```
/srv/panel/
├── app/                 ← git clone de luisgarciau03-art/PanelNioval
├── secretos/
│   ├── .env             ← chmod 600, fuera de git
│   └── credentials.json ← service account, copiada por scp
└── docker-compose.yml
```

Dos piezas nuevas:

**1. `Dockerfile` en el repo.** PanelNioval solo tiene `Procfile` y `nixpacks.toml`,
artefactos de Railway sin uso fuera de ahí. Se añade uno equivalente al de Bruce:

```dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD gunicorn app:app --bind 0.0.0.0:8000 --workers 2 --timeout 120
```

**2. Bloque en `/srv/proxy/Caddyfile`:**

```
panelnioval.duckdns.org {
	reverse_proxy panel:8000
}
```

El contenedor **no publica puertos**: solo alcanzable por la red interna, igual que Bruce.
Caddy emite y renueva el certificado Let's Encrypt automáticamente.

`docker-compose.yml` con `container_name: panel`, `restart: unless-stopped`,
`mem_limit: 768m` y rotación de logs (`max-size: 10m`, `max-file: 3`), para que el panel no
pueda tumbar al bot.

El `container_name: panel` no es cosmético: es el nombre que Caddy resuelve por DNS interno
de Docker en `reverse_proxy panel:8000`. Si no coincide, el proxy devuelve 502.

**Actualización de código:** `git pull` en `/srv/panel/app` + `docker compose up -d --build`,
el mismo flujo que Bruce.

---

## 4. Endurecimiento fail-closed

Cambio de código en `app.py`, con rama y PR propios. Los defaults se invierten:

| Gate | Hoy | Después |
|---|---|---|
| `PANEL_DASHBOARD_TOKEN` ausente | panel abierto | la app **no arranca** (`RuntimeError` con mensaje claro) |
| `WORKER_TOKEN` ausente en heartbeat | 200, acepta la escritura | **401** |
| `SECRET_KEY` ausente con auth activa | `print()` de advertencia | la app **no arranca** |

Escape hatch único, explícito y ruidoso: `PANEL_AUTH_DESACTIVADA=1` para desarrollo local y
para la suite de tests. El default deja de ser "abierto"; quien abra el panel tiene que
escribirlo a propósito.

**Coste declarado:** los 155 tests actuales (antes de esta rama) llaman rutas sin token y dependen del
comportamiento fail-open. La corrección esperada es fijar `PANEL_AUTH_DESACTIVADA=1` en
`conftest.py` — es el `conftest`, no 155 tests. Esta rama suma 9 tests más. El alcance exacto no se conoce hasta correr
la suite; si resulta mayor, se reporta antes de seguir.

---

## 5. Secretos

Cinco variables **críticas de arranque** en `/srv/panel/secretos/.env`, `chmod 600`, nunca
en git:

| Variable | Origen |
|---|---|
| `PANEL_DASHBOARD_TOKEN` | generado en el servidor, `openssl rand -hex 32` |
| `WORKER_TOKEN` | ídem |
| `SECRET_KEY` | ídem |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | el vigente — ver gate §8.3 |

Tres variables adicionales son **de función, no de arranque**: la app arranca y sirve sin
ellas, pero la ruta que las usa falla visiblemente (nunca en silencio) al invocarse. Deben
cargarse en el mismo `.env` antes de dar por completo el go-live de las funciones asociadas:

| Variable | Sin ella | Ruta afectada |
|---|---|---|
| `IMGBB_API_KEY` (`app.py:425`) | 500 al subir el comprobante | `/api/ventas/upload-pago` |
| `GMAPS_API_KEY` (`app.py:4434`) | `{"ok": false}` sin arrancar la búsqueda | `/api/importador/iniciar` |
| `PAGO_FOLDER_ID` (`app.py:157`) | `get_pago_folder_id()` (`app.py:158`) lanza `ValueError` si se invoca | ninguna ruta activa hoy la llama — `upload-pago` usa `IMGBB_API_KEY`, no Drive; se documenta por si el flujo Drive se reactiva |

`GOOGLE_CREDENTIALS_JSON` no se usa: la service account se monta como volumen `:ro`, igual
que Bruce. Viaja por `scp`, nunca por git (el `.gitignore` ya cubre `*.json`).

**Manejo:** los tokens se generan en el servidor y se quedan ahí. No se pegan en la
conversación, ni en commits, ni en informes. El owner los lee por SSH cuando los necesite.

---

## 6. Corte, DNS y rollback

Orden estricto; cada paso se verifica antes del siguiente:

| # | Paso | Verificación |
|---|---|---|
| 1 | PR de endurecimiento → merge a `main` | baseline de tests en verde |
| 2 | Provisionar `/srv/panel`, levantar contenedor **sin tocar DNS** | `curl -H "Host: panelnioval.duckdns.org"` por red interna |
| 3 | Repuntar DuckDNS `panelnioval` → `155.138.200.66` | resolución + cert emitido por Caddy |
| 4 | Smoke test contra la URL pública | `tools/smoke_panel.py` (sirve tal cual) |
| 5 | Actualizar `iniciar-worker.bat`: `PANEL_URL` + `WORKER_TOKEN` | heartbeat visible en el panel |
| 6 | **Eliminar el servicio de Railway** | la URL vieja deja de responder |
| 7 | Rotar `TELEGRAM_TOKEN` | alerta de prueba recibida |

**Railway muere en el paso 6 a propósito: es el rollback.** Hasta ese momento, si el VPS
falla, la operación sigue en la URL vieja. Después del paso 6 el rollback es redesplegar,
no volver atrás.

**Riesgo de doble escritura:** entre los pasos 3 y 6 hay dos instancias vivas contra las
mismas hojas. La ventana debe ser corta y sin uso operativo del panel viejo. Es el mismo
patrón que causó la duplicación de la hoja Seguimiento de Bruce.

---

## 7. Testeo completo del sistema

Siete capas. El sistema bajo prueba incluye a Bruce: se le añade un servicio a su servidor,
así que un testeo que no verifique su no-regresión no está completo.

### Capa 1 — Suite unitaria
`python -m pytest tests/ -q` → **155 passed**, el baseline oficial antes de esta rama; esta rama sube a **164 passed**. Nada avanza en rojo.

### Capa 2 — Arranque y gates
- La app se niega a arrancar sin `PANEL_DASHBOARD_TOKEN` / `SECRET_KEY`
- `GET /` sin token → **401** (hoy Railway devuelve 200 con el dashboard)
- `POST /api/catalogo/heartbeat` sin `X-Worker-Token` → **401**
- `/api/debug`, `/api/debug/respuestas`, `/api/test/<key>` → **401** sin token
- Certificado TLS válido y emitido por Caddy

### Capa 3 — Lectura
Las 24 rutas GET y las 3 vistas HTML (`/`, `/formulario`, `/importador`) contra las hojas
reales. Sin riesgo: no escriben.

### Capa 4 — Escritura (protocolo sobre producción)

Las 15 rutas POST escriben en hojas compartidas con proyectos externos (§1.6). Protocolo
obligatorio:

1. **Respaldo primero.** Exportar los 5 spreadsheets a copia fechada local **antes** de
   escribir nada. El respaldo existe antes del cambio, no después.
2. **Orden de columnas intocable.** Las escrituras usan el esquema existente tal cual; no se
   inserta ni reordena nada. Se registra el hash de la fila de encabezados antes y después
   para *probar* que la estructura no se movió.
3. **Teléfono del owner, nunca de un cliente.** Toda fila de prueba que toque
   `seguimiento` / `PROSPECTOS BRUCE` lleva el número del owner. Si un job de Bruce la
   levanta, el mensaje llega al owner.
4. **Fuera de ventana, con Bruce pausado.** Esas escrituras se hacen fuera de 09:00–20:00 MX.
   "Pausar Bruce" significa concretamente: `WA_SCHEDULER=0` en `/srv/bruce/secretos/.env`,
   `docker compose up -d` para recargar, y al terminar restaurar el valor original y
   verificar que los 16 jobs volvieron a registrarse. El valor previo de los cuatro flags se
   anota antes de tocarlos.
5. **Marcado y retiro.** `PRUEBA-2026-08-17` en el campo de nombre. Al terminar se retiran
   solo esas filas, con reconteo de filas y revalidación de encabezados contra el pre-test.

**Límite honesto de este protocolo:** si un proyecto externo sincroniza durante la ventana
de prueba, ya leyó la fila; retirarla del sheet no lo deshace aguas abajo. Por eso el
marcado inequívoco y la ventana de baja actividad. Si el owner identifica los consumidores
externos, el protocolo se ajusta.

### Capa 5 — Worker Selenium
Heartbeat autenticado contra la URL nueva, encolado desde el panel, corrección de número, y
un envío real de catálogo **al número del owner**. Nunca a un cliente.

### Capa 6 — No-regresión de Bruce
- Webhook de Meta sigue verificando y recibiendo
- Los 16 jobs del scheduler siguen registrados y activos
- Un envío saliente de prueba llega
- `docker stats`: ambos contenedores dentro de límites, sin presión de swap
- Los flags (`WA_SCHEDULER`, `WA_GEO_AUTO`, `WA_BUSCADOR_AUTO`, `WA_CAMPANA_AUTO`) quedan
  como estaban antes de la prueba

### Capa 7 — Resiliencia
- Reboot del VPS: los tres contenedores vuelven solos (`restart: unless-stopped`)
- Rotación de logs activa en el panel
- Renovación del certificado configurada

---

## 8. Gates del owner

Acciones que no puede ejecutar el agente.

1. **DuckDNS** — token de la cuenta, o el owner repunta el registro (§6, paso 3).
2. **Railway** — sin acceso a esa cuenta; el borrado del servicio (§6, paso 6) es del owner.
   Mientras no ocurra, la exposición de §1.3 sigue abierta.
3. **`TELEGRAM_TOKEN`** — pendiente conocido: está en ~14 copias del historial git.
   Cargarlo tal cual en el VPS migra una credencial quemada. Recomendación: rotarlo
   **antes** de §6 paso 1 y montar el nuevo directo. Retirarlo del código no lo desactiva;
   solo la rotación en el proveedor cierra el riesgo.
4. **Ventana de prueba** — confirmar el horario fuera de 09:00–20:00 MX y el número del
   owner para las capas 4 y 5.
5. **Proyectos externos** — identificar qué más sincroniza los 5 spreadsheets, para apretar
   el protocolo de la capa 4.

---

## 9. Riesgos aceptados

| Riesgo | Mitigación | Residual |
|---|---|---|
| Doble escritura entre pasos 3 y 6 | ventana corta, sin uso del panel viejo | bajo |
| Fila de prueba disparando un envío de Bruce | teléfono del owner + fuera de ventana + scheduler pausado | bajo |
| Sync externo leyendo una fila de prueba | marcado inequívoco + ventana de baja actividad | **no eliminable** |
| RAM del box con un tercer servicio | `mem_limit: 768m`, 1.3 GB libres, 5.4 GB swap, medición en capa 6 | bajo |
| La suite depende del fail-open más de lo previsto | se reporta antes de seguir en vez de forzar el merge | medio |

---

## 10. Criterios de aceptación

La migración está terminada cuando **todo** esto es cierto y está evidenciado:

1. `panelnioval.duckdns.org` sirve el panel por TLS válido desde `155.138.200.66`
2. Sin token, cualquier ruta del panel devuelve 401 — verificado, no supuesto
3. La app no arranca sin sus secretos
4. `pytest tests/ -q` → 164 passed
5. Las 7 capas de prueba pasan, con su evidencia registrada
6. El worker local opera contra la URL nueva y su heartbeat se ve en el panel
7. Railway está eliminado y su URL no responde
8. Bruce no se degradó: webhook, 16 jobs y envío saliente verificados **después** del cambio
9. Los encabezados de los 5 spreadsheets son idénticos a los del respaldo previo
10. Ningún valor de credencial aparece en commits, informes ni en la conversación
