#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

bash "$ROOT/scripts/unix/start.sh"
echo "Logs: $ROOT/logs/api.dev.log and $ROOT/logs/web.dev.log"
