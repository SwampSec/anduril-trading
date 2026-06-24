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

cp "${ROOT}/scripts/launch_anduril.sh" "${INSTALL_ROOT}/launch.sh"
chmod +x "${INSTALL_ROOT}/launch.sh"
echo "  ✓ launch.sh"

if [[ -f "${INSTALL_ROOT}/Anduril Trading.command" ]]; then
  cat > "${INSTALL_ROOT}/Anduril Trading.command" <<'CMD'
#!/usr/bin/env bash
exec bash "$HOME/Anduril/launch.sh"
CMD
  chmod +x "${INSTALL_ROOT}/Anduril Trading.command"
fi

DESKTOP_CMD="${HOME}/Desktop/Anduril Trading.command"
if [[ -d "${HOME}/Desktop" ]]; then
  cat > "${DESKTOP_CMD}" <<'CMD'
#!/usr/bin/env bash
exec bash "$HOME/Anduril/launch.sh"
CMD
  chmod +x "${DESKTOP_CMD}"
  echo "  ✓ Desktop/Anduril Trading.command"
fi

echo ""
echo "Done. Launch with:"
echo "  bash ${INSTALL_ROOT}/launch.sh"
echo "Or double-click: Anduril Trading.command on Desktop (if linked)"
