#!/bin/sh
set -eu

echo "Starting sync worker..."
exec python -m app.worker
