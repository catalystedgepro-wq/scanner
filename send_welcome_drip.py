#!/usr/bin/env python3
"""send_welcome_drip.py — Welcome email drip for scanner subscribers.

Reads from subscribers.json (populated by /api/subscribe).
Sends a 3-email welcome sequence:
  Day 0: Welcome + how to use the scanner + all free tools
  Day 1: Top features deep dive (squeeze radar, dark pool, insider clusters)
  Day 2: API / Premium pitch

Only sends one email per subscriber per day.
Requires SMTP env vars in .sec_email_env.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent
SUBS_FILE = ROOT / "subscribers.json"
SITE = "https://catalystedgescanner.com"


def _load_env():
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_subs() -> list[dict]:
    if SUBS_FILE.exists():
        try:
            return json.loads(SUBS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _save_subs(subs: list[dict]):
    SUBS_FILE.write_text(json.dumps(subs, indent=2), encoding="utf-8")


EMAILS = {
    0: {
        "subject": "Welcome to Catalyst Edge — Here's Everything You Get Free",
        "html": f"""
<div style="max-width:580px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px 24px;border-radius:12px">
  <div style="text-align:center;margin-bottom:24px">
    <span style="font-size:1.8em;font-weight:800;color:#d4a843">Catalyst Edge</span>
  </div>
  <h1 style="font-size:1.4em;color:#e2e8f0;margin-bottom:16px">Welcome aboard.</h1>
  <p style="color:#94a3b8;line-height:1.7;font-size:.95em">
    You just signed up for the only SEC filing scanner that scores catalysts, tracks squeeze pressure,
    and monitors dark pool signals — all before market open.
  </p>
  <p style="color:#94a3b8;line-height:1.7;font-size:.95em">Here's everything you get for free:</p>

  <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:16px;margin:20px 0">
    <p style="color:#d4a843;font-weight:700;margin:0 0 12px;font-size:.95em">Your Free Tools:</p>
    <p style="margin:6px 0;font-size:.9em"><a href="{SITE}/" style="color:#22c55e;text-decoration:none">Scanner</a> — 1,600+ tickers scored daily before 4 AM ET</p>
    <p style="margin:6px 0;font-size:.9em"><a href="{SITE}/alerts/" style="color:#22c55e;text-decoration:none">Filing Alerts</a> — Get notified when your tickers file with SEC</p>
    <p style="margin:6px 0;font-size:.9em"><a href="{SITE}/cheat-sheet/" style="color:#22c55e;text-decoration:none">Cheat Sheet</a> — 12 filing types ranked by win rate (free download)</p>
    <p style="margin:6px 0;font-size:.9em"><a href="{SITE}/arcade/" style="color:#22c55e;text-decoration:none">Arcade Game</a> — SEC Signal Defense (seriously, try it)</p>
    <p style="margin:6px 0;font-size:.9em"><a href="{SITE}/compare/" style="color:#22c55e;text-decoration:none">Scanner Comparison</a> — How we stack up vs Finviz, TradingView</p>
    <p style="margin:6px 0;font-size:.9em"><a href="{SITE}/methodology/" style="color:#22c55e;text-decoration:none">Methodology</a> — How the scoring engine works</p>
  </div>

  <p style="color:#94a3b8;line-height:1.7;font-size:.95em">
    Tomorrow I'll show you the three most powerful features that most traders miss.
  </p>
  <p style="color:#64748b;font-size:.8em;margin-top:24px">
    — Catalyst Edge<br>
    <a href="{SITE}" style="color:#d4a843;text-decoration:none">catalystedgescanner.com</a>
  </p>
</div>""",
    },
    1: {
        "subject": "3 Scanner Features Most Traders Miss",
        "html": f"""
<div style="max-width:580px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px 24px;border-radius:12px">
  <div style="text-align:center;margin-bottom:24px">
    <span style="font-size:1.4em;font-weight:800;color:#d4a843">Catalyst Edge</span>
  </div>
  <h1 style="font-size:1.3em;color:#e2e8f0;margin-bottom:16px">3 Features That Give You an Edge</h1>

  <div style="background:#111827;border-left:3px solid #06b6d4;padding:14px 16px;border-radius:0 8px 8px 0;margin:16px 0">
    <p style="color:#06b6d4;font-weight:700;margin:0 0 6px;font-size:.95em">1. Squeeze Radar (0-100)</p>
    <p style="color:#94a3b8;margin:0;font-size:.88em;line-height:1.6">
      Combines short interest, days-to-cover, utilization rate, and cost-to-borrow into a single score.
      When squeeze_score &gt; 70 and an 8-K drops, the setup is explosive.
      <a href="{SITE}/glossary/short-squeeze-scanner/" style="color:#22c55e;text-decoration:none">Learn more</a>
    </p>
  </div>

  <div style="background:#111827;border-left:3px solid #8b5cf6;padding:14px 16px;border-radius:0 8px 8px 0;margin:16px 0">
    <p style="color:#8b5cf6;font-weight:700;margin:0 0 6px;font-size:.95em">2. Dark Pool Signals</p>
    <p style="color:#94a3b8;margin:0;font-size:.88em;line-height:1.6">
      35-40% of US volume runs through dark pools. When institutional block volume spikes,
      it often precedes directional moves — especially combined with SEC filing catalysts.
      <a href="{SITE}/glossary/dark-pool-signals/" style="color:#22c55e;text-decoration:none">Learn more</a>
    </p>
  </div>

  <div style="background:#111827;border-left:3px solid #22c55e;padding:14px 16px;border-radius:0 8px 8px 0;margin:16px 0">
    <p style="color:#22c55e;font-weight:700;margin:0 0 6px;font-size:.95em">3. Insider Buy Clusters</p>
    <p style="color:#94a3b8;margin:0;font-size:.88em;line-height:1.6">
      One insider buy is data. Three insider buys in 10 days is conviction.
      Our scanner detects these clusters and flags them alongside the filing catalyst.
      <a href="{SITE}/glossary/insider-buying-signals/" style="color:#22c55e;text-decoration:none">Learn more</a>
    </p>
  </div>

  <p style="color:#94a3b8;line-height:1.7;font-size:.95em;margin-top:20px">
    Tomorrow: how traders are using the API to automate their morning workflow.
  </p>
  <p style="color:#64748b;font-size:.8em;margin-top:24px">
    — Catalyst Edge<br>
    <a href="{SITE}" style="color:#d4a843;text-decoration:none">catalystedgescanner.com</a>
  </p>
