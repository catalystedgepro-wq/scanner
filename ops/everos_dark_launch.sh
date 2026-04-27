#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${CEREBRO_ENV_FILE:-$ROOT/.env}"
API_URL="${CEREBRO_API_URL:-http://127.0.0.1:8000}"
EVEROS_URL="${EVEROS_BASE_URL_OVERRIDE:-http://127.0.0.1:1995}"
SERVICE_NAME="${CEREBRO_SERVICE_NAME:-cerebro.service}"
ACTION="${1:-status}"

runtime_gate_check() {
  (cd "$ROOT" && bash ops/check_mnemosyne_lanes.sh --mode runtime >/dev/null)
}

write_probe() {
  (cd "$ROOT" && python3 everos_pipeline_ingest.py --mode manual --status success --reason dark_launch_probe)
}

set_env_var() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = []
if path.exists():
    lines = path.read_text(encoding="utf-8").splitlines()
updated = False
for index, line in enumerate(lines):
    if line.startswith(f"{key}="):
        lines[index] = f"{key}={value}"
        updated = True
        break
if not updated:
    lines.append(f"{key}={value}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

show_status() {
  python3 - "$ENV_FILE" "$API_URL" "$EVEROS_URL" <<'PY'
import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

env_path = Path(sys.argv[1])
api_url = sys.argv[2].rstrip("/")
everos_url = sys.argv[3].rstrip("/")
enabled = "missing"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("EVEROS_ENABLED="):
            enabled = line.split("=", 1)[1].strip()
            break
print(f"EVEROS_ENABLED={enabled}")
try:
    with urlopen(f"{api_url}/api/health", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    everos = payload.get("everos") or {}
    runtime = payload.get("model_runtime") or {}
    print(json.dumps({
        "everos": everos,
        "model_runtime": runtime,
    }, indent=2))
except Exception as exc:
    print(f"api_health_error={exc}")
try:
    with urlopen(f"{everos_url}/health", timeout=5) as response:
        body = response.read().decode("utf-8", "replace")
    print(f"everos_backend={body}")
except URLError as exc:
    print(f"everos_backend_error={exc.reason}")
except Exception as exc:
    print(f"everos_backend_error={exc}")
PY
}

verify_enabled() {
  python3 - "$API_URL" <<'PY'
import json
import sys
from urllib.request import urlopen

api_url = sys.argv[1].rstrip("/")
with urlopen(f"{api_url}/api/health", timeout=10) as response:
    payload = json.loads(response.read().decode("utf-8", "replace"))
everos = payload.get("everos") or {}
if not everos.get("enabled"):
    raise SystemExit("EVEROS not enabled in /api/health")
if not everos.get("configured"):
    raise SystemExit("EVEROS not configured in /api/health")
if not everos.get("backend_available"):
    raise SystemExit("EVEROS backend is not available according to /api/health")
print("EVEROS dark launch verified")
PY
}

restart_service() {
  systemctl restart "$SERVICE_NAME"
  sleep 2
}

case "$ACTION" in
  status)
    show_status
    ;;
  enable)
    runtime_gate_check || true
    python3 - "$EVEROS_URL" <<'PY'
import sys
from urllib.request import urlopen

everos_url = sys.argv[1].rstrip("/")
with urlopen(f"{everos_url}/health", timeout=5) as response:
    body = response.read().decode("utf-8", "replace")
if "healthy" not in body.lower() and "\"ok\"" not in body.lower():
    raise SystemExit(f"EverOS backend not healthy enough for launch: {body}")
PY
    set_env_var "EVEROS_ENABLED" "1"
    restart_service
    runtime_gate_check
    verify_enabled
    write_probe
    show_status
    ;;
  disable)
    set_env_var "EVEROS_ENABLED" "0"
    restart_service
    runtime_gate_check
    show_status
    ;;
  verify)
    runtime_gate_check
    verify_enabled
    ;;
  *)
    echo "usage: $0 {status|enable|disable|verify}" >&2
    exit 1
    ;;
esac
