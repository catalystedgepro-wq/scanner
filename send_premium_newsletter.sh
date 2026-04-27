#!/usr/bin/env bash
# send_premium_newsletter.sh — Sends premium newsletter at 3:30 AM ET.
# Gated by .newsletter_premium_sent_STAMP so it only fires once per day.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$SCRIPT_DIR}"
cd "$ROOT"

if [[ -f "$ROOT/.sec_email_env" ]]; then
  set -a
  source "$ROOT/.sec_email_env"
  set +a
fi

STAMP="$(date +%F)"
PREMIUM_FLAG="$ROOT/.newsletter_premium_sent_${STAMP}"
PREMIUM_PARTIAL_FLAG="$ROOT/.newsletter_premium_partial_${STAMP}"

if [[ -f "$PREMIUM_FLAG" ]]; then
  echo "$(date '+%F %T %Z') premium newsletter already sent today — skipping"
  exit 0
fi

if [[ -z "${PREMIUM_EMAIL_TO:-}" ]]; then
  echo "$(date '+%F %T %Z') PREMIUM_EMAIL_TO not set — skipping premium send"
  exit 0
fi

if [[ -n "${SMTP_HOST:-}" && -n "${SMTP_PORT:-}" && -n "${SMTP_USER:-}" && -n "${SMTP_PASS:-}" ]]; then
  echo "$(date '+%F %T %Z') premium_email_send_start"
  set +e
  NEWSLETTER_MODE=1 PREMIUM_ONLY=1 /usr/bin/python3 "$ROOT/send_sec_catalyst_email.py"
  SEND_EXIT=$?
  set -e
  if [[ $SEND_EXIT -eq 0 ]]; then
    echo "$(date '+%F %T %Z') premium_email_send_ok"
    touch "$PREMIUM_FLAG"
    rm -f "$PREMIUM_PARTIAL_FLAG"
  elif [[ $SEND_EXIT -eq 2 ]]; then
    echo "$(date '+%F %T %Z') premium_email_send_partial_failure - check delivery_log_${STAMP}.txt"
    touch "$PREMIUM_PARTIAL_FLAG"
    exit 2
  else
    echo "$(date '+%F %T %Z') premium_email_send_FAILED exit=$SEND_EXIT - newsletter NOT sent"
    exit "$SEND_EXIT"
  fi
else
  echo "$(date '+%F %T %Z') premium send skipped: SMTP env vars not set"
fi
