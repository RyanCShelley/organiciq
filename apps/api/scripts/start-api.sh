#!/bin/sh
# Deliberately not `set -e`: a failed migration must not stop the API starting.
set -u

PORT="${PORT:-8000}"
MIGRATION_STATE_FILE="${MIGRATION_STATE_FILE:-/tmp/organiciq-migration-state}"
MIGRATION_LOG="${MIGRATION_LOG:-/tmp/organiciq-migration.log}"
export MIGRATION_STATE_FILE MIGRATION_LOG

echo "Running alembic upgrade head..."
if alembic upgrade head >"$MIGRATION_LOG" 2>&1; then
  cat "$MIGRATION_LOG"
  printf 'ok' >"$MIGRATION_STATE_FILE"
else
  # This used to run under `set -e`, so a migration that would not even resolve
  # exited the script and the API never started — every page 404ed, with the
  # real cause buried in a boot log nobody was watching. Starting against the
  # existing schema is worse than a clean deploy and much better than an
  # outage, so the failure is recorded and surfaced on /health instead.
  printf 'failed' >"$MIGRATION_STATE_FILE"
  echo "=========================================================" >&2
  echo "MIGRATION FAILED. Starting the API against the existing" >&2
  echo "schema. Anything the migration would have added is absent." >&2
  echo "=========================================================" >&2
  cat "$MIGRATION_LOG" >&2
fi

# Process sync jobs in-process until a dedicated Railway worker service is stable.
# Set EMBEDDED_WORKER=false when running a separate worker service.
if [ "${EMBEDDED_WORKER:-true}" = "true" ]; then
  echo "Starting embedded sync worker..."
  python -m app.worker &
fi

echo "Starting API on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
