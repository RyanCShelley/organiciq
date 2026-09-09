#!/bin/sh
set -eu

# One image, two Railway services: set SERVICE_ROLE=worker on the worker service.
role="${SERVICE_ROLE:-api}"

if [ "$role" = "worker" ]; then
  exec scripts/start-worker.sh
fi

exec scripts/start-api.sh
