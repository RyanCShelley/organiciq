#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${API_DIR}/../.." && pwd)"
WEB_DIR="${REPO_ROOT}/apps/web-v2"

read -r DEFAULT_API_PORT DEFAULT_WEB_PORT < <(
  "${API_DIR}/.venv/bin/python" -c "
import socket
s1 = socket.socket()
s2 = socket.socket()
s1.bind(('127.0.0.1', 0))
s2.bind(('127.0.0.1', 0))
print(s1.getsockname()[1], s2.getsockname()[1])
s1.close()
s2.close()
"
)

API_PORT="${API_PORT:-${DEFAULT_API_PORT}}"
WEB_PORT="${WEB_PORT:-${DEFAULT_WEB_PORT}}"

export APP_ENV="test"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://ryanshelley@localhost:5432/organiciq_test_e2e_phase4}"
export DATABASE_URL="${TEST_DATABASE_URL}"
export AUTH_SECRET="${AUTH_SECRET:-test-auth-secret-for-the-suite-only-0123456789}"
export AUTH_URL="http://127.0.0.1:${WEB_PORT}"
export AUTH_ORIGIN="http://127.0.0.1:${WEB_PORT}"
export NEXTAUTH_URL="http://127.0.0.1:${WEB_PORT}"
export API_URL="http://127.0.0.1:${API_PORT}"
export NEXT_PUBLIC_API_URL="http://127.0.0.1:${API_PORT}"
export WEB_URL="http://127.0.0.1:${WEB_PORT}"
export SMA_ADMIN_EMAILS="${SMA_ADMIN_EMAILS:-admin@smamarketing.com}"

WORK_TMP="$(mktemp -d)"
MANIFEST_PATH="${WORK_TMP}/seed-manifest.json"
API_LOG="${WORK_TMP}/mock_api.log"
WEB_LOG="${WORK_TMP}/next_web.log"
export SEED_MANIFEST_PATH="${MANIFEST_PATH}"

API_PID=""
WEB_PID=""

cleanup() {
  local rc=$?
  set +e
  if [[ "${rc}" -ne 0 ]]; then
    if [[ -f "${API_LOG}" ]]; then
      echo "=== mock_api.log (tail) ===" >&2
      tail -n 40 "${API_LOG}" >&2
    fi
    if [[ -f "${WEB_LOG}" ]]; then
      echo "=== next_web.log (tail) ===" >&2
      tail -n 40 "${WEB_LOG}" >&2
    fi
  fi
  if [[ -n "${WEB_PID}" ]]; then
    kill "${WEB_PID}" 2>/dev/null || true
    wait "${WEB_PID}" 2>/dev/null || true
  fi
  if [[ -n "${API_PID}" ]]; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
  rm -rf "${WORK_TMP}"
  exit "${rc}"
}
trap cleanup EXIT INT TERM

echo "Starting mock_api_server on 127.0.0.1:${API_PORT}..."
(
  cd "${API_DIR}"
  exec "${API_DIR}/.venv/bin/python" -m e2e_phase4.mock_api_server \
    --host 127.0.0.1 \
    --port "${API_PORT}" \
    --seed-browser-suite \
    --seed-manifest "${MANIFEST_PATH}"
) >"${API_LOG}" 2>&1 &
API_PID=$!

for _ in $(seq 1 120); do
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "mock_api_server exited prematurely. Log:" >&2
    cat "${API_LOG}" >&2
    exit 1
  fi
  if [[ -s "${MANIFEST_PATH}" ]] && curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 || [[ ! -s "${MANIFEST_PATH}" ]]; then
  echo "Timed out waiting for mock_api_server or seed manifest. Log:" >&2
  cat "${API_LOG}" >&2
  exit 1
fi

echo "Starting apps/web-v2 on 127.0.0.1:${WEB_PORT}..."
(
  cd "${WEB_DIR}"
  if [[ -f "${WEB_DIR}/.next/BUILD_ID" ]]; then
    exec npx next start -H 127.0.0.1 -p "${WEB_PORT}"
  else
    exec npx next dev -H 127.0.0.1 -p "${WEB_PORT}"
  fi
) >"${WEB_LOG}" 2>&1 &
WEB_PID=$!

for _ in $(seq 1 120); do
  if ! kill -0 "${WEB_PID}" 2>/dev/null; then
    echo "Next.js server exited prematurely. Log:" >&2
    cat "${WEB_LOG}" >&2
    exit 1
  fi
  if curl -fsS "http://127.0.0.1:${WEB_PORT}/login" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "http://127.0.0.1:${WEB_PORT}/login" >/dev/null 2>&1; then
  echo "Timed out waiting for apps/web-v2 on http://127.0.0.1:${WEB_PORT}/login. Log:" >&2
  cat "${WEB_LOG}" >&2
  exit 1
fi

echo "Executing web_e2e.mjs..."
node "${SCRIPT_DIR}/web_e2e.mjs"
