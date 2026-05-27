#!/usr/bin/env bash
# Script de inicio para Render
# Usa gunicorn con workers uvicorn para producción
exec gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
