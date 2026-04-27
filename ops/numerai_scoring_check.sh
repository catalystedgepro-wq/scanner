#!/usr/bin/env bash
# numerai_scoring_check.sh — fires once on 2026-04-30 (Numerai Round 1253 scoring start).
# Verifies submission still active, queues next-round submission, emails status.
set -euo pipefail

ROOT="/home/operator/.openclaw/workspace"
LOG="$ROOT/.numerai_scoring_check.log"
MARKER="$ROOT/.numerai_round1253_checked"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# Idempotency — only fire once even if cron re-triggers
if [[ -f "$MARKER" ]]; then
  echo "[$(ts)] already checked, exiting" >> "$LOG"
  exit 0
fi

cd "$ROOT"

{
  echo "=== [$(ts)] Numerai Round 1253 scoring window opens today ==="

  # 1. Verify last submission is still in droplet status JSON
  if [[ -f "$ROOT/docs/data/numerai_submit_status.json" ]]; then
    python3 -c "
import json, sys
with open('$ROOT/docs/data/numerai_submit_status.json') as f:
    d = json.load(f)
print(f\"  prior_round={d.get('round')} submission_id={d.get('submission_id','')[:12]}... rows={d.get('rows_submitted')}\")
"
  fi

  # 2. Re-build + re-submit for the new round
  if [[ -f "$ROOT/build_numerai_signals.py" ]]; then
    python3 "$ROOT/build_numerai_signals.py" || echo "  build_numerai_signals failed"
  fi
  if [[ -f "$ROOT/submit_numerai.py" ]]; then
    python3 "$ROOT/submit_numerai.py" || echo "  submit_numerai failed"
  fi

  # 3. Email the user with a one-line status
  if [[ -f "$ROOT/.sec_email_env" ]]; then
    python3 - <<'PY'
import json, os, smtplib
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
env = ROOT / ".sec_email_env"
if env.exists():
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

status = {}
sf = ROOT / "docs/data/numerai_submit_status.json"
if sf.exists():
    status = json.loads(sf.read_text())

body = (
    f"Numerai Round {status.get('round','?')} scoring opens today.\n\n"
    f"  Submission ID: {status.get('submission_id','?')}\n"
    f"  Model: {status.get('model_name','?')}\n"
    f"  Rows: {status.get('rows_submitted','?')}\n"
    f"  Scoring resolves: {status.get('scoring_resolves','?')}\n\n"
    f"Leaderboard: {status.get('leaderboard_url','https://signals.numer.ai/')}\n"
)

host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
user = os.environ.get("EMAIL_SMTP_USER", "")
pwd = os.environ.get("EMAIL_SMTP_PASS", "")
to = os.environ.get("EMAIL_TO", user)
if user and pwd:
    msg = MIMEText(body)
    msg["Subject"] = f"[Catalyst Edge] Numerai Round {status.get('round','?')} scoring open"
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    print(f"  emailed {to}")
PY
  fi

  touch "$MARKER"
  echo "=== [$(ts)] check complete, marker written ==="
} >> "$LOG" 2>&1
