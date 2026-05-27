#!/usr/bin/env bash
# Script de inicio para Render (plan free - 1 worker para evitar OOM con RapidOCR)
exec gunicorn main:app \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 180 \
    --max-requests 50 \
    --max-requests-jitter 10 \
    --access-logfile - \
    --error-logfile -
