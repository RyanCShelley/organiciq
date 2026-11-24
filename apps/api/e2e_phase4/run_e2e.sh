#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export APP_ENV=test
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://ryanshelley@localhost:5432/organiciq_test_e2e_phase4}"
exec .venv/bin/pytest e2e_phase4 -v "$@"
