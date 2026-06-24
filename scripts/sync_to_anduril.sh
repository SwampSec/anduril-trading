#!/usr/bin/env bash
# Refresh ~/Anduril install from this repo (dashboard + copilot). API stays in repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_ROOT="${ANDURIL_INSTALL_ROOT:-$HOME/Anduril}"

echo "Syncing Anduril install → ${INSTALL_ROOT}"

mkdir -p "${INSTALL_ROOT}/dashboard"

cp "${ROOT}/_app_source.py" "${INSTALL_ROOT}/dashboard/app.py"
echo "  ✓ dashboard/app.py"

if [[ -d "${ROOT}/copilot" ]]; then
  rm -rf "${INSTALL_ROOT}/copilot"
  cp -R "${ROOT}/copilot" "${INSTALL_ROOT}/copilot"
  echo "  ✓ copilot/"
fi

if [[ -f "${ROOT}/guide.html" ]]; then
  cp "${ROOT}/guide.html" "${INSTALL_ROOT}/guide.html"
  echo "  ✓ guide.html"
fi

if [[ -x "${INSTALL_ROOT}/venv/bin/pip" ]]; then
  "${INSTALL_ROOT}/venv/bin/pip" install -q -r "${ROOT}/requirements.txt" 2>/dev/null || true
  echo "  ✓ pip deps (dashboard)"
fi

cat > "${INSTALL_ROOT}/launch.sh" <<LAUNCH
#!/usr/bin/env bash
set -euo pipefail
INSTALL_ROOT="${INSTALL_ROOT}"
REPO_ROOT="${ROOT}"
source "\${INSTALL_ROOT}/venv/bin/activate"

export ANDURIL_API_BASE="\${ANDURIL_API_BASE:-http://127.0.0.1:9001}"

if ! curl -sf "\${ANDURIL_API_BASE}/health" >/dev/null 2>&1; then
  echo "Starting trading API from \${REPO_ROOT}..."
  if [[ -f "\${REPO_ROOT}/.env.broker" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "\${REPO_ROOT}/.env.broker"
    set +a
  fi
  if [[ -x "\${REPO_ROOT}/.venv/bin/python" ]]; then
    (cd "\${REPO_ROOT}" && "\${REPO_ROOT}/.venv/bin/python" -m uvicorn api.main:app --host "\${API_HOST:-127.0.0.1}" --port "\${API_PORT:-9001}" &) 
  else
    echo "  ⚠ API venv missing at \${REPO_ROOT}/.venv — run: cd \${REPO_ROOT} && python3 -m venv .venv && pip install -r requirements.txt"
  fi
  sleep 2
fi

echo ""
echo "  Andúril Trading Suite"
echo "  Dashboard  →  http://127.0.0.1:8050"
echo "  Bot API    →  \${ANDURIL_API_BASE}"
echo "  Trades     →  http://127.0.0.1:8050/trades"
echo "  Press Ctrl+C to stop dashboard (API keeps running in background)"
echo ""

python "\${INSTALL_ROOT}/dashboard/app.py" &
dash_pid=\$!
for _ in \$(seq 1 30); do
  if curl -sf "http://127.0.0.1:8050/" >/dev/null 2>&1; then
    open "http://127.0.0.1:8050/trades" 2>/dev/null || true
    break
  fi
  sleep 0.5
done

wait "\${dash_pid}"
LAUNCH
chmod +x "${INSTALL_ROOT}/launch.sh"

if [[ -f "${INSTALL_ROOT}/Anduril Trading.command" ]]; then
  cp "${INSTALL_ROOT}/launch.sh" "${INSTALL_ROOT}/Anduril Trading.command"
  chmod +x "${INSTALL_ROOT}/Anduril Trading.command"
fi

echo ""
echo "Done. Launch with:"
echo "  bash ${INSTALL_ROOT}/launch.sh"
echo "Or double-click: Anduril Trading.command on Desktop (if linked)"
