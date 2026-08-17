FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Forma exec: gunicorn queda como PID 1 y recibe el SIGTERM de `docker stop`
# directamente. En forma shell, PID 1 seria /bin/sh, que no reenvia senales:
# cada parada terminaria en SIGKILL a los 10s, cortando peticiones en vuelo.
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
