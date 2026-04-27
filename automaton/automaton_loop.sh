#!/usr/bin/env bash
# automaton_loop.sh — Protocol Automaton orchestrator.
#
# Fires biweekly (Sunday 14:00 UTC). Each fire:
#   1. Pops the next eligible queued spoke from automaton/pending_spokes.yaml
#   2. Runs spoke_smith → generates build_<name>.py and stubs parse()
#   3. Posts a notification telling the operator (or a follow-up agent) that
#      a new spoke is in_progress and needs its parse() filled in
#   4. On the NEXT fire (two weeks later), runs spoke_audit on whatever's
#      in_progress to graduate or fail it
#   5. tune_scoring_config.py picks up probationary spokes weekly and
#      graduates them to live after 4 weeks of positive contribution
#
# State lives in pending_spokes.yaml — fully self-describing, no DB.

set -uo pipefail
ROOT="/home/operator/.openclaw/workspace"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/automaton_loop.log"
LOCK="/tmp/automaton_loop.lock"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Prevent overlap
exec 9>"$LOCK"
if ! flock -n 9; then
  log "SKIP: previous run still active"
  exit 0
fi

cd "$ROOT"
log "=== automaton_loop START ==="

# Phase 1: audit anything currently in_progress AND probationary
log "phase 1: spoke_audit --all-in-progress"
if python3 "$ROOT/automaton/spoke_audit.py" --all-in-progress >> "$LOG" 2>&1; then
  log "  audit phase: pass"
else
  log "  audit phase: at least one spoke FAILED (kept in_progress for review)"
fi

# Phase 2: ship the next queued spoke (generates the build_*.py with stub parse())
log "phase 2: spoke_smith --next"
if python3 "$ROOT/automaton/spoke_smith.py" --next >> "$LOG" 2>&1; then
  log "  smith phase: a new spoke was generated"
  SMITH_OK=1
else
  rc=$?
  SMITH_OK=0
  if [[ $rc -eq 1 ]]; then
    log "  smith phase: queue empty — no spoke shipped"
  else
    log "  smith phase: FAILED rc=$rc"
  fi
fi

# Phase 2b: parser_writer auto-completes parse() on whatever the smith just generated.
# This closes the last manual loop — the spoke is fully populated before the
# next fire's audit phase reaches it.
if [[ "$SMITH_OK" == "1" ]]; then
  log "phase 2b: spoke_parser_writer --all-in-progress"
  if python3 "$ROOT/automaton/spoke_parser_writer.py" --all-in-progress >> "$LOG" 2>&1; then
    log "  parser_writer phase: parse() filled in"
  else
    rc=$?
    log "  parser_writer phase: rc=$rc (some spokes left with TODO blocks for next cycle)"
  fi
fi

# Phase 3: notify operator via Discord webhook (read from .sec_email_env)
WEBHOOK=""
if [[ -f "$ROOT/.sec_email_env" ]]; then
  WEBHOOK=$(grep -E '^DISCORD_WEBHOOK_URL=' "$ROOT/.sec_email_env" | cut -d= -f2- | tr -d '"' || true)
fi
if [[ -n "$WEBHOOK" ]]; then
  RECENT=$(tail -30 "$LOG" | grep -E "(generated|PASS|FAIL|smith phase|audit phase)" | tail -10)
  PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'content': '🤖 **Protocol Automaton** fired '+sys.argv[1]+'\n\`\`\`\n'+sys.argv[2]+'\n\`\`\`'}))" "$(ts)" "$RECENT")
  curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$WEBHOOK" > /dev/null 2>&1 || true
  log "  notification posted to Discord"
fi

log "=== automaton_loop END ==="
