#!/usr/bin/env bash
# Install official Interactive Brokers ibapi from source/pythonclient.
# Source MUST come from https://interactivebrokers.github.io/ (SECURITY.md T6).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${TWS_API_PYTHONCLIENT:-}" ]]; then
  cat <<'EOF'
Set TWS_API_PYTHONCLIENT to the official source/pythonclient directory, e.g.:

  export TWS_API_PYTHONCLIENT="$HOME/IBJts/source/pythonclient"
  ./scripts/install_ibapi.sh

Download the TWS API (Mac/Unix Latest) from:
  https://interactivebrokers.github.io/

Do NOT install ibapi from PyPI.
EOF
  exit 1
fi

if [[ ! -f "$TWS_API_PYTHONCLIENT/setup.py" ]]; then
  echo "setup.py not found in TWS_API_PYTHONCLIENT=$TWS_API_PYTHONCLIENT" >&2
  exit 1
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python3"
fi

"$PYTHON" -m pip install "$TWS_API_PYTHONCLIENT"
"$PYTHON" -m pip show ibapi

echo "Official ibapi installed from $TWS_API_PYTHONCLIENT"
