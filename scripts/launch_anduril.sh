#!/usr/bin/env bash
INSTALL_ROOT="${HOME}/Anduril"
REPO_ROOT="${HOME}/Documents/Tools/Anduril-Trading"

cd "${INSTALL_ROOT}" || exit 1
source "${INSTALL_ROOT}/venv/bin/activate"

export ANDURIL_API_BASE="${ANDURIL_API_BASE:-http://127.0.0.1:9001}"

# API in background (bot/trades features) — dashboard is the main app on :8050
if ! curl -sf "${ANDURIL_API_BASE}/health" >/dev/null 2>&1; then
  echo "Starting trading API..."
  if [[ -f "${REPO_ROOT}/.env.broker" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.env.broker"
    set +a
  fi
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    (cd "${REPO_ROOT}" && nohup "${REPO_ROOT}/.venv/bin/python" -m uvicorn api.main:app \
      --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-9001}" \
      >/tmp/anduril-api.log 2>&1 &)
    sleep 2
  else
    echo "Warning: API not started — missing ${REPO_ROOT}/.venv"
  fi
fi

echo ""
echo "  Andúril Trading Suite"
echo "  Dashboard  →  http://127.0.0.1:8050"
echo "  Trades       →  http://127.0.0.1:8050/trades"
echo "  Bot API      →  ${ANDURIL_API_BASE}/docs"
echo ""

python "${INSTALL_ROOT}/dashboard/app.py" &
dash_pid=$!

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:8050/" >/dev/null 2>&1; then
    open "http://127.0.0.1:8050/trades"
    break
  fi
  sleep 0.5
done

wait "${dash_pid}"
