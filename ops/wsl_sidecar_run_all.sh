#!/usr/bin/env bash
# wsl_sidecar_run_all.sh
#
# Runs EVERY build_*.py on WSL (residential IP, no Cloudflare blocks), then
# rsyncs the resulting CSVs to the droplet. Bypasses the DO IP flagging that
# kills ~40% of spokes when run on /opt/catalyst directly.
#
# Architecture:
#   WSL (residential IP)        Droplet (/opt/catalyst)
#   ──────────────────          ───────────────────────
#   run all build_*.py ────►    rsync *.csv ────► scanner/API consumes
#
# Schedule: WSL cron fires at 2:30 AM ET so CSVs land before the droplet's
# 3:00 AM pipeline rebuilds convergence.
set -uo pipefail  # NOTE: no -e — we want to continue on spoke failures

ROOT="/home/operator/.openclaw/workspace"
LOG="$ROOT/logs/wsl_sidecar.log"
LOG_DIR="$(dirname "$LOG")"
mkdir -p "$LOG_DIR"
LOCK="/tmp/wsl_sidecar.lock"
DROPLET="root@67.205.148.181"
DROPLET_DIR="/opt/catalyst"

PARALLEL="${PARALLEL:-8}"     # concurrent spoke runs
PER_SPOKE_TIMEOUT="${PER_SPOKE_TIMEOUT:-60}"  # seconds per spoke

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

# Prevent overlapping runs
exec 9>"$LOCK"
if ! flock -n 9; then
  log "SKIP: previous run still active"
  exit 0
fi

cd "$ROOT"
log "=== wsl_sidecar START (parallel=$PARALLEL timeout=${PER_SPOKE_TIMEOUT}s) ==="

# Collect all build_*.py scripts
mapfile -t SPOKES < <(ls /home/operator/.openclaw/workspace/build_*.py 2>/dev/null | sort)
TOTAL=${#SPOKES[@]}
log "found $TOTAL spokes"

# Run spokes in parallel using xargs -P
OK_COUNT=0
FAIL_COUNT=0
TIMEOUT_COUNT=0

run_one() {
  local script="$1"
  local name="$(basename "$script" .py)"
  local out
  out=$(timeout "$PER_SPOKE_TIMEOUT" /usr/bin/python3 "$script" 2>&1 | tail -1)
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "OK $name $out"
  elif [[ $rc -eq 124 ]]; then
    echo "TIMEOUT $name"
  else
    echo "FAIL rc=$rc $name ${out:0:120}"
  fi
}
export -f run_one
export PER_SPOKE_TIMEOUT

RESULT_FILE="$LOG_DIR/sidecar_last_results.txt"
: > "$RESULT_FILE"

printf '%s\n' "${SPOKES[@]}" | xargs -I {} -P "$PARALLEL" bash -c 'run_one "$@"' _ {} >> "$RESULT_FILE" 2>&1

OK_COUNT=$(grep -c "^OK " "$RESULT_FILE" || true)
FAIL_COUNT=$(grep -c "^FAIL " "$RESULT_FILE" || true)
TIMEOUT_COUNT=$(grep -c "^TIMEOUT " "$RESULT_FILE" || true)
log "spokes ran: ok=$OK_COUNT fail=$FAIL_COUNT timeout=$TIMEOUT_COUNT total=$TOTAL"

# Rsync fresh CSVs (modified in last 24h) to droplet.
# Use explicit --include with file-modified filter via find.
log "rsync fresh CSVs to droplet..."
FRESH_LIST="/tmp/fresh_csvs.list"
find "$ROOT" -maxdepth 1 -name '*.csv' -mtime -1 -type f -printf '%P\n' 2>/dev/null > "$FRESH_LIST"
FRESH_COUNT=$(wc -l < "$FRESH_LIST")
log "  $FRESH_COUNT fresh CSVs to push"

if [[ $FRESH_COUNT -gt 0 ]]; then
  # rsync with explicit file list
  rsync -az --timeout=60 --files-from="$FRESH_LIST" \
    -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15" \
    "$ROOT/" "$DROPLET:$DROPLET_DIR/" >> "$LOG" 2>&1
  RSYNC_RC=$?
  log "  rsync exit=$RSYNC_RC"
fi

# Publish health report to droplet docs/data/
cat > "$ROOT/docs/data/wsl_sidecar_status.json" <<JSON
{
  "last_run_utc": "$(ts)",
  "total_spokes": $TOTAL,
  "ok": $OK_COUNT,
  "failed": $FAIL_COUNT,
  "timed_out": $TIMEOUT_COUNT,
  "fresh_csvs_pushed": $FRESH_COUNT,
  "architecture": "WSL-sidecar: residential IP fetches, rsync to droplet"
}
JSON

scp -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
  "$ROOT/docs/data/wsl_sidecar_status.json" \
  "$DROPLET:$DROPLET_DIR/docs/data/wsl_sidecar_status.json" >> "$LOG" 2>&1

log "=== wsl_sidecar END (ok=$OK_COUNT/$TOTAL, pushed=$FRESH_COUNT) ==="