</div>""",
    },
    2: {
        "subject": "Automate Your Morning Edge — API + Premium",
        "html": f"""
<div style="max-width:580px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px 24px;border-radius:12px">
  <div style="text-align:center;margin-bottom:24px">
    <span style="font-size:1.4em;font-weight:800;color:#d4a843">Catalyst Edge</span>
  </div>
  <h1 style="font-size:1.3em;color:#e2e8f0;margin-bottom:16px">From Scanner to Algo in One Line</h1>

  <p style="color:#94a3b8;line-height:1.7;font-size:.95em">
    The free scanner gives you the scores. Premium gives you the <strong style="color:#e2e8f0">data feed</strong>.
  </p>

  <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:16px;margin:20px 0;font-family:monospace;font-size:.85em;color:#22c55e;line-height:1.6">
    curl -H "X-API-Key: ce_YOUR_KEY" \\<br>
    &nbsp;&nbsp;{SITE}/api/universe
  </div>

  <p style="color:#94a3b8;line-height:1.7;font-size:.95em">
    14 fields per ticker. 1,600+ tickers daily. JSON or CSV. Before 3:30 AM ET.
  </p>

  <div style="background:#0f1f0f;border:2px solid #22c55e;border-radius:10px;padding:20px;margin:24px 0;text-align:center">
    <p style="color:#22c55e;font-weight:800;font-size:1.2em;margin:0 0 8px">Pro / Prop Desk — $99/mo</p>
    <p style="color:#94a3b8;font-size:.88em;margin:0 0 16px">API access + CSV delivery + full scoring source code + Slack channel</p>
    <a href="{SITE}/pricing/" style="display:inline-block;padding:12px 28px;background:#22c55e;color:#0a0e1a;font-weight:700;border-radius:8px;text-decoration:none;font-size:.95em">See Plans</a>
  </div>

  <p style="color:#94a3b8;line-height:1.7;font-size:.95em">
    Want a sample CSV first? Reply to this email and I'll send last week's feed — no commitment.
  </p>

  <div style="border-top:1px solid #1e293b;margin-top:24px;padding-top:16px">
    <p style="color:#64748b;font-size:.78em;margin:0">
      <a href="{SITE}/api/" style="color:#d4a843;text-decoration:none">API Docs</a> &middot;
      <a href="{SITE}/methodology/" style="color:#d4a843;text-decoration:none">Methodology</a> &middot;
      <a href="{SITE}/compare/" style="color:#d4a843;text-decoration:none">Compare Tools</a>
    </p>
    <p style="color:#64748b;font-size:.8em;margin-top:8px">
      — Catalyst Edge<br>
      <a href="{SITE}" style="color:#d4a843;text-decoration:none">catalystedgescanner.com</a>
    </p>
  </div>
</div>""",
    },
}


def _send_email(to: str, subject: str, html: str):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    email_from = os.environ.get("EMAIL_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        print(f"  [SKIP] No SMTP credentials configured")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Catalyst Edge <{email_from}>"
    msg["To"] = to
    msg.set_content(subject)  # plaintext fallback
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"  [SENT] Day email to {to}: {subject}")
        return True
    except Exception as e:
        print(f"  [FAIL] {to}: {e}")
        return False


def main():
    _load_env()
    subs = _load_subs()
    if not subs:
        print("[welcome_drip] No subscribers found")
        return

    today = dt.date.today().isoformat()
    changed = False

    for sub in subs:
        email = sub.get("email", "")
        if not email or not sub.get("active", True):
            continue

        joined = sub.get("joined", today)
        try:
            join_date = dt.date.fromisoformat(joined)
        except (ValueError, TypeError):
            join_date = dt.date.today()

        days_since = (dt.date.today() - join_date).days
        sent_days = sub.get("welcome_sent_days", [])

        # Only send days 0, 1, 2
        if days_since > 3:
            continue

        day_to_send = min(days_since, 2)
        if day_to_send in sent_days:
            continue

        email_data = EMAILS.get(day_to_send)
        if not email_data:
            continue

        if _send_email(email, email_data["subject"], email_data["html"]):
            sent_days.append(day_to_send)
            sub["welcome_sent_days"] = sent_days
            changed = True

    if changed:
        _save_subs(subs)
        print(f"[welcome_drip] Updated {SUBS_FILE.name}")
    else:
        print("[welcome_drip] No emails to send today")


if __name__ == "__main__":
    main()
