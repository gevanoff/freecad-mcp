#!/usr/bin/env bash
# Run from any directory: bash scripts/check-local.sh
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# Keep each selected interpreter's environment separate, including distinct
# installations of the same Python version. Never delete an existing venv.
IDENTITY='import hashlib, os, sys; base = os.path.realpath(getattr(sys, "_base_executable", sys.executable)); print(hashlib.sha256((base + "\0" + sys.version).encode()).hexdigest())'
INTERPRETER_ID="$("$PYTHON" -c "$IDENTITY")"
VENV_DIR=".venv-checks/$INTERPRETER_ID"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi
if [[ ! -x "$VENV_DIR/bin/python" ]] || [[ "$("$VENV_DIR/bin/python" -c "$IDENTITY")" != "$INTERPRETER_ID" ]]; then
  echo "Validation environment does not match the selected Python: $VENV_DIR" >&2
  echo "Remove that environment and retry; no files were removed automatically." >&2
  exit 1
fi
"$VENV_DIR/bin/python" -c 'import sys; print("Validation interpreter:", sys.executable, sys.version)'
"$VENV_DIR/bin/python" -m pip install -e .
"$VENV_DIR/bin/python" -m unittest discover -s tests -v
"$VENV_DIR/bin/python" -m compileall -q src freecad_addon
echo "Local FreeCAD MCP checks passed"
