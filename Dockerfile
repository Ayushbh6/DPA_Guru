FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/apps/api/src:/app/apps/api:/app/packages/checklist/python:/app/packages/schemas/python

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

COPY apps/api /app/apps/api
COPY packages/checklist/python /app/packages/checklist/python
COPY packages/schemas/python /app/packages/schemas/python
COPY kb /app/kb

CMD ["sh", "-lc", "set -e; if [ \"${SERVICE_KIND:-api}\" = \"worker\" ]; then python -m upload_api worker; else if [ \"${RUN_MIGRATIONS:-0}\" = \"1\" ]; then cd /app/apps/api && alembic -c alembic.ini upgrade head; cd /app; fi; exec uvicorn upload_api.main:app --host 0.0.0.0 --port ${PORT:-8001}; fi"]
