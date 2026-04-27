#!/usr/bin/env python3
"""send_partner_followup.py — Follow-up to partner outreach (sent 7+ days ago, no response).

Gate: .partner_followup_{email_hash} per contact — never double-sends.
Only sends to contacts that already have a .partner_outreach_{hash} flag (initial sent)
and do NOT have a .partner_followup_{hash} flag yet.
Waits 7+ days from initial send (flag mtime).
"""
from __future__ import annotations

import hashlib
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import datetime

ROOT = Path(__file__).parent

SUBJECT = "Re: Partnership Opportunity — Catalyst Edge × {name}"

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">

<p>Hi {name} team,</p>

<p>Following up on my note from last week about a cross-promotion between Catalyst Edge
and your publication.</p>

<p>Quick context: We scan 300+ SEC filings and 1,600+ tickers every morning and email traders
our top gap plays before 4 AM ET — all free, all automated. Growing fast on Telegram
(<a href="https://t.me/CatalystEdgePro">@CatalystEdgePro</a>) and Discord as well.</p>

<p>The ask is simple: one mention in your next newsletter in exchange for us featuring your
publication to our subscriber base. Zero cost, no strings.</p>

<p>If this isn't the right fit, no worries at all — just let me know and I won't follow up
again. But if there's any interest, I'd love to connect briefly.</p>

<p>Best,<br>
Catalyst Edge Team<br>
opensource@example.com<br>
<a href="https://catalystedge.agency">catalystedge.agency</a></p>

</body>
</html>
"""

PLAIN_TEMPLATE = """\
Hi {name} team,

Following up on my note from last week about a cross-promotion between Catalyst Edge
and your publication.

We scan 300+ SEC filings before every open, deliver top gap plays before 4 AM ET.
Growing fast on Telegram (t.me/CatalystEdgePro) and Discord.

Simple ask: one mention in your next newsletter in exchange for featuring your publication
to our subscribers. Zero cost.

If not a fit, just say so — I won't follow up again.

Best,
Catalyst Edge Team
opensource@example.com
catalystedge.agency
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


def hash8(email: str) -> str:
    return hashlib.md5(email.encode()).hexdigest()[:8]


def initial_sent(email: str) -> bool:
    return (ROOT / f".partner_outreach_{hash8(email)}").exists()


def followup_sent(email: str) -> bool:
    return (ROOT / f".partner_followup_{hash8(email)}").exists()


def days_since_initial(email: str) -> float:
    flag = ROOT / f".partner_outreach_{hash8(email)}"
    if not flag.exists():
        return 0.0
    age = datetime.datetime.now() - datetime.datetime.fromtimestamp(flag.stat().st_mtime)
    return age.total_seconds() / 86400


def mark_followup(email: str) -> None:
    (ROOT / f".partner_followup_{hash8(email)}").touch()


def send(smtp_host, smtp_port, smtp_user, smtp_pass, from_addr,
         to_addr, name, use_tls) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT.format(name=name)
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
    from send_partner_outreach import CONTACTS

    env     = load_env()
    host    = env.get("SMTP_HOST", "")
    port    = int(env.get("SMTP_PORT", 465))
    user    = env.get("SMTP_USER", "")
    passwd  = env.get("SMTP_PASS", "").replace(" ", "")
    sender  = env.get("EMAIL_FROM", user)
    use_tls = env.get("SMTP_USE_TLS", "true").lower() == "true"

    if not all([host, user, passwd]):
        print("send_partner_followup: SMTP not configured")
        return 1

    MIN_DAYS = 7
    sent = 0
    skipped = 0
    for name, email in CONTACTS:
        if not initial_sent(email):
            continue  # never sent initial — skip
        if followup_sent(email):
            skipped += 1
            continue
        days = days_since_initial(email)
        if days < MIN_DAYS:
            print(f"  too soon ({days:.1f}d) → {email}")
            continue
        print(f"  → {name} <{email}> ({days:.0f}d ago)")
        if send(host, port, user, passwd, sender, email, name, use_tls):
            mark_followup(email)
            sent += 1
            print(f"    ✅ sent")
        else:
            print(f"    ❌ failed")
        time.sleep(3)

    print(f"send_partner_followup: {sent} follow-ups sent, {skipped} already followed up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
