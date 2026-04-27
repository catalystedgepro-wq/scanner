#!/usr/bin/env python3
"""send_welcome_sequence.py — 3-email welcome sequence for new Beehiiv subscribers.

Email 1 (day 0): Welcome + scanner link + Telegram invite
Email 2 (day 2): How the scanner works — builds trust/credibility
Email 3 (day 5): Premium pitch — convert to $9/month

Tracks state in .welcome_{hash}.json per subscriber email.
Reads subscriber list from Beehiiv API.
"""
from __future__ import annotations
import hashlib, json, os, smtplib, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).parent

# ── Email 1: Welcome ──────────────────────────────────────────────────────────
SUBJ_1 = "Welcome to Catalyst Edge — your first picks are ready"
HTML_1 = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<h2 style="color:#1a1a1a;">You're in. Here's what happens next.</h2>
<p>Every weekday morning before 4 AM ET, you'll receive the top SEC catalyst plays
for the pre-market — scored by gap probability, insider signal strength, and squeeze potential.</p>
<p><strong>Start here:</strong></p>
<ul>
<li>📊 <a href="https://catalystedgescanner.com">Today's live picks</a>
— updated every morning before the open</li>
<li>📲 <a href="https://t.me/CatalystEdgePro">Join the Telegram channel</a>
— real-time alerts throughout the trading day</li>
<li>💬 <a href="https://discord.gg/8aJEHghHVy">Join the Discord</a>
— discuss setups with other traders</li>
</ul>
<p>The newsletter hits your inbox before 4 AM. If you don't see it, check spam
and mark us as safe — that's the most important thing you can do right now.</p>
<p>Talk soon,<br>Catalyst Edge Team<br>opensource@example.com</p>
</body></html>"""

PLAIN_1 = """\
You're in. Here's what happens next.

Every weekday before 4 AM ET you'll get the top SEC catalyst plays for the pre-market
— scored by gap probability, insider signal, and squeeze potential.

START HERE:
- Today's live picks: catalystedgescanner.com
- Real-time Telegram alerts: t.me/CatalystEdgePro
- Discord community: discord.gg/8aJEHghHVy

The newsletter hits before 4 AM. Mark us as safe so you don't miss it.

Talk soon,
Catalyst Edge Team
opensource@example.com
"""

# ── Email 2: How it works ─────────────────────────────────────────────────────
SUBJ_2 = "How we find stocks before the algos do"
HTML_2 = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<h2>How the scanner actually works</h2>
<p>Most traders find out about a stock move <em>after</em> it's already happened.
We built Catalyst Edge to flip that.</p>
<p><strong>Here's the process every morning:</strong></p>
<ol>
<li><strong>3:00 AM ET</strong> — We pull every filing that hit SEC EDGAR overnight:
8-K earnings surprises, Form 4 insider buys, S-3 offerings, 13D activist disclosures,
NT late filings, and merger agreements.</li>
<li><strong>3:15 AM ET</strong> — Each ticker gets scored on:
gap probability, volume ratio vs 3-month average, insider signal strength,
short interest (squeeze potential), and filing sentiment.</li>
<li><strong>3:30 AM ET</strong> — Top picks ranked and packaged.
Premium subscribers get the full CSV. Free subscribers get the top 10.</li>
<li><strong>Before 4 AM ET</strong> — Newsletter delivered. Pre-market opens at 4 AM.
You have the data before anyone without direct EDGAR access.</li>
</ol>
<p>The live output is always at:
<a href="https://catalystedgescanner.com">catalystedgescanner.com</a></p>
<p>Any questions — just reply to this email.<br>
Catalyst Edge Team</p>
</body></html>"""

PLAIN_2 = """\
How the scanner actually works

Most traders find out about a move after it happens. We built Catalyst Edge to flip that.

EVERY MORNING:
3:00 AM — Pull every EDGAR filing overnight: 8-K, Form 4, S-3, 13D, NT filings
3:15 AM — Score each ticker: gap probability, volume ratio, insider signal,
           short interest, filing sentiment
3:30 AM — Rank and package. Premium = full CSV. Free = top 10.
Before 4 AM — Delivered. Pre-market opens at 4 AM. You have it first.

Live output: catalystedgescanner.com

Any questions — just reply.
Catalyst Edge Team
"""

