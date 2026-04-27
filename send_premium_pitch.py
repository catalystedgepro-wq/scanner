#!/usr/bin/env python3
"""send_premium_pitch.py — Pitch premium paid tier to existing free subscribers.

Announces a $9/month premium tier with:
- Raw scanner CSV delivered daily
- Squeeze + dark pool signals
- Priority email before 3:30 AM ET

Gate: .premium_pitch_sent — one-time send.
"""
from __future__ import annotations
import json, os, smtplib, time, urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent
FLAG = ROOT / ".premium_pitch_sent"

SUBJECT = "Catalyst Edge Premium — Early Access at $9/month"

HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<h2 style="color:#00c853;">Catalyst Edge Premium — Now Available</h2>
<p>Hey,</p>
<p>You've been with us from the beginning. Before we open this to the public,
we're offering <strong>early access to Premium</strong> to our founding subscribers.</p>
<hr style="border:1px solid #eee;">
<h3>What's included for $9/month:</h3>
<ul>
<li>📊 <strong>Raw scanner CSV</strong> — full 1,600+ ticker dataset with gap scores,
volume ratios, and SEC filing links delivered to your inbox daily</li>
<li>🔒 <strong>Squeeze + dark pool signals</strong> — elevated short interest, unusual
block trades, and insider cluster alerts</li>
<li>⚡ <strong>Priority delivery before 3:30 AM ET</strong> — ahead of the free newsletter</li>
<li>📲 <strong>Telegram priority channel</strong> — alerts fire before the public channel</li>
<li>🤖 <strong>Unlimited AI agent access</strong> at catalystedge.agency — ask about any ticker</li>
</ul>
<hr style="border:1px solid #eee;">
<p>As a founding subscriber, you lock in the $9/month rate permanently —
even if we raise prices later.</p>
<p style="background:#f0fff4;padding:15px;border-left:4px solid #00c853;">
<strong>To sign up:</strong> Reply to this email with "PREMIUM" and we'll send
you the payment link directly.
</p>
<p>Thank you for being here from day one.</p>
<p>— Catalyst Edge Team<br>opensource@example.com</p>
</body></html>"""

PLAIN = """\
Catalyst Edge Premium — Now Available

You've been with us from the beginning. Early access offer for founding subscribers:

WHAT'S INCLUDED FOR $9/MONTH:
- Raw scanner CSV: full 1,600+ ticker dataset with gap scores, volume, SEC filing links
- Squeeze + dark pool signals: short interest, block trades, insider clusters
- Priority delivery before 3:30 AM ET
- Telegram priority channel — alerts before the public channel
- Unlimited AI agent access at catalystedge.agency

Founding subscribers lock in $9/month permanently.

TO SIGN UP: Reply to this email with "PREMIUM" and we'll send the payment link.

— Catalyst Edge Team
opensource@example.com
"""

def load_env():
    env = {}
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    for k, v in os.environ.items(): env.setdefault(k, v)
    return env

def get_subscribers(api_key, pub_id):
    req = urllib.request.Request(
        f"https://api.beehiiv.com/v2/publications/{pub_id}/subscriptions?limit=100&status=active",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return [s["email"] for s in data.get("data", []) if s.get("email")]

def send(host, port, user, passwd, sender, to, tls):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT; msg["From"] = f"Catalyst Edge <{sender}>"; msg["To"] = to
    msg.attach(MIMEText(PLAIN, "plain")); msg.attach(MIMEText(HTML, "html"))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if tls: s.starttls()
            s.login(user, passwd); s.sendmail(sender, to, msg.as_string())
        return True
    except Exception as e:
        print(f"  error: {e}"); return False

def main():
    if FLAG.exists(): print("premium_pitch: already sent"); return 0
    env = load_env()
    host = env.get("SMTP_HOST",""); port = int(env.get("SMTP_PORT",587))
    user = env.get("SMTP_USER",""); passwd = env.get("SMTP_PASS","").replace(" ","")
    sender = env.get("EMAIL_FROM", user)
    api_key = env.get("BEEHIIV_API_KEY",""); pub_id = env.get("BEEHIIV_PUB_ID","")
    tls = env.get("SMTP_USE_TLS","true").lower()=="true"
    if not all([host, user, passwd, api_key, pub_id]): print("missing credentials"); return 1
    emails = get_subscribers(api_key, pub_id)
    print(f"premium_pitch: {len(emails)} subscribers")
    sent = 0
    for email in emails:
        print(f"  → {email}")
        if send(host, port, user, passwd, sender, email, tls): sent += 1
        time.sleep(2)
    print(f"premium_pitch: {sent}/{len(emails)} sent")
    if sent > 0: FLAG.touch()
    return 0

if __name__ == "__main__": raise SystemExit(main())
