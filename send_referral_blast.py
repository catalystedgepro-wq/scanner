#!/usr/bin/env python3
"""send_referral_blast.py — Email existing subscribers about referral program + Telegram.

Sends a one-time re-engagement email to all active Beehiiv subscribers:
- Announces the live Telegram gap alert channel
- Promotes the referral program (already enabled on Beehiiv)
- Reminds them of the Discord watchlist
- Asks them to share with one trader friend

Gate: .referral_blast_sent (never sends twice)
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent
FLAG = ROOT / ".referral_blast_sent"


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


def get_subscribers(api_key: str, pub_id: str) -> list[str]:
    req = urllib.request.Request(
        f"https://api.beehiiv.com/v2/publications/{pub_id}/subscriptions"
        f"?limit=100&status=active",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return [s["email"] for s in data.get("data", []) if s.get("email")]


HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">

<h2 style="color:#00c853;">⚡ Big Update — Catalyst Edge Just Got More Powerful</h2>

<p>Hey,</p>

<p>We've been building hard behind the scenes. Here's what's new:</p>

<hr style="border:1px solid #eee;">

<h3>📲 Real-Time Gap Alerts on Telegram</h3>
<p>Our scanner now fires <strong>instant alerts to Telegram</strong> the moment a penny stock gaps up
— sometimes as early as 4:00 AM ET before anyone else sees it.</p>

<p><strong>Join the channel → <a href="https://t.me/CatalystEdgePro" style="color:#00c853;">t.me/CatalystEdgePro</a></strong></p>
<p style="color:#666;font-size:13px;">Free. No spam. Only real alerts when the scanner fires.</p>

<hr style="border:1px solid #eee;">

<h3>📊 Live Discord Watchlist</h3>
<p>We have a live Discord server with a watchlist that updates every 5 minutes with real prices,
gap percentages, and volume — visible right in the server sidebar.</p>
<p><a href="https://discord.gg/8aJEHghHVy" style="color:#00c853;">Join the Catalyst Edge Discord →</a></p>

<hr style="border:1px solid #eee;">

<h3>🎁 Refer a Trader — Grow Together</h3>
<p>You're one of the early subscribers. That means you get in on our referral program first.</p>

<p><strong>Share your unique link and when a friend subscribes, you both benefit.</strong>
The more traders we have, the better our collective intelligence gets.</p>

<p>Your referral link is in every newsletter footer — or log into
<a href="https://catalystedge.agency" style="color:#00c853;">catalystedge.agency</a>
to find it.</p>

<p style="background:#f0fff4;padding:15px;border-left:4px solid #00c853;">
<strong>Ask yourself:</strong> Do you know one trader who would benefit from knowing which stocks
are gapping up before the market opens, sourced directly from SEC filings?
<br><br>
Forward this email to them. That's it.
</p>

<hr style="border:1px solid #eee;">

<p>We scan 1,600+ tickers and 300+ SEC filings before every open so you don't have to.
The newsletter lands before 4 AM ET every trading day.</p>

<p>Thank you for being here from the start.</p>

<p>— The Catalyst Edge Team</p>

<p style="font-size:11px;color:#999;">
Catalyst Edge · catalystedge.agency · Telegram: @CatalystEdgePro<br>
You're receiving this because you subscribed to the Catalyst Edge newsletter.
</p>

</body>
</html>
"""

PLAIN = """\
Big Update — Catalyst Edge Just Got More Powerful

1. REAL-TIME TELEGRAM ALERTS
Our scanner now fires instant alerts to Telegram the moment a stock gaps up — sometimes at 4 AM.
Join: t.me/CatalystEdgePro

2. LIVE DISCORD WATCHLIST
Live prices updating every 5 minutes in our Discord server sidebar.
Join: discord.gg/8aJEHghHVy

3. REFERRAL PROGRAM
Share your unique link (in every newsletter footer) and grow together.
Or just forward this email to one trader who would benefit.

We scan 1,600+ tickers before every open. Newsletter lands before 4 AM ET daily.

— Catalyst Edge Team
catalystedge.agency
"""


def send(smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
         from_addr: str, to_addr: str, use_tls: bool) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "⚡ New: Real-time gap alerts on Telegram + referral program"
    msg["From"]    = f"Catalyst Edge <{from_addr}>"
    msg["To"]      = to_addr
    msg.attach(MIMEText(PLAIN, "plain"))
    msg.attach(MIMEText(HTML,  "html"))
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            if use_tls:
                s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(from_addr, to_addr, msg.as_string())
        return True
    except Exception as e:
        print(f"  send error to {to_addr}: {e}")
        return False


def main() -> int:
    if FLAG.exists():
        print("send_referral_blast: already sent — skipping")
        return 0

    env = load_env()
    smtp_host = env.get("SMTP_HOST", "")
    smtp_port = int(env.get("SMTP_PORT", 465))
    smtp_user = env.get("SMTP_USER", "")
    smtp_pass = env.get("SMTP_PASS", "").replace(" ", "")
    from_addr = env.get("EMAIL_FROM", smtp_user)
    api_key   = env.get("BEEHIIV_API_KEY", "")
    pub_id    = env.get("BEEHIIV_PUB_ID", "")
    use_tls   = env.get("SMTP_USE_TLS", "true").lower() == "true"

    if not all([smtp_host, smtp_user, smtp_pass, api_key, pub_id]):
        print("send_referral_blast: missing credentials — skipping")
        return 1

    emails = get_subscribers(api_key, pub_id)
    print(f"send_referral_blast: {len(emails)} subscribers found")

    sent = 0
    for email in emails:
        print(f"  → {email}")
        if send(smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, email, use_tls):
            sent += 1
    print(f"send_referral_blast: {sent}/{len(emails)} sent")
    if sent > 0:
        FLAG.touch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
