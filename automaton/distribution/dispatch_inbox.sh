#!/usr/bin/env bash
# dispatch_inbox.sh — Drain the social_inbox/ produced by content_smith.
#
# Each file is named <slug>_<platform>.txt with the post content as plain text.
# This script:
#   1. Posts to Telegram (channel) + Discord (webhook) for every inbox file —
#      these channels accept any content via simple HTTP, no Playwright needed.
#   2. Calls platform-specific Playwright posters (post_to_twitter.cjs etc.)
#      with INBOX_TEXT_FILE env var set, so they post the inbox content
#      instead of generating from daily picks.
#   3. Archives processed files to social_inbox/sent/.
#
# The existing run_social_posts.sh STILL fires its daily-picks rotation
# afterwards — this script just drains the inbox first.
#
# Idempotent: re-running picks up only files that haven't moved to sent/.

set -uo pipefail
ROOT="/home/operator/.openclaw/workspace"
INBOX="$ROOT/social_inbox"
SENT="$INBOX/sent"
LOG="$ROOT/logs/dispatch_inbox.log"

mkdir -p "$SENT" "$ROOT/logs"
ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Load env once
if [[ -f "$ROOT/.sec_email_env" ]]; then
  set -a
  . "$ROOT/.sec_email_env"
  set +a
fi

post_telegram() {
  local content="$1"
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHANNEL:-}" ]]; then
    log "  telegram: skipped (no token/channel configured)"
    return 1
  fi
  # Truncate for Telegram (4096 char hard limit; we keep 3500 for safety)
  local trimmed
  trimmed=$(printf '%s' "$content" | head -c 3500)
  local url="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
  local payload
  payload=$(python3 -c "
import json, sys
print(json.dumps({
  'chat_id': sys.argv[1],
  'text': sys.argv[2],
  'parse_mode': 'Markdown',
  'disable_web_page_preview': False,
}))" "$TELEGRAM_CHANNEL" "$trimmed")
  local rc
  rc=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
       -d "$payload" --max-time 15 "$url")
  if [[ "$rc" =~ ^2 ]]; then
    log "  telegram: posted (HTTP $rc)"
    return 0
  fi
  log "  telegram: failed (HTTP $rc)"
  return 1
}

post_discord() {
  local content="$1"
  if [[ -z "${DISCORD_WEBHOOK_URL:-}" ]]; then
    log "  discord: skipped (no webhook configured)"
    return 1
  fi
  # Discord webhook content limit is 2000 chars
  local trimmed
  trimmed=$(printf '%s' "$content" | head -c 1900)
  local payload
  payload=$(python3 -c "
import json, sys
print(json.dumps({'content': sys.argv[1]}))" "$trimmed")
  local rc
  rc=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
       -d "$payload" --max-time 15 "$DISCORD_WEBHOOK_URL")
  if [[ "$rc" =~ ^2 ]]; then
    log "  discord: posted (HTTP $rc)"
    return 0
  fi
  log "  discord: failed (HTTP $rc)"
  return 1
}

post_mastodon() {
  local file="$1"
  if INBOX_TEXT_FILE="$file" python3 "$ROOT/post_to_mastodon.py" >> "$LOG" 2>&1; then
    return 0
  fi
  return 1
}

post_bluesky() {
  local file="$1"
  if INBOX_TEXT_FILE="$file" python3 "$ROOT/post_to_bluesky.py" >> "$LOG" 2>&1; then
    return 0
  fi
  return 1
}

post_playwright() {
  local platform="$1"
  local file="$2"
  local script
  case "$platform" in
    x|twitter)   script="post_to_twitter.cjs" ;;
    linkedin)    script="post_to_linkedin.cjs" ;;
    reddit)      script="post_to_reddit.cjs" ;;
    instagram)   script="post_to_instagram.cjs" ;;
    tiktok)      script="post_to_tiktok.cjs" ;;
    youtube)     script="post_to_youtube.cjs" ;;
    *) log "  playwright: unsupported platform $platform"; return 1 ;;
  esac

  if [[ ! -f "$ROOT/$script" ]]; then
    log "  playwright: $script not found"
    return 1
  fi

  # Find a node binary (WSL or Windows path). Same probe as run_social_posts.sh.
  local NODE_BIN=""
  for cand in node /usr/bin/node "/mnt/c/Program Files/nodejs/node.exe"; do
    if [[ -x "$cand" || $(command -v "$cand" 2>/dev/null) ]]; then
      NODE_BIN="$cand"; break
    fi
  done
  if [[ -z "$NODE_BIN" ]]; then
    log "  playwright: node not found"
    return 1
  fi

  # The post_to_*.cjs scripts honor INBOX_TEXT_FILE.
  # We wrap with xvfb-run when available so Playwright runs in HEADED mode
  # against an in-memory X display — defeats the headless detection that
  # X / LinkedIn / YouTube use to invalidate auth cookies even when they're
  # valid in the profile SQLite.
  log "  playwright: dispatching $platform via $script with INBOX_TEXT_FILE=$file"
  local cmd_prefix=""
  if command -v xvfb-run >/dev/null 2>&1 && [[ ! "$NODE_BIN" == *".exe" ]]; then
    cmd_prefix="xvfb-run -a --server-args=-screen 0 1280x900x24"
  fi
  if INBOX_TEXT_FILE="$file" $cmd_prefix "$NODE_BIN" "$ROOT/$script" >> "$LOG" 2>&1; then
    log "  playwright: $platform OK"
    return 0
  fi
  log "  playwright: $platform FAILED"
  return 1
}

# Main loop ----------------------------------------------------------------
log "=== dispatch_inbox START ==="

shopt -s nullglob
files=("$INBOX"/*.txt)
shopt -u nullglob

if [[ ${#files[@]} -eq 0 ]]; then
  log "inbox empty — exit 0"
  exit 0
fi

posted=0
failed=0

for f in "${files[@]}"; do
  base=$(basename "$f" .txt)
  # Filename pattern: <slug>_<platform>.txt — split on last underscore.
  platform="${base##*_}"
  slug="${base%_*}"
  log "--- $base  (slug=$slug platform=$platform) ---"

  content=$(cat "$f")
  if [[ -z "$content" ]]; then
    log "  empty file — skipping (will be archived anyway)"
    mv "$f" "$SENT/$(date -u +%Y%m%dT%H%M%S)_${base}.empty.txt"
    continue
  fi

  any_ok=0

  # Always mirror to Telegram + Discord (these never need Playwright).
  if post_telegram "$content"; then any_ok=1; fi
  if post_discord  "$content"; then any_ok=1; fi
  # Tier-3 webhook channels (Mastodon, Bluesky) — skip silently if creds absent.
  if post_mastodon "$f"; then any_ok=1; fi
  if post_bluesky  "$f"; then any_ok=1; fi

  # Then try the platform-specific Playwright path.
  case "$platform" in
    x|twitter|linkedin|reddit|instagram|tiktok|youtube)
      if post_playwright "$platform" "$f"; then any_ok=1; fi
      ;;
    telegram|discord)
      # already covered above
      ;;
    *)
      log "  unknown platform $platform — only mirrored to Telegram/Discord"
      ;;
  esac

  if [[ "$any_ok" == "1" ]]; then
    archived="$SENT/$(date -u +%Y%m%dT%H%M%S)_${base}.txt"
    mv "$f" "$archived"
    log "  archived → $(basename "$archived")"
    posted=$((posted + 1))
  else
    log "  ALL channels failed — leaving $f in inbox for retry"
    failed=$((failed + 1))
  fi
done

log "=== dispatch_inbox END  posted=$posted  failed=$failed ==="
