#!/usr/bin/env python3
"""send_affiliate_outreach.py — Pitch broker affiliate programs.

Brokers pay $50-$200 per funded account referral. Our audience is active traders.
Gate: .affiliate_outreach_{hash} per contact.
"""
from __future__ import annotations
import hashlib, os, smtplib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent

CONTACTS = [
    ("moomoo PR",                      "pr@moomoo.com"),
    ("Tradier Brokerage",              "service@tradierbrokerage.com"),
    ("tastytrade",                     "accounts@tastytrade.com"),
    ("Interactive Brokers Influencer", "influencers@ibkr.com"),
    ("Interactive Brokers Publishers", "publishers@interactivebrokers.com"),
    ("TradeStation Affiliates",        "affiliates@tradestation.com"),
    ("Cobra Trading",                  "info@cobratrading.com"),
    ("Charles Schwab Affiliates",      "affiliates@schwab.com"),
    ("Public.com",                     "press@public.com"),
    ("Simply Wall St Affiliates",      "affiliates@simplywallst.com"),
    # Additional brokers with active affiliate programs
    ("Webull Media",                   "media@webull.com"),
    ("Firstrade Affiliates",           "affiliates@firstrade.com"),
    ("Ally Invest Partners",           "partners@ally.com"),
    ("SoFi Invest Affiliates",         "affiliates@sofi.com"),
    ("M1 Finance Partners",            "partnerships@m1.com"),
    ("Robinhood Affiliates",           "affiliates@robinhood.com"),
    ("eToro Partners",                 "affiliates@etoro.com"),
    # Trading education affiliates
    ("Warrior Trading Affiliates",     "affiliates@warriortrading.com"),
    ("Investopedia Academy",           "academy@investopedia.com"),
    ("Bulls on Wall Street Affiliates","affiliates@bullsonwallstreet.com"),
]

SUBJECT = "Affiliate Partnership — Catalyst Edge Newsletter (Active Trader Audience)"

HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<p>Hi {name} team,</p>
<p>I run <strong>Catalyst Edge</strong> — a free daily newsletter delivering pre-market
gap plays and SEC filing alerts to active traders before 4 AM ET. We scan 300+ EDGAR
filings and 1,600+ tickers every morning.</p>
<p><strong>Our audience profile:</strong></p>
<ul>
<li>Active retail traders — day traders and swing traders</li>
<li>Engaged daily: 37%+ open rates</li>
<li>Growing across Telegram (<a href="https://t.me/CatalystEdgePro">@CatalystEdgePro</a>)
and Discord (<a href="https://discord.gg/8aJEHghHVy">discord.gg/8aJEHghHVy</a>)</li>
<li>Audience specifically interested in pre-market movers and catalyst-driven setups</li>
</ul>
<p>This is exactly the audience that opens brokerage accounts to act on the alerts
they receive. I'd love to explore adding your affiliate link to our daily newsletter
and Telegram channel.</p>
<p>Do you have an affiliate or partner program I can apply to, or a direct contact
for your partnerships team?</p>
<p>Best,<br>Catalyst Edge Team<br>opensource@example.com<br>
<a href="https://catalystedge.agency">catalystedge.agency</a><br>
<a href="https://catalystedgescanner.com">Live Scanner</a></p>
</body></html>"""

PLAIN = """\
Hi {name} team,

I run Catalyst Edge — a free daily newsletter delivering pre-market gap plays and
SEC filing alerts to active traders before 4 AM ET. 300+ EDGAR filings scanned daily.

Audience: active retail day/swing traders, 37%+ open rates, growing on Telegram
(@CatalystEdgePro) and Discord.

This is exactly the audience that opens brokerage accounts to act on alerts.
I'd love to add your affiliate link to our newsletter and Telegram channel.

Do you have an affiliate program I can apply to?

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

def sent_flag(email): return ROOT / f".affiliate_outreach_{hashlib.md5(email.encode()).hexdigest()[:8]}"
def already_sent(email): return sent_flag(email).exists()
def mark_sent(email): sent_flag(email).touch()

def send(host, port, user, passwd, sender, to, name, tls):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT; msg["From"] = f"Catalyst Edge <{sender}>"; msg["To"] = to
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
    env = load_env()
    host = env.get("SMTP_HOST",""); port = int(env.get("SMTP_PORT",587))
    user = env.get("SMTP_USER",""); passwd = env.get("SMTP_PASS","").replace(" ","")
    sender = env.get("EMAIL_FROM", user); tls = env.get("SMTP_USE_TLS","true").lower()=="true"
    if not all([host, user, passwd]): print("SMTP not configured"); return 1
    sent = 0
    for name, email in CONTACTS:
        if already_sent(email): print(f"  already sent → {email}"); continue
        print(f"  → {name} <{email}>")
        if send(host, port, user, passwd, sender, email, name, tls):
            mark_sent(email); sent += 1; print("    ✅ sent")
        else: print("    ❌ failed")
        time.sleep(3)
    print(f"send_affiliate_outreach: {sent}/{len(CONTACTS)} sent")
    return 0

if __name__ == "__main__": raise SystemExit(main())
