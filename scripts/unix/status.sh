#!/usr/bin/env bash
set -euo pipefail

show_status() {
  local name="$1"
  local port="$2"

  local pids
  pids="$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"

  if [[ -z "$pids" ]]; then
    echo "$name: stopped (port $port)"
  else
    echo "$name: running (port $port, PID ${pids//$'\n'/,})"
  fi
}

show_status "API" 4321
show_status "Web" 1234
