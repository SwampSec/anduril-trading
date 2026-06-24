#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python3"
fi

if [[ -f "$ROOT/.env.broker" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.broker"
  set +a
fi

HOST="${API_HOST:-127.0.0.1}"
PORT="${API_PORT:-9001}"

exec "$PYTHON" -m uvicorn api.main:app --host "$HOST" --port "$PORT" --reload
