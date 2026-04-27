#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${CEREBRO_DEPLOY_HOST:-cerebro}"
REMOTE_ROOT="${CEREBRO_REMOTE_ROOT:-auto}"
REMOTE_CRON_FILE="/etc/cron.d/cerebro-sympathy-watch"
CRON_SCHEDULE="${CEREBRO_SYMPATHY_CRON:-*/5 * * * 1-5}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

detect_remote_root() {
  if [[ "$REMOTE_ROOT" != "auto" ]]; then
    printf '%s\n' "$REMOTE_ROOT"
    return 0
  fi

  ssh "$HOST" '
primary="$(systemctl show -p WorkingDirectory --value cerebro 2>/dev/null || true)"
best_path=""
best_score=-1
for candidate in /opt/catalyst "$primary" /home/operator/.openclaw/workspace; do
  [[ -n "$candidate" && -d "$candidate" && -f "$candidate/build_sympathy_logger.py" ]] || continue
  score=0
  [[ -f "$candidate/sympathy_events.csv" ]] && score=$((score + 3))
  [[ -f "$candidate/sec_catalyst_ranked.csv" ]] && score=$((score + 2))
  [[ -f "$candidate/ops/check_sympathy_burst.py" ]] && score=$((score + 1))
  if (( score > best_score )); then
    best_score=$score
    best_path="$candidate"
  fi
done
printf "%s" "$best_path"
'
}

require_cmd ssh
require_cmd rsync

REMOTE_ROOT="$(detect_remote_root)"
if [[ -z "$REMOTE_ROOT" ]]; then
  echo "Unable to detect remote sympathy monitor root on $HOST" >&2
  exit 1
fi

log "Syncing sympathy watch scripts to $HOST:$REMOTE_ROOT"
ssh "$HOST" "mkdir -p '$REMOTE_ROOT/ops' '$REMOTE_ROOT/logs'"
rsync -av "$WORKSPACE_ROOT/build_sympathy_logger.py" "$HOST:$REMOTE_ROOT/build_sympathy_logger.py"
rsync -av "$WORKSPACE_ROOT/ops/check_sympathy_burst.py" "$HOST:$REMOTE_ROOT/ops/check_sympathy_burst.py"
rsync -av "$WORKSPACE_ROOT/ops/sympathy_burst_watch.sh" "$HOST:$REMOTE_ROOT/ops/sympathy_burst_watch.sh"
ssh "$HOST" "chmod +x '$REMOTE_ROOT/ops/sympathy_burst_watch.sh'"

log "Installing dedicated sympathy watch cron at $REMOTE_CRON_FILE"
ssh "$HOST" "cat > '$REMOTE_CRON_FILE' <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=\"\"
$CRON_SCHEDULE root cd '$REMOTE_ROOT' && /bin/bash '$REMOTE_ROOT/ops/sympathy_burst_watch.sh' >> '$REMOTE_ROOT/logs/sympathy_burst_watch.log' 2>&1
EOF"
ssh "$HOST" "chmod 644 '$REMOTE_CRON_FILE'"

log "Running one foreground verification pass"
ssh "$HOST" "cd '$REMOTE_ROOT' && /bin/bash '$REMOTE_ROOT/ops/sympathy_burst_watch.sh' || true"

log "Installed sympathy watch cron"
ssh "$HOST" "cat '$REMOTE_CRON_FILE'"
