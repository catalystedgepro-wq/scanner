#!/usr/bin/env bash
set -euo pipefail

HOST="${CEREBRO_DEPLOY_HOST:-cerebro}"
REMOTE_ROOT="${CEREBRO_REMOTE_ROOT:-auto}"
MODE="daily"
BACKGROUND="true"

usage() {
  cat <<'EOF'
Usage:
  bash ops/run_pipeline_droplet.sh [options]

Options:
  --mode MODE        Pipeline mode: daily, intraday, build_only, or ui_only. Default: daily
  --remote-root PATH Remote app root. Default: auto-detect
  --foreground       Run in the foreground over SSH.
  --background       Start detached on the droplet. Default behavior.
  --help             Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo "Missing value for --mode" >&2; exit 1; }
      MODE="$2"
      shift 2
      ;;
    --foreground)
      BACKGROUND="false"
      shift
      ;;
    --remote-root)
      [[ $# -ge 2 ]] || { echo "Missing value for --remote-root" >&2; exit 1; }
      REMOTE_ROOT="$2"
      shift 2
      ;;
    --background)
      BACKGROUND="true"
      shift
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

if [[ "$MODE" != "daily" && "$MODE" != "intraday" && "$MODE" != "build_only" && "$MODE" != "ui_only" ]]; then
  echo "Unsupported mode: $MODE" >&2
  exit 1
fi

detect_remote_root() {
  if [[ "$REMOTE_ROOT" != "auto" ]]; then
    printf '%s\n' "$REMOTE_ROOT"
    return 0
  fi

  local detected
  detected="$(ssh "$HOST" '
primary="$(systemctl show -p WorkingDirectory --value cerebro 2>/dev/null || true)"
best_path=""
best_score=-1
for candidate in "$primary" /opt/catalyst /home/operator/.openclaw/workspace; do
  [[ -n "$candidate" && -d "$candidate" && -f "$candidate/run_daily_sec_catalyst.sh" ]] || continue
  score=0
  [[ -f "$candidate/evaluate_sec_outcomes.py" ]] && score=$((score + 1))
  [[ -f "$candidate/tune_scoring_config.py" ]] && score=$((score + 1))
  [[ -f "$candidate/rank_sec_catalysts.py" ]] && score=$((score + 1))
  [[ -f "$candidate/generate_seo_site.py" ]] && score=$((score + 1))
  if (( score > best_score )); then
    best_score=$score
    best_path="$candidate"
  fi
done
printf "%s" "$best_path"
' )"

  if [[ -z "$detected" ]]; then
    echo "Unable to detect remote pipeline root on $HOST" >&2
    exit 1
  fi
  printf '%s\n' "$detected"
}

REMOTE_ROOT="$(detect_remote_root)"
printf 'Using remote pipeline root: %s\n' "$REMOTE_ROOT"

if [[ "$BACKGROUND" == "true" ]]; then
  unit="cerebro-manual-${MODE}-$(date +%s)"
  ssh "$HOST" "systemd-run --unit '$unit' --property=WorkingDirectory='$REMOTE_ROOT' --setenv=CEREBRO_RUN_MODE='$MODE' '$REMOTE_ROOT/run_daily_sec_catalyst.sh'"
else
  ssh "$HOST" "cd '$REMOTE_ROOT' && env CEREBRO_RUN_MODE='$MODE' ./run_daily_sec_catalyst.sh"
fi