# ── Email 3: Premium pitch ────────────────────────────────────────────────────
SUBJ_3 = "Want the full raw data? Here's what Premium includes"
HTML_3 = """\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<h2>You've been getting the highlights. Here's everything behind them.</h2>
<p>The free newsletter shows you the top 10. Premium gives you the full picture:</p>
<table style="width:100%;border-collapse:collapse;margin:16px 0;">
<tr style="background:#f5f5f5;">
  <th style="padding:8px;text-align:left;border:1px solid #ddd;">Feature</th>
  <th style="padding:8px;text-align:center;border:1px solid #ddd;">Free</th>
  <th style="padding:8px;text-align:center;border:1px solid #ddd;">Premium $9/mo</th>
</tr>
<tr><td style="padding:8px;border:1px solid #ddd;">Daily top picks</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">Top 10</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">All 1,600+ tickers</td></tr>
<tr style="background:#f9f9f9;"><td style="padding:8px;border:1px solid #ddd;">Raw scanner CSV</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">—</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">✅ Full dataset</td></tr>
<tr><td style="padding:8px;border:1px solid #ddd;">Dark pool signals</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">—</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">✅</td></tr>
<tr style="background:#f9f9f9;"><td style="padding:8px;border:1px solid #ddd;">Squeeze radar</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">—</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">✅</td></tr>
<tr><td style="padding:8px;border:1px solid #ddd;">Delivery time</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">3:35 AM ET</td>
<td style="padding:8px;text-align:center;border:1px solid #ddd;">3:30 AM ET</td></tr>
</table>
<p><strong>Reply with "PREMIUM" and we'll send you the payment link.</strong>
$9/month. Cancel anytime.</p>
<p>Catalyst Edge Team<br>opensource@example.com</p>
</body></html>"""

PLAIN_3 = """\
You've been getting the highlights. Here's everything behind them.

FREE vs PREMIUM ($9/month):

                    Free        Premium
Daily picks         Top 10      All 1,600+ tickers
Raw scanner CSV     —           Full dataset
Dark pool signals   —           ✅
Squeeze radar       —           ✅
Delivery            3:35 AM     3:30 AM ET

Reply with "PREMIUM" and we'll send the payment link.
$9/month. Cancel anytime.

Catalyst Edge Team
opensource@example.com
"""

SEQUENCE = [
    (0, SUBJ_1, HTML_1, PLAIN_1),
    (2, SUBJ_2, HTML_2, PLAIN_2),
    (5, SUBJ_3, HTML_3, PLAIN_3),
]

def load_env() -> dict:
    env = {}
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    for k, v in os.environ.items(): env.setdefault(k, v)
    return env

def fetch_beehiiv_subscribers(api_key: str, pub_id: str) -> list[dict]:
    url = f"https://api.beehiiv.com/v2/publications/{pub_id}/subscriptions?limit=100&status=active"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            return data.get("data", [])
    except Exception as e:
        print(f"  beehiiv error: {e}"); return []

def state_file(email: str) -> Path:
    h = hashlib.md5(email.encode()).hexdigest()[:8]
    return ROOT / f".welcome_{h}.json"

def load_state(email: str) -> dict:
    sf = state_file(email)
    if sf.exists():
        return json.loads(sf.read_text())
    return {"subscribed_date": None, "sent_steps": []}

def save_state(email: str, state: dict) -> None:
    state_file(email).write_text(json.dumps(state))

def smtp_send(host, port, user, passwd, sender, to, subj, html, plain, tls) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = f"Catalyst Edge <{sender}>"
    msg["To"] = to
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if tls: s.starttls()
            s.login(user, passwd)
            s.sendmail(sender, to, msg.as_string())
        return True
    except Exception as e:
        print(f"  smtp error: {e}"); return False

def main() -> int:
    env = load_env()
    host   = env.get("SMTP_HOST", ""); port = int(env.get("SMTP_PORT", 587))
    user   = env.get("SMTP_USER", ""); passwd = env.get("SMTP_PASS", "").replace(" ", "")
    sender = env.get("EMAIL_FROM", user); tls = env.get("SMTP_USE_TLS", "true").lower() == "true"
    api_key = env.get("BEEHIIV_API_KEY", ""); pub_id = env.get("BEEHIIV_PUB_ID", "")
    if not all([host, user, passwd]): print("SMTP not configured"); return 1

    subs = fetch_beehiiv_subscribers(api_key, pub_id) if (api_key and pub_id) else []

    # Also include EMAIL_TO subscribers
    extra = [e.strip() for e in env.get("EMAIL_TO", "").split(",") if e.strip()]
    for e in extra:
        if not any(s.get("email") == e for s in subs):
            subs.append({"email": e, "created": int(time.time())})

    sent_total = 0
    now = datetime.now(timezone.utc)

    for sub in subs:
        email = sub.get("email", "").strip()
        if not email: continue

        # Determine subscription date
        created_ts = sub.get("created") or sub.get("created_at") or int(time.time())
        try:
            sub_date = datetime.fromtimestamp(float(created_ts), tz=timezone.utc)
        except Exception:
            sub_date = now

        days_since = (now - sub_date).days
        state = load_state(email)

        # Initialize state for new subscribers
        if state["subscribed_date"] is None:
            state["subscribed_date"] = sub_date.isoformat()
            save_state(email, state)

        for step_day, subj, html, plain in SEQUENCE:
            step_key = f"step_{step_day}"
            if step_key in state["sent_steps"]: continue
            if days_since < step_day: continue

            print(f"  → {email} step {step_day}d: {subj[:50]}")
            if smtp_send(host, port, user, passwd, sender, email, subj, html, plain, tls):
                state["sent_steps"].append(step_key)
                save_state(email, state)
                sent_total += 1
                print("    ✅ sent")
            else:
                print("    ❌ failed")
            time.sleep(3)

    print(f"send_welcome_sequence: {sent_total} emails sent across {len(subs)} subscribers")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
