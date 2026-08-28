FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

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
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--worker-class", "gthread", "--timeout", "120"]
