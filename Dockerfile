FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Zona horaria del contenedor (Plan 5 T5.3, M2). python:3.11-slim corre en UTC
# y Mexico es UTC-6: sin esto, los logs y cualquier `date` del contenedor van
# seis horas adelantados respecto a lo que ve el owner.
#
# Es la SEGUNDA capa, no la unica. El codigo usa ZoneInfo explicito
# (nucleo_catalogo.ahora_mexico), porque confiar solo en esta variable dejaria
# el resultado dependiendo del despliegue: en la maquina del owner (Windows,
# hora local) y en el runner de CI (UTC) los tests darian resultados distintos.
# La variable arregla los logs; el codigo arregla los datos.
ENV TZ=America/Mexico_City

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Healthcheck (Plan 5 T5.4, M9). Sin esto, un contenedor que arranco pero no
# responde queda `Up` para Docker y para Caddy, y el owner se entera cuando abre
# el panel.
#
# QUE HACE Y QUE NO. Marca el contenedor `unhealthy`, y eso es TODO: en docker
# compose plano el estado de salud es informativo. `restart: unless-stopped`
# reacciona a que el PROCESO termine, no a que el healthcheck falle, y el
# fragmento de Caddy hace `reverse_proxy panel:8000` sin `health_uri`, asi que
# sigue enrutando trafico a un contenedor enfermo. O sea que esto da
# VISIBILIDAD en `docker ps`, no auto-reparacion. Cerrar esa brecha es decision
# del owner: o un sidecar `autoheal` en el compose, o `health_uri /salud` en
# Caddy para que deje de enrutar. (El comentario anterior afirmaba un "bucle de
# reinicios" que no ocurre; lo corrigio code-reviewer.)
#
# Se usa PYTHON y no curl/wget A PROPOSITO: python:3.11-slim no trae ninguno de
# los dos, y un HEALTHCHECK que los invoque falla SIEMPRE y reporta enfermo un
# panel sano. Es el error clasico de esta directiva y es silencioso, porque
# parece que "funciona": efectivamente reporta algo.
#
# ProxyHandler({}) vacio: en Linux, urllib NO exceptua 127.0.0.1 de las
# variables de proxy (a diferencia de macOS y Windows). El compose carga
# `secretos/.env` ENTERO con env_file, asi que el dia que ahi aparezca un
# HTTP_PROXY para cualquier otra cosa, el healthcheck saldria a la red en vez de
# sondear localhost — y reportaria enfermo un panel sano, que es justo el fallo
# que este bloque intenta evitar.
#
# start-period 40s: el arranque en frio importa googleapiclient y tarda. Sin
# margen, el contenedor se marcaria unhealthy mientras todavia esta cargando.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3   CMD ["python", "-c", "import urllib.request,sys; abridor=urllib.request.build_opener(urllib.request.ProxyHandler({})); sys.exit(0 if abridor.open('http://127.0.0.1:8000/salud', timeout=4).status == 200 else 1)"]


# UN worker con hilos, no dos procesos. _import_job y _cache son globales de
# modulo: con --workers 2 son dos memorias distintas y la mitad de los sondeos
# del importador responde 'idle' con el trabajo corriendo (medido: 10 de 20).
# El trabajo es I/O contra Google, donde el GIL se libera, asi que 4 hilos dan
# mas concurrencia real que 2 workers sincronos.
# Razonamiento completo: docs/adr/2026-08-27-estado-compartido-importador.md
# Forma exec: gunicorn queda como PID 1 y recibe el SIGTERM de `docker stop`
# directamente. En forma shell, PID 1 seria /bin/sh, que no reenvia senales:
# cada parada terminaria en SIGKILL a los 10s, cortando peticiones en vuelo.
# --graceful-timeout 120: la parada ordenada del importador (Plan 5 T5.5) se
# consulta en puntos seguros del bucle, y con los 30 s por defecto de gunicorn
# el SIGKILL llegaba antes de que el hilo alcanzara uno. Sin esto, la parada
# ordenada existe en el codigo y no se ejecuta nunca en produccion.
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "--graceful-timeout", "120"]
