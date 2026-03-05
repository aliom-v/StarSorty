#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="$ROOT/.run"
API_PORT=4321
WEB_PORT=1234

kill_by_pid_file() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$pid" >/dev/null 2>&1 || true
    echo "$name stopped (PID $pid)"
  fi
  rm -f "$pid_file"
}

kill_by_port() {
  local name="$1"
  local port="$2"

  local pids
  pids="$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "$name not running on port $port"
    return
  fi

  echo "$pids" | xargs kill >/dev/null 2>&1 || true
  sleep 1
  echo "$pids" | xargs kill -9 >/dev/null 2>&1 || true
  echo "$name stopped by port $port"
}

mkdir -p "$RUNTIME_DIR"
kill_by_pid_file "API" "$RUNTIME_DIR/api.pid"
kill_by_pid_file "Web" "$RUNTIME_DIR/web.pid"
kill_by_port "API" "$API_PORT"
kill_by_port "Web" "$WEB_PORT"
