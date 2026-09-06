#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$REPO_ROOT/scripts/run_time_machine_app.py"
VENV_PY="$REPO_ROOT/.venv/bin/python"

if [[ ! -f "$RUNNER" ]]; then
  echo "[ERROR] Could not find runner script at $RUNNER" >&2
  exit 1
fi

if [[ -x "$VENV_PY" ]]; then
  PYTHON_EXE="$VENV_PY"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python)"
else
  echo "[ERROR] Python was not found. Activate your environment or install Python 3.10+." >&2
  exit 1
fi

echo "[STARTUP] MatchGenomeIPL"
echo "[ENV] Python executable: $PYTHON_EXE"
echo "[RUN] Starting Time Machine app..."

if ! "$PYTHON_EXE" -c "import sqlite3" >/dev/null 2>&1; then
  echo "[ERROR] Missing Python sqlite3 module support in this environment." >&2
  exit 1
fi

cd "$REPO_ROOT"
exec "$PYTHON_EXE" -u "$RUNNER"

