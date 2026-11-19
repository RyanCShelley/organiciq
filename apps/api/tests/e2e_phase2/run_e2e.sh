#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${API_DIR}"

export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://ryanshelley@localhost:5432/organiciq_test_e2e}"

exec .venv/bin/pytest tests/e2e_phase2 -v "$@"
