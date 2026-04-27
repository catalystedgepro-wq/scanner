#!/usr/bin/env python3
"""send_trader_outreach.py — Email individual traders discovered via YouTube/social search.

Reads trader_contacts.csv, sends personalized pitch to each, gates on .trader_outreach_{hash}.
"""
from __future__ import annotations
import csv, hashlib, os, smtplib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT       = Path(__file__).parent
CONTACTS   = ROOT / "trader_contacts.csv"

SUBJECT = "Your channel + Catalyst Edge — free cross-promo for your audience"

HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<p>Hi {name},</p>
<p>I've been watching your content — the traders following you would love what we built.</p>
<p><strong>Catalyst Edge</strong> is a free daily newsletter that scans 300+ SEC EDGAR
filings and 1,600+ tickers every morning before the market opens, then delivers the top
pre-market gap plays, insider filing alerts, and squeeze setups before 4 AM ET.</p>
<p>Completely automated, completely free for subscribers. Here's what we're running:</p>
<ul>
<li>📊 Daily gap scanner: <a href="https://catalystedge.agency">catalystedge.agency</a></li>
<li>📲 Live Telegram alerts: <a href="https://t.me/CatalystEdgePro">t.me/CatalystEdgePro</a></li>
<li>💬 Discord community: <a href="https://discord.gg/8aJEHghHVy">discord.gg/8aJEHghHVy</a></li>
</ul>
<p>Simple ask: mention us to your audience once and we'll feature your channel
to our subscribers. No cost, no obligation — two traders helping each other's communities.</p>
<p>Would that work for you?</p>
<p>— Catalyst Edge Team<br>opensource@example.com</p>
</body></html>"""

PLAIN = """\
Hi {name},

I've been watching your content — the traders following you would love what we built.

Catalyst Edge scans 300+ SEC EDGAR filings and 1,600+ tickers every morning before the
open, delivering top pre-market gap plays and insider filing alerts before 4 AM ET.
Free for subscribers, fully automated.

Live scanner (today's picks): catalystedgescanner.com
Newsletter: catalystedge.agency
Live Telegram alerts: t.me/CatalystEdgePro
Discord: discord.gg/8aJEHghHVy

Simple ask: mention us to your audience once, we'll feature your channel to our subscribers.
No cost, no strings.

Would that work?

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

def sent_flag(email): return ROOT / f".trader_outreach_{hashlib.md5(email.encode()).hexdigest()[:8]}"
def already_sent(email): return sent_flag(email).exists()
def is_bounced(email):
    h = hashlib.md5(email.encode()).hexdigest()[:8]
    return (ROOT / f".bounced_{h}").exists()
def mark_sent(email): sent_flag(email).touch()

def send(host, port, user, passwd, sender, to, name, tls):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"] = f"Catalyst Edge <{sender}>"; msg["To"] = to
    msg.attach(MIMEText(PLAIN.format(name=name), "plain"))
    msg.attach(MIMEText(HTML.format(name=name), "html"))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if tls: s.starttls()
            s.login(user, passwd); s.sendmail(sender, to, msg.as_string())
        return True
    except Exception as e:
        print(f"  error: {e}"); return False

def main():
    if not CONTACTS.exists():
        print("trader_contacts.csv not found — run discover_trader_contacts.py first")
        return 0
    env = load_env()
    host = env.get("SMTP_HOST",""); port = int(env.get("SMTP_PORT",587))
    user = env.get("SMTP_USER",""); passwd = env.get("SMTP_PASS","").replace(" ","")
    sender = env.get("EMAIL_FROM", user); tls = env.get("SMTP_USE_TLS","true").lower()=="true"
    if not all([host, user, passwd]): print("SMTP not configured"); return 1

    rows = []
    with CONTACTS.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sent = 0
    for row in rows:
        email = row.get("email","").strip()
        raw_name = row.get("name","").strip()
        name = raw_name if raw_name and raw_name not in ("Home","Unknown","Trader","") else "Trader"
        if not email or already_sent(email) or is_bounced(email):
            continue
        print(f"  → {name} <{email}>")
        if send(host, port, user, passwd, sender, email, name, tls):
            mark_sent(email); sent += 1; print("    ✅ sent")
        else:
            print("    ❌ failed")
        time.sleep(4)

    print(f"send_trader_outreach: {sent} sent")
    return 0

if __name__ == "__main__": raise SystemExit(main())
