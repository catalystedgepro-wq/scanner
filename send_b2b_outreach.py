#!/usr/bin/env python3
"""send_b2b_outreach.py — Pitch SEC scanner data feed to prop firms and data buyers.

These are buyers who pay for the underlying data, not subscribers.
Gate: .b2b_outreach_{hash} per contact.
"""
from __future__ import annotations
import hashlib, os, smtplib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent

CONTACTS = [
    ("SMB Capital",             "info@smbcap.com"),
    ("Maverick Trading",        "support@mavericktrading.com"),
    ("Topstep",                 "support@topstep.com"),
    ("Earn2Trade",              "support@earn2trade.com"),
    ("T3 Trading Group",        "info@t3trading.com"),
    ("Jane Street",             "media@janestreet.com"),
    ("Jane Street Sponsorship", "sponsorship-inquiries@janestreet.com"),
    ("TradeZero",               "support@tradezero.co"),
    ("Quant Data",              "contact@quantdata.us"),
    ("OTC Markets Media",       "media@otcmarkets.com"),
    ("IBD Licensing",           "licensing@investors.com"),
    # Prop firm / funded trader platforms
    ("FTMO",                    "support@ftmo.com"),
    ("My Forex Funds",          "support@myforexfunds.com"),
    ("True Forex Funds",        "support@trueforexfunds.com"),
    ("Apex Trader Funding",     "support@apextraderfunding.com"),
    ("Funded Next",             "support@fundednext.com"),
    ("The Funded Trader",       "support@thefundedtrader.com"),
    # Market data / fintech buyers
    ("Benzinga Pro",            "pro@benzinga.com"),
    ("Refinitiv Sales",         "sales@refinitiv.com"),
    ("Bloomberg Data Inquiry",  "data@bloomberg.net"),
    ("Quandl / Nasdaq Data",    "data@quandl.com"),
    ("Intrinio",                "sales@intrinio.com"),
    ("Tiingo Data",             "support@tiingo.com"),
    ("Polygon.io",              "support@polygon.io"),
    # Algorithmic trading platforms
    ("QuantConnect Sales",      "support@quantconnect.com"),
    ("Alpaca Markets",          "support@alpaca.markets"),
    ("Tradier API",             "api@tradier.com"),
    ("Interactive Brokers API", "api@interactivebrokers.com"),
    # Family offices / RIAs (directional)
    ("Cambria Investments",     "info@cambriainvestments.com"),
    ("Ritholtz Wealth",         "info@ritholtzwealth.com"),
]

SUBJECT = "SEC EDGAR Gap Scanner Data Feed — Available for Licensing"

HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<p>Hi {name} team,</p>
<p>I've built a fully automated SEC EDGAR scanner that runs before every market open:</p>
<ul>
<li>Parses <strong>300+ catalyst filings</strong> daily (8-K, Form 4, S-3, 13D/G, NT filings)</li>
<li>Scores and ranks <strong>1,600+ tickers</strong> on gap probability, volume, short interest,
and filing sentiment</li>
<li>Outputs structured CSV data: ticker, gap%, volume ratio, catalyst type, insider signal,
squeeze score, filing URL</li>
<li>Runs daily at 3:30 AM ET — data ready before pre-market opens</li>
<li>Built on pure Python stdlib — no third-party data dependencies</li>
</ul>
<p>Currently powering a free daily newsletter
(<a href="https://catalystedge.agency">catalystedge.agency</a>) with strong
open rates among active traders. Live scanner output visible at
<a href="https://catalystedgescanner.com">catalystedgescanner.com</a>
— updated every morning before 4 AM ET.</p>
<p><strong>I'm open to licensing the raw data feed, white-labeling the scanner for your
platform, or a revenue-share arrangement.</strong> The full pipeline runs on GitHub
Actions with zero maintenance.</p>
<p>Would you be open to a brief call to explore this?</p>
<p>Best,<br>Catalyst Edge<br>opensource@example.com</p>
</body></html>"""

PLAIN = """\
Hi {name} team,

I've built a fully automated SEC EDGAR scanner that runs before every market open:

- Parses 300+ catalyst filings daily (8-K, Form 4, S-3, 13D/G, NT filings)
- Scores and ranks 1,600+ tickers on gap probability, volume ratio, short interest,
  filing sentiment, and squeeze score
- Outputs structured CSV: ticker, gap%, volume, catalyst type, insider signal, filing URL
- Runs at 3:30 AM ET daily — data ready before pre-market

Currently powers a free daily newsletter (catalystedge.agency).
Live scanner output: catalystedgescanner.com (updated daily before 4 AM).

Open to licensing the raw data feed, white-labeling, or revenue-share.
The pipeline is fully automated on GitHub Actions — zero maintenance.

Would you be open to a brief call?

Best,
Catalyst Edge
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

def sent_flag(email): return ROOT / f".b2b_outreach_{hashlib.md5(email.encode()).hexdigest()[:8]}"
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
    print(f"send_b2b_outreach: {sent}/{len(CONTACTS)} sent")
    return 0

if __name__ == "__main__": raise SystemExit(main())
