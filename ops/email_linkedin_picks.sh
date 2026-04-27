#!/usr/bin/env bash
# email_linkedin_picks.sh — Mon 8:07 AM EDT cron.
# Pulls the freshest 2 LinkedIn posts from the live JSON feed and emails them.
# Rotation: each week pick the 2 posts whose ids hash to (week_of_year mod 5).
set -euo pipefail

ROOT="/home/operator/.openclaw/workspace"
LOG="$ROOT/.linkedin_email.log"

cd "$ROOT"
ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

{
  echo "=== [$(ts)] linkedin email picks ==="

  if [[ -f "$ROOT/build_linkedin_posts.py" ]]; then
    /usr/bin/python3 "$ROOT/build_linkedin_posts.py" || echo "  build_linkedin_posts: failed (using droplet version)"
  fi

  /usr/bin/python3 - <<'PY'
import json, os, smtplib, time, urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")

# Load env
env_file = ROOT / ".sec_email_env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Prefer droplet-fresh JSON (autonomous_loop refreshed ~every 2h), fall back local
posts = []
try:
    with urllib.request.urlopen(
        "https://catalystedgescanner.com/data/linkedin_posts.json", timeout=10
    ) as r:
        posts = json.loads(r.read()).get("posts", [])
except Exception:
    f = ROOT / "docs/data/linkedin_posts.json"
    if f.exists():
        posts = json.loads(f.read_text()).get("posts", [])

if not posts:
    print("  no posts available, exiting")
    raise SystemExit(0)

# Rotation: ISO week number → starting offset, pick 2 consecutive
week = int(time.strftime("%V"))
n = len(posts)
i0 = week % n
i1 = (week + 1) % n
picks = [posts[i0], posts[i1]]

# Build HTML email
parts = []
for p in picks:
    body_html = p["body"].replace("\n", "<br>")
    tags = " ".join(p.get("hashtags", []))
    parts.append(f"""
<div style="background:#f5f7fa;border:1px solid #d1d9e6;border-radius:8px;padding:18px;margin-bottom:18px">
  <div style="font-size:11px;color:#0a66c2;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">{p.get('angle','')}</div>
  <h3 style="margin:0 0 10px;color:#0b0f17;font-size:16px">{p.get('title','')}</h3>
  <div style="background:#fff;border-radius:6px;padding:14px;font-size:14px;line-height:1.5;color:#1a1a1a;white-space:normal">{body_html}</div>
  <div style="margin-top:10px;font-size:13px;color:#0a66c2">{tags}</div>
  <div style="margin-top:8px;font-size:12px;color:#65788a">{p.get('char_count',0)} chars · ready to paste</div>
</div>""")

html = f"""<!doctype html><html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f0f2f5;padding:20px;margin:0">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
  <div style="background:#0a66c2;color:#fff;padding:18px 22px">
    <h2 style="margin:0;font-size:18px">📅 This Week's LinkedIn Picks</h2>
    <div style="font-size:13px;opacity:0.85;margin-top:4px">Catalyst Edge · ISO week {week} · {len(picks)} of {n} posts</div>
  </div>
  <div style="padding:22px">
    <p style="font-size:14px;color:#65788a;margin:0 0 18px">Copy → paste → post. Each one pulls live numbers from the scanner.</p>
    {''.join(parts)}
    <p style="font-size:13px;color:#65788a;margin:18px 0 0">All 5 posts available at <a href="https://catalystedgescanner.com/linkedin/?unlock=REPLACE_WITH_YOUR_ADMIN_TOKEN" style="color:#0a66c2">catalystedgescanner.com/linkedin/</a> (admin bookmark).</p>
  </div>
</div>
</body></html>"""

text_parts = []
for p in picks:
    text_parts.append(f"=== {p.get('title','')} ===\n{p.get('full_text','')}\n")
text = "This Week's LinkedIn Picks (Catalyst Edge)\n\n" + "\n".join(text_parts)

host = os.environ.get("SMTP_HOST") or os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
port = int(os.environ.get("SMTP_PORT") or os.environ.get("EMAIL_SMTP_PORT", "587"))
user = os.environ.get("SMTP_USER") or os.environ.get("EMAIL_SMTP_USER", "")
pwd  = os.environ.get("SMTP_PASS") or os.environ.get("EMAIL_SMTP_PASS", "")
sender = os.environ.get("EMAIL_FROM", user)
admins = os.environ.get("ADMIN_EMAILS", "").strip()
to = (admins.split(",")[0].strip() if admins else "") or "opensource@example.com"

if not (user and pwd):
    print("  no SMTP creds, skipping send")
    raise SystemExit(0)

msg = MIMEMultipart("alternative")
msg["Subject"] = f"📅 LinkedIn picks · week {week} · {picks[0].get('title','')[:40]}"
msg["From"] = sender
msg["To"] = to
msg.attach(MIMEText(text, "plain", "utf-8"))
msg.attach(MIMEText(html, "html", "utf-8"))

with smtplib.SMTP(host, port, timeout=20) as s:
    s.starttls()
    s.login(user, pwd)
    s.send_message(msg)

print(f"  emailed to={to} picks={[p['id'] for p in picks]}")
PY

  echo "=== [$(ts)] done ==="
} >> "$LOG" 2>&1
