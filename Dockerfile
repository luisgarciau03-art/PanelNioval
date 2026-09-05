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
