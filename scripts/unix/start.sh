#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs"
API_PORT=4321
WEB_PORT=1234

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

is_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

start_service() {
  local name="$1"
  local port="$2"
  local cmd="$3"
  local pid_file="$4"
  local log_file="$5"

  if is_listening "$port"; then
    echo "$name already running on port $port"
    return
  fi

  bash -lc "$cmd" >>"$log_file" 2>&1 &
  local pid=$!
  echo "$pid" >"$pid_file"
  sleep 1

  if is_listening "$port"; then
    echo "$name started on port $port (PID $pid)"
  else
    echo "$name failed to bind port $port, check $log_file"
  fi
}

if [[ ! -x "$ROOT/api/.venv/bin/python" ]]; then
  echo "Missing API venv: cd api && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [[ ! -d "$ROOT/web/node_modules" ]]; then
  echo "Missing web dependencies: cd web && npm install"
  exit 1
fi

start_service \
  "API" \
  "$API_PORT" \
  "cd '$ROOT/api' && '$ROOT/api/.venv/bin/python' -m uvicorn app.main:app --reload --host 127.0.0.1 --port $API_PORT" \
  "$RUNTIME_DIR/api.pid" \
  "$LOG_DIR/api.dev.log"

start_service \
  "Web" \
  "$WEB_PORT" \
  "cd '$ROOT/web' && npm run dev" \
  "$RUNTIME_DIR/web.pid" \
  "$LOG_DIR/web.dev.log"
