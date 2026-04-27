#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${CEREBRO_DEPLOY_HOST:-cerebro}"
REMOTE_ROOT="${CEREBRO_REMOTE_ROOT:-/opt/catalyst}"
REMOTE_CRON_PATH="$REMOTE_ROOT/ops/scanner_refresh.crontab.example"
REMOTE_SYSTEM_CRON="/etc/cron.d/cerebro-scanner"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

require_cmd ssh
require_cmd rsync

log "Syncing scanner cron template to $HOST"
ssh "$HOST" "mkdir -p '$REMOTE_ROOT/ops'"
rsync -av "$WORKSPACE_ROOT/ops/scanner_refresh.crontab.example" "$HOST:$REMOTE_CRON_PATH"

log "Backing up current cron surfaces on $HOST"
ssh "$HOST" "\
  if [[ -f '$REMOTE_SYSTEM_CRON' ]]; then \
    cp '$REMOTE_SYSTEM_CRON' '$REMOTE_ROOT/cerebro_scanner_cron_backup_$(date +%F_%H%M%S).txt'; \
  fi; \
  (crontab -l 2>/dev/null || true) > '$REMOTE_ROOT/root_crontab_backup_$(date +%F_%H%M%S).txt'"

log "Installing /etc/cron.d scanner contract from $REMOTE_CRON_PATH"
ssh "$HOST" "cp '$REMOTE_CRON_PATH' '$REMOTE_SYSTEM_CRON' && chmod 0644 '$REMOTE_SYSTEM_CRON'"

log "Installed scanner cron contract"
ssh "$HOST" "cat '$REMOTE_SYSTEM_CRON'"
