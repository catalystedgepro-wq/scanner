#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="release"

usage() {
  cat <<'EOF'
Usage:
  bash ops/check_mnemosyne_lanes.sh [--mode release|runtime]

Modes:
  release  Check local release surfaces, including vendored EverOS/MSA repos.
  runtime  Check runtime-facing surfaces and EVEROS_ENABLED guard state.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo "Missing value for --mode" >&2; exit 1; }
      MODE="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$MODE" != "release" && "$MODE" != "runtime" ]]; then
  echo "Unsupported mode: $MODE" >&2
  exit 1
fi

required_files=(
  ".agents/skills/everos-memory-os/SKILL.md"
  ".agents/skills/msa-memory-sparse-attention/SKILL.md"
  "everos_memory_client.py"
  "everos_pipeline_ingest.py"
  "spoke_memory.py"
  "build_sympathy_logger.py"
  "CEREBRO_EVERMIND_INTEGRATION.md"
  "CEREBRO_MEMORY_AGENT_POLICY.md"
)

if [[ "$MODE" == "release" ]]; then
  required_files+=(
    "vendor/evermind/EverOS"
    "vendor/evermind/MSA"
  )
fi

missing=()
for rel_path in "${required_files[@]}"; do
  if [[ ! -e "$ROOT/$rel_path" ]]; then
    missing+=("$rel_path")
  fi
done

everos_enabled="unset"
for env_file in "$ROOT/.env" "$ROOT/.sec_email_env"; do
  if [[ -f "$env_file" ]]; then
    value="$(grep -h '^EVEROS_ENABLED=' "$env_file" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
    if [[ -n "$value" ]]; then
      everos_enabled="$value"
    fi
  fi
done

runtime_guard_ok="true"
if [[ "$MODE" == "runtime" ]]; then
  if [[ "$everos_enabled" != "0" && "$everos_enabled" != "1" ]]; then
    runtime_guard_ok="false"
  fi
fi

everos_backend_ok="true"
if [[ "$MODE" == "runtime" && "$everos_enabled" == "1" ]]; then
  if ! everos_probe="$(cd "$ROOT" && python3 - <<'PY'
import json
from everos_memory_client import EverOSRequestError, backend_available, load_config

cfg = load_config()
payload = {"enabled": cfg.enabled, "backend_available": False}
try:
    payload["backend_available"] = backend_available(cfg)
except EverOSRequestError:
    payload["backend_available"] = False
print(json.dumps(payload))
raise SystemExit(0 if payload["backend_available"] else 1)
PY
)"; then
    everos_backend_ok="false"
  fi
fi

missing_text="$(printf '%s\n' "${missing[@]:-}" | sed '/^$/d')"
export CHECK_MODE="$MODE"
export CHECK_ROOT="$ROOT"
export EVEROS_ENABLED_VALUE="$everos_enabled"
export RUNTIME_GUARD_OK="$runtime_guard_ok"
export EVEROS_BACKEND_OK="$everos_backend_ok"
export MISSING_TEXT="$missing_text"
python3 - <<'PY'
import json
import os
import sys

mode = os.environ["CHECK_MODE"]
missing = [line for line in os.environ.get("MISSING_TEXT", "").splitlines() if line]
runtime_guard_ok = os.environ.get("RUNTIME_GUARD_OK", "false").lower() == "true"
everos_backend_ok = os.environ.get("EVEROS_BACKEND_OK", "false").lower() == "true"
payload = {
    "mode": mode,
    "root": os.environ.get("CHECK_ROOT"),
    "everos_enabled": os.environ.get("EVEROS_ENABLED_VALUE", "unset"),
    "runtime_guard_ok": runtime_guard_ok,
    "everos_backend_ok": everos_backend_ok,
    "required_vendor_repos": mode == "release",
    "missing": missing,
}
payload["valid"] = (not missing) and (runtime_guard_ok or mode != "runtime") and (everos_backend_ok or mode != "runtime")
print(json.dumps(payload))
raise SystemExit(0 if payload["valid"] else 1)
PY
