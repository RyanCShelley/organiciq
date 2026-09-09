#!/bin/sh
set -eu

PORT="${PORT:-8000}"

echo "Running alembic upgrade head..."
alembic upgrade head

# Process sync jobs in-process until a dedicated Railway worker service is stable.
# Set EMBEDDED_WORKER=false when running a separate worker service.
if [ "${EMBEDDED_WORKER:-true}" = "true" ]; then
  echo "Starting embedded sync worker..."
  python -m app.worker &
fi

echo "Starting API on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
