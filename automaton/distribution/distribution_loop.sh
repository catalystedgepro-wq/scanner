#!/usr/bin/env bash
# distribution_loop.sh — Distribution Automaton orchestrator.
#
# Fires daily at 11:00 UTC via cron. Mirrors the design of
# automaton/automaton_loop.sh: phased, idempotent, log-everything.
#
# Sequence each fire:
#   phase 1: content_smith --next            draft the next queued post
#   phase 2: content_publisher --next-drafted  publish the most recent draft
#   phase 3: social_rotator --latest         cross-post freshly published post
#   phase 4: conversion_tracker (Mondays only)
#   phase 5: Discord summary webhook (if DISCORD_WEBHOOK_URL set)
#
# State lives in pending_content.yaml — fully self-describing, no DB.

set -uo pipefail
ROOT="/home/operator/.openclaw/workspace"
DIST="$ROOT/automaton/distribution"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/distribution_loop.log"
LOCK="/tmp/distribution_loop.lock"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] distribution_loop: $*" | tee -a "$LOG"; }

exec 9>"$LOCK"
if ! flock -n 9; then
  log "SKIP: previous run still active"
  exit 0
fi

cd "$ROOT"
log "=== distribution_loop START ==="

PHASE_RESULTS=()

# Phase 1 — draft the next queued post
log "phase 1: content_smith --next"
if python3 "$DIST/content_smith.py" --next >> "$LOG" 2>&1; then
  log "  smith: drafted a post"
  PHASE_RESULTS+=("smith=ok")
else
  rc=$?
  if [[ $rc -eq 1 ]]; then
    log "  smith: queue empty"
    PHASE_RESULTS+=("smith=empty")
  else
    log "  smith: FAILED rc=$rc"
    PHASE_RESULTS+=("smith=fail")
  fi
fi

# Phase 2 — publish the most recent draft
log "phase 2: content_publisher --next-drafted"
if python3 "$DIST/content_publisher.py" --next-drafted >> "$LOG" 2>&1; then
  log "  publisher: published"
  PHASE_RESULTS+=("publisher=ok")
else
  rc=$?
  if [[ $rc -eq 1 ]]; then
    log "  publisher: nothing in drafted state"
    PHASE_RESULTS+=("publisher=none")
  else
    log "  publisher: FAILED rc=$rc"
    PHASE_RESULTS+=("publisher=fail")
  fi
fi

# Phase 3 — cross-post the freshly published post to social_inbox
log "phase 3: social_rotator --latest"
if python3 "$DIST/social_rotator.py" --latest >> "$LOG" 2>&1; then
  log "  rotator: social_inbox updated"
  PHASE_RESULTS+=("rotator=ok")
else
  rc=$?
  if [[ $rc -eq 1 ]]; then
    log "  rotator: nothing published yet"
    PHASE_RESULTS+=("rotator=none")
  else
    log "  rotator: FAILED rc=$rc"
    PHASE_RESULTS+=("rotator=fail")
  fi
fi

# Phase 3.5 — drain social_inbox immediately (was waiting until Mon-Fri 08:35 UTC,
# leaving weekend posts queued. Now every loop fire is fully end-to-end.)
log "phase 3.5: dispatch_inbox (drain webhook+playwright)"
if bash "$DIST/dispatch_inbox.sh" >> "$LOG" 2>&1; then
  log "  dispatch: inbox drained"
  PHASE_RESULTS+=("dispatch=ok")
else
  log "  dispatch: FAILED rc=$?"
  PHASE_RESULTS+=("dispatch=fail")
fi

# Phase 4 — weekly conversion summary (Mondays only)
DOW=$(date -u +%u)  # 1 = Monday
if [[ "$DOW" == "1" ]]; then
  log "phase 4: conversion_tracker (Monday)"
  if python3 "$DIST/conversion_tracker.py" --days 7 >> "$LOG" 2>&1; then
    log "  tracker: leaderboard written"
    PHASE_RESULTS+=("tracker=ok")
  else
    log "  tracker: FAILED"
    PHASE_RESULTS+=("tracker=fail")
  fi
else
  log "phase 4: skipping conversion_tracker (DOW=$DOW != Mon)"
fi

# Phase 5 — Discord summary (if webhook configured)
SUMMARY="distribution_loop fired $(ts) — $(IFS=,; echo "${PHASE_RESULTS[*]}")"
log "$SUMMARY"

if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
  PAYLOAD=$(printf '{"content":"Distribution Automaton: %s"}' "$(echo "$SUMMARY" | sed 's/"/\\"/g')")
  if curl -fsS -X POST -H "Content-Type: application/json" \
       -d "$PAYLOAD" "$DISCORD_WEBHOOK_URL" >> "$LOG" 2>&1; then
    log "  discord: summary posted"
  else
    log "  discord: post failed"
  fi
else
  log "  discord: DISCORD_WEBHOOK_URL not set — skipping"
fi

log "=== distribution_loop END ==="
