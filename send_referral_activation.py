#!/usr/bin/env python3
"""send_referral_activation.py — Launch referral program to existing subscribers.

Sends a dedicated referral program announcement to all current subscribers.
Gate: .referral_activation_sent — fires once, never repeats.
"""
from __future__ import annotations
import os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent
FLAG = ROOT / ".referral_activation_sent"

SUBJECT = "You can now earn free Premium access — here's how"

HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<p>You've been with Catalyst Edge since the beginning.</p>
<p>We're launching a <strong>referral program</strong> — and founding subscribers like you get the best deal.</p>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0">
<h2 style="color:#1a1a1a;font-size:1.2em;">How to earn free Premium access:</h2>
<ul>
<li><strong>Refer 3 traders</strong> → 1 month of Premium free ($9 value)</li>
<li><strong>Refer 10 traders</strong> → 6 months of Premium free ($54 value)</li>
<li><strong>Refer 25 traders</strong> → Lifetime Premium free + your name in the daily scanner</li>
</ul>
<p>Premium includes the raw scanner CSV (1,600+ tickers), dark pool signals,
squeeze alerts, and priority 3:30 AM delivery.</p>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0">
<p><strong>Your referral link:</strong><br>
<a href="https://catalystedge.agency?utm_source=referral">https://catalystedge.agency?utm_source=referral</a></p>
<p>Share it with any trader you know — if they subscribe, it counts.
Forward this email, drop it in a Discord, post it in a trading group.
Every referral moves you closer to free Premium.</p>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0">
<p><strong>The easiest share:</strong><br>
<em>"This free newsletter scans 300+ SEC filings every morning and sends the top gap plays before 4 AM.
Been using it, it's legit: <a href="https://catalystedge.agency">catalystedge.agency</a>"</em></p>
<p>— Catalyst Edge Team<br>opensource@example.com</p>
</body></html>"""

PLAIN = """\
You've been with Catalyst Edge since the beginning.

We're launching a referral program — founding subscribers get the best deal.

HOW TO EARN FREE PREMIUM ACCESS:
- Refer 3 traders → 1 month free ($9 value)
- Refer 10 traders → 6 months free ($54 value)
- Refer 25 traders → Lifetime free + your name in the daily scanner

Premium = raw scanner CSV (1,600+ tickers), dark pool signals, squeeze alerts, 3:30 AM delivery.

YOUR REFERRAL LINK:
https://catalystedge.agency?utm_source=referral

Share it in any trading group, Discord, or with friends. Every subscribe counts.

THE EASIEST SHARE:
"This free newsletter scans 300+ SEC filings every morning and sends the top gap plays
before 4 AM. Been using it, it's legit: catalystedge.agency"

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

def main():
    if FLAG.exists(): print("referral activation already sent"); return 0
    env = load_env()
    host   = env.get("SMTP_HOST",""); port = int(env.get("SMTP_PORT",587))
    user   = env.get("SMTP_USER",""); passwd = env.get("SMTP_PASS","").replace(" ","")
    sender = env.get("EMAIL_FROM", user); tls = env.get("SMTP_USE_TLS","true").lower()=="true"
    # Send to all known subscriber addresses
    email_to_raw = env.get("EMAIL_TO","")
    recipients = [e.strip() for e in email_to_raw.split(",") if e.strip()]
    if not recipients:
        print("No EMAIL_TO configured"); return 1
    if not all([host, user, passwd]):
        print("SMTP not configured"); return 1

    sent = 0
    for to in recipients:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = SUBJECT
        msg["From"] = f"Catalyst Edge <{sender}>"; msg["To"] = to
        msg.attach(MIMEText(PLAIN, "plain"))
        msg.attach(MIMEText(HTML, "html"))
        try:
            with smtplib.SMTP(host, port, timeout=30) as s:
                if tls: s.starttls()
                s.login(user, passwd); s.sendmail(sender, to, msg.as_string())
            sent += 1; print(f"  ✅ {to}")
        except Exception as e:
            print(f"  ❌ {to}: {e}")

    if sent > 0: FLAG.touch()
    print(f"send_referral_activation: {sent}/{len(recipients)} sent")
    return 0

if __name__ == "__main__": raise SystemExit(main())
