#!/usr/bin/env python3
"""send_newsletter_directories.py — Submit Catalyst Edge to newsletter discovery directories.

These are free listings that drive organic discovery. Gate per directory.
"""
from __future__ import annotations
import hashlib, os, smtplib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent

# Newsletter directories that accept submissions via email
# (ones with web forms only are excluded — those need manual one-time setup)
DIRECTORIES = [
    ("Newsletter Stack", "submit@newsletterstack.com"),
    ("Inbox Reads",      "hello@inboxreads.co"),
    ("Letterlist",       "add@letterlist.com"),
    ("Wellput",          "submit@wellput.co"),
    ("The Sample",       "publishers@thesampl.com"),
]

SUBJECT = "Newsletter Submission — Catalyst Edge (Free Daily SEC Trading Alerts)"

HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<p>Hi,</p>
<p>I'd like to submit <strong>Catalyst Edge</strong> for listing in your newsletter directory.</p>
<p><strong>Newsletter details:</strong></p>
<ul>
<li><strong>Name:</strong> Catalyst Edge</li>
<li><strong>URL:</strong> <a href="https://catalystedge.agency">catalystedge.agency</a></li>
<li><strong>Category:</strong> Finance / Trading / Investing</li>
<li><strong>Frequency:</strong> Daily (weekdays)</li>
<li><strong>Description:</strong> Free daily pre-market intelligence for active traders.
We scan 300+ SEC EDGAR filings and 1,600+ tickers every morning before the market opens,
then deliver the top gap plays, insider filing alerts, and squeeze candidates before 4 AM ET.
Completely free, fully automated, zero fluff.</li>
<li><strong>Audience:</strong> Active retail traders — day traders and swing traders</li>
<li><strong>Open rate:</strong> 37%+</li>
<li><strong>Platform:</strong> Beehiiv</li>
</ul>
<p>Please let me know if you need any additional information or assets.</p>
<p>Best,<br>Catalyst Edge Team<br>opensource@example.com<br>
<a href="https://catalystedge.agency">catalystedge.agency</a></p>
</body></html>"""

PLAIN = """\
Hi,

I'd like to submit Catalyst Edge for listing in your newsletter directory.

Name: Catalyst Edge
URL: catalystedge.agency
Category: Finance / Trading / Investing
Frequency: Daily (weekdays)
Description: Free daily pre-market intelligence for active traders. We scan 300+ SEC EDGAR
filings and 1,600+ tickers every morning, delivering top gap plays, insider filing alerts,
and squeeze candidates before 4 AM ET. Free, automated, zero fluff.
Audience: Active retail day/swing traders
Open rate: 37%+
Platform: Beehiiv

Let me know if you need anything else.

Best,
Catalyst Edge Team
opensource@example.com
catalystedge.agency
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

def sent_flag(email): return ROOT / f".dir_submit_{hashlib.md5(email.encode()).hexdigest()[:8]}"
def already_sent(email): return sent_flag(email).exists()
def mark_sent(email): sent_flag(email).touch()

def send(host, port, user, passwd, sender, to, tls):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT; msg["From"] = f"Catalyst Edge <{sender}>"; msg["To"] = to
    msg.attach(MIMEText(PLAIN, "plain"))
    msg.attach(MIMEText(HTML, "html"))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if tls: s.starttls()
            s.login(user, passwd); s.sendmail(sender, to, msg.as_string())
        return True
    except Exception as e:
        print(f"  error: {e}"); return False

def main():
    env = load_env()
    host = env.get("SMTP_HOST",""); port = int(env.get("SMTP_PORT",587))
    user = env.get("SMTP_USER",""); passwd = env.get("SMTP_PASS","").replace(" ","")
    sender = env.get("EMAIL_FROM", user); tls = env.get("SMTP_USE_TLS","true").lower()=="true"
    if not all([host, user, passwd]): print("SMTP not configured"); return 1
    sent = 0
    for name, email in DIRECTORIES:
        if already_sent(email): print(f"  already submitted → {name}"); continue
        print(f"  → {name} <{email}>")
        if send(host, port, user, passwd, sender, email, tls):
            mark_sent(email); sent += 1; print("    ✅ sent")
        else: print("    ❌ failed")
        time.sleep(3)
    print(f"send_newsletter_directories: {sent}/{len(DIRECTORIES)} submitted")
    return 0

if __name__ == "__main__": raise SystemExit(main())
