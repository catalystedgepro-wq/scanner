#!/usr/bin/env python3
"""send_partner_outreach.py — Cold outreach to trading newsletter operators.

Sends personalized partnership pitch to trading communities and newsletters.
Gate: .partner_outreach_{email_hash} per contact — never double-sends.
"""
from __future__ import annotations

import hashlib
import os
import smtplib
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent

CONTACTS = [
    # Tier 1 — already sent
    # Tier 2 — trading newsletters & communities
    # Tier 3 — penny stock / small cap focused
    # Tier 4 — broader finance / options
    # Tier 5 — financial education blogs
    # Tier 6 — independent trader blogs / influencers
    # Tier 7 — financial media / press
    # Tier 8 — SEC / regulatory watchers
    # Tier 9 — quant / data newsletters
    # Tier 10 — Reddit / community-adjacent newsletters
    # Tier 11 — broker / platform editorial teams
    ]

SUBJECT = "Partnership Opportunity — Free SEC Gap Scanner for Your Audience"

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">

<p>Hi {name} team,</p>

<p>I'm reaching out from <strong>Catalyst Edge</strong> — a free daily newsletter that scans
300+ SEC filings and 1,600+ tickers every morning before the market opens, then delivers
the top gap plays, insider filing alerts, and squeeze candidates directly to traders'
inboxes before 4 AM ET.</p>

<p>We built the entire thing from scratch — automated SEC EDGAR parsing, gap detection,
momentum scoring, and multi-platform alerts (email, Telegram, Discord, StockTwits).</p>

<p><strong>Why I'm reaching out:</strong></p>
<p>Your audience are exactly the traders who benefit most from knowing which stocks are
moving on SEC filings before the algos front-run them. We'd love to explore a simple
cross-promotion — a mention in your next newsletter in exchange for featuring your
publication to our growing subscriber base.</p>

<ul>
<li>📊 Live scanner: <a href="https://catalystedgescanner.com">catalystedgescanner.com</a> (today's picks, updated daily)</li>
<li>📬 Newsletter: <a href="https://catalystedge.agency">catalystedge.agency</a></li>
<li>📲 Live Telegram alerts: <a href="https://t.me/CatalystEdgePro">t.me/CatalystEdgePro</a></li>
<li>💬 Discord community: <a href="https://discord.gg/8aJEHghHVy">discord.gg/8aJEHghHVy</a></li>
</ul>

<p>No cost. No obligation. Just two newsletters helping each other's audiences.</p>

<p>Would a 15-minute call work this week to explore this?</p>

<p>Best,<br>
Catalyst Edge Team<br>
opensource@example.com<br>
<a href="https://catalystedge.agency">catalystedge.agency</a></p>

</body>
</html>
"""

PLAIN_TEMPLATE = """\
Hi {name} team,

I'm reaching out from Catalyst Edge — a free daily newsletter that scans 300+ SEC filings
and 1,600+ tickers every morning before the market opens, delivering top gap plays and
insider filing alerts to traders before 4 AM ET.

Your audience would benefit from our pre-market intelligence. We'd love to explore a
simple cross-promotion — a mention in your next newsletter in exchange for featuring
your publication to our growing subscriber base.

Live scanner (today's picks): catalystedgescanner.com
Newsletter: catalystedge.agency
Live Telegram alerts: t.me/CatalystEdgePro
Discord: discord.gg/8aJEHghHVy

Would a quick call work this week?

Best,
Catalyst Edge Team
opensource@example.com
"""


def load_env() -> dict:
    env = {}
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k, v in os.environ.items():
        env.setdefault(k, v)
    return env


def already_sent(email: str) -> bool:
    h = hashlib.md5(email.encode()).hexdigest()[:8]
    return (ROOT / f".partner_outreach_{h}").exists()


def mark_sent(email: str) -> None:
    h = hashlib.md5(email.encode()).hexdigest()[:8]
    (ROOT / f".partner_outreach_{h}").touch()


def send(smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
         from_addr: str, to_addr: str, name: str, use_tls: bool) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"]    = f"Catalyst Edge <{from_addr}>"
    msg["To"]      = to_addr
    msg["Reply-To"] = from_addr
    msg.attach(MIMEText(PLAIN_TEMPLATE.format(name=name), "plain"))
    msg.attach(MIMEText(HTML_TEMPLATE.format(name=name),  "html"))
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            if use_tls:
                s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(from_addr, to_addr, msg.as_string())
        return True
    except Exception as e:
        print(f"  error → {to_addr}: {e}")
        return False


def main() -> int:
    env     = load_env()
    host    = env.get("SMTP_HOST", "")
    port    = int(env.get("SMTP_PORT", 465))
    user    = env.get("SMTP_USER", "")
    passwd  = env.get("SMTP_PASS", "").replace(" ", "")
    sender  = env.get("EMAIL_FROM", user)
    use_tls = env.get("SMTP_USE_TLS", "true").lower() == "true"

    if not all([host, user, passwd]):
        print("send_partner_outreach: SMTP not configured")
        return 1

    sent = 0
    for name, email in CONTACTS:
        if already_sent(email):
            print(f"  already sent → {email}")
            continue
        print(f"  → {name} <{email}>")
        if send(host, port, user, passwd, sender, email, name, use_tls):
            mark_sent(email)
            sent += 1
            print(f"    ✅ sent")
        else:
            print(f"    ❌ failed")
        time.sleep(3)

    print(f"send_partner_outreach: {sent}/{len(CONTACTS)} sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
