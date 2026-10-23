#!/usr/bin/env bash
# Run from any directory: bash scripts/check-local.sh
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src freecad_addon
echo "Local FreeCAD MCP checks passed"
