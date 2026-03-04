#!/bin/sh
set -e

case "$1" in
  api)
    exec uvicorn src.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python -m src.workflows.worker
    ;;
  *)
    exec "$@"
    ;;
esac
