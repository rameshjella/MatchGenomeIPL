#!/usr/bin/env bash
set -euo pipefail

BIND_HOST="0.0.0.0"
PORT="8080"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lan)
      BIND_HOST="0.0.0.0"
      shift
      ;;
    --host)
      BIND_HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      echo "Usage: ./start.sh [--lan] [--host <host>] [--port <port>]" >&2
      exit 1
      ;;
  esac
done

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
echo "[RUN] Starting Time Machine app on ${BIND_HOST}:${PORT}..."

if [[ "$BIND_HOST" == "0.0.0.0" ]]; then
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -n "$LAN_IP" ]]; then
    echo "[LAN] Open from another system/mobile: http://${LAN_IP}:${PORT}"
  else
    echo "[LAN] Host is exposed on all interfaces. Use this machine's IPv4 with port ${PORT}."
  fi
fi

if ! "$PYTHON_EXE" -c "import sqlite3" >/dev/null 2>&1; then
  echo "[ERROR] Missing Python sqlite3 module support in this environment." >&2
  exit 1
fi

cd "$REPO_ROOT"
export MATCHGENOME_HOST="$BIND_HOST"
export MATCHGENOME_PORT="$PORT"
exec "$PYTHON_EXE" -u "$RUNNER"

