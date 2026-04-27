#!/usr/bin/env bash
# send_free_newsletter.sh - Sends the free/public newsletter once the morning build is fresh.
# Gated by .newsletter_free_sent_STAMP so it only fires once per day.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$SCRIPT_DIR}"
cd "$ROOT"

if [[ -f "$ROOT/.sec_email_env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.sec_email_env"
  set +a
fi

STAMP="$(date +%F)"
FREE_FLAG="$ROOT/.newsletter_free_sent_${STAMP}"
LEGACY_FLAG="$ROOT/.newsletter_sent_${STAMP}"

if [[ -f "$FREE_FLAG" ]]; then
  echo "$(date '+%F %T %Z') free newsletter already sent today - skipping"
  exit 0
fi

SMTP_OK=0
BEEHIIV_OK=0
PARTIAL_OK=0
PARTIAL_FLAG="$ROOT/.newsletter_free_partial_${STAMP}"

if [[ -n "${SMTP_HOST:-}" && -n "${SMTP_PORT:-}" && -n "${SMTP_USER:-}" && -n "${SMTP_PASS:-}" ]]; then
  echo "$(date '+%F %T %Z') free_email_send_start"
  set +e
  NEWSLETTER_MODE=1 FREE_ONLY=1 /usr/bin/python3 "$ROOT/send_sec_catalyst_email.py"
  SEND_EXIT=$?
  set -e
  if [[ $SEND_EXIT -eq 0 ]]; then
    echo "$(date '+%F %T %Z') free_email_send_ok"
    SMTP_OK=1
  elif [[ $SEND_EXIT -eq 2 ]]; then
    echo "$(date '+%F %T %Z') free_email_send_partial_failure - check delivery_log_${STAMP}.txt"
    PARTIAL_OK=1
  else
    echo "$(date '+%F %T %Z') free_email_send_FAILED exit=$SEND_EXIT"
  fi
else
  echo "$(date '+%F %T %Z') free_email_send_skipped: SMTP env vars not fully set"
fi

if [[ -d "/mnt/c/playwright_tools/beehiiv_profile" ]]; then
  echo "$(date '+%F %T %Z') beehiiv_post_start"
  set +e
  /usr/bin/node "$ROOT/post_to_beehiiv.cjs"
  BEEHIIV_EXIT=$?
  set -e
  if [[ $BEEHIIV_EXIT -eq 0 ]]; then
    echo "$(date '+%F %T %Z') beehiiv_post_ok"
    BEEHIIV_OK=1
  else
    echo "$(date '+%F %T %Z') beehiiv_post_failed exit=$BEEHIIV_EXIT"
  fi
fi

/usr/bin/python3 "$ROOT/cleanup_beehiiv_posts.py" || echo "$(date '+%F %T') beehiiv_cleanup skipped"

if [[ $SMTP_OK -eq 1 || $BEEHIIV_OK -eq 1 ]]; then
  if [[ $PARTIAL_OK -eq 1 ]]; then
    touch "$PARTIAL_FLAG"
    echo "$(date '+%F %T %Z') free_delivery_partial - success path incomplete"
    exit 2
  fi
  touch "$FREE_FLAG"
  touch "$LEGACY_FLAG"
  rm -f "$PARTIAL_FLAG"
  exit 0
fi

echo "$(date '+%F %T %Z') free_delivery_failed - no free newsletter transport succeeded"
exit 1
