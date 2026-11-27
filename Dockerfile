FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=fridge_service.settings \
    HOST=0.0.0.0 \
    PORT=8000 \
    SQLITE_PATH=/app/backend/fridge.db \
    MEDIA_ROOT=/app/backend/uploads \
    UVICORN_RELOAD=false

WORKDIR /app/backend

COPY backend/requirements.txt /app/backend/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements.txt

COPY backend/ /app/backend/

EXPOSE 8000

CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker fridge_service.asgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-2}"]