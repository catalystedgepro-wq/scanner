#!/usr/bin/env python3
"""send_cheatsheet_drip.py — Simple drip email for cheat sheet leads.

Reads from leads.json (populated by the landing page or manually).
Sends a 3-email sequence over 3 days:
  Day 0: Welcome + cheat sheet download link
  Day 1: Top finding deep dive
  Day 2: Premium upgrade pitch

Only sends one email per lead per day.
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
LEADS_FILE = ROOT / "leads.json"
SITE = "https://catalystedgescanner.com"


def _load_env():
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _load_leads() -> list[dict]:
    if LEADS_FILE.exists():
        try:
            return json.loads(LEADS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_leads(leads: list[dict]):
    LEADS_FILE.write_text(json.dumps(leads, indent=2), encoding="utf-8")


def _send_email(smtp_cfg: dict, to: str, subject: str, html: str):
    msg = EmailMessage()
    msg["From"] = smtp_cfg["from"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("View this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(smtp_cfg["host"], int(smtp_cfg["port"])) as s:
        if smtp_cfg.get("tls", "1") == "1":
            s.starttls()
        s.login(smtp_cfg["user"], smtp_cfg["pass"])
        s.send_message(msg)


EMAILS = {
    0: {
        "subject": "Your SEC Filing Cheat Sheet is ready",
        "html": f"""
<div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px 24px;">
  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:12px;color:#d4a843;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Catalyst Edge</div>
    <h1 style="font-size:24px;margin:8px 0;color:#fff;">Your SEC Filing Cheat Sheet</h1>
  </div>

  <p>Thanks for downloading the SEC Filing Cheat Sheet.</p>

  <p>Here's your direct link (bookmark it):</p>

  <div style="text-align:center;margin:24px 0;">
    <a href="{SITE}/cheat-sheet/download.html"
       style="display:inline-block;padding:12px 32px;background:#d4a843;color:#000;font-weight:700;
              border-radius:8px;text-decoration:none;font-size:15px;">
      Open Cheat Sheet
    </a>
  </div>

  <p>Quick highlights from the data:</p>
  <ul style="color:#94a3b8;line-height:1.8;">
    <li><strong style="color:#e2e8f0;">424B1 filings</strong> hit 66.7% — highest of any form type</li>
    <li><strong style="color:#e2e8f0;">424B2 filings</strong> hit just 9.5% — almost always dilutive</li>
    <li><strong style="color:#e2e8f0;">Cost Reduction</strong> tags have a 75% hit rate</li>
    <li><strong style="color:#e2e8f0;">FDA Approvals</strong> hit 66.7% on 3%+ moves</li>
  </ul>

  <p>Tomorrow I'll send you a deep dive on the #1 finding — why certain prospectus types
  outperform everything else.</p>

  <p style="color:#64748b;font-size:13px;margin-top:24px;">
    Meanwhile, check out the <a href="{SITE}" style="color:#d4a843;">live scanner</a> — updated every morning before 4 AM ET.
  </p>

  <div style="text-align:center;border-top:1px solid #1e293b;margin-top:32px;padding-top:16px;font-size:12px;color:#64748b;">
    Catalyst Edge &middot; catalystedgescanner.com<br>
    <a href="{SITE}" style="color:#64748b;">Unsubscribe</a>
  </div>
</div>""",
    },
    1: {
        "subject": "The SEC filing type nobody talks about (66.7% hit rate)",
        "html": f"""
<div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px 24px;">
  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:12px;color:#d4a843;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Catalyst Edge</div>
    <h1 style="font-size:22px;margin:8px 0;color:#fff;">The Filing Type Nobody Watches</h1>
  </div>

  <p>Yesterday I sent you the SEC Filing Cheat Sheet. Today, let's go deeper on the #1 finding.</p>

  <h2 style="font-size:18px;color:#d4a843;margin:24px 0 12px;">424B1: The Quiet Performer</h2>

  <p>Most traders ignore 424B-series filings entirely — they look like boring prospectus documents.
  But our backtest across 8,400+ picks revealed something interesting:</p>

  <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:16px;margin:16px 0;">
    <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
      <span style="color:#94a3b8;">424B1 Hit Rate (3%+ move)</span>
      <span style="color:#22c55e;font-weight:700;">66.7%</span>
    </div>
    <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
      <span style="color:#94a3b8;">424B5 Hit Rate</span>
      <span style="color:#d4a843;font-weight:700;">40.1%</span>
    </div>
    <div style="display:flex;justify-content:space-between;">
      <span style="color:#94a3b8;">424B2 Hit Rate</span>
      <span style="color:#ef4444;font-weight:700;">9.5%</span>
    </div>
  </div>

  <p><strong>Why the difference?</strong> 424B1 is a <em>preliminary</em> prospectus — filed early
  in the offering process. It often signals institutional demand before the market prices it in.
  424B2, by contrast, is structured notes — almost pure dilution.</p>

  <p>The lesson: not all prospectus filings are bearish. The form <em>number</em> matters enormously.</p>

  <h2 style="font-size:18px;color:#d4a843;margin:24px 0 12px;">How to act on this</h2>

  <p>Our scanner filters and ranks these automatically every morning. You don't have to read EDGAR —
  just check the daily email.</p>

  <div style="text-align:center;margin:24px 0;">
    <a href="{SITE}/#subscribe"
       style="display:inline-block;padding:12px 32px;background:#22c55e;color:#000;font-weight:700;
              border-radius:8px;text-decoration:none;font-size:15px;">
      Get Free Daily Picks
    </a>
  </div>

  <p style="color:#64748b;font-size:13px;">
    Tomorrow: why "Cost Reduction" tags have a 75% hit rate — and how to spot them before the crowd.
  </p>

  <div style="text-align:center;border-top:1px solid #1e293b;margin-top:32px;padding-top:16px;font-size:12px;color:#64748b;">
    Catalyst Edge &middot; catalystedgescanner.com
  </div>
</div>""",
    },
    2: {
        "subject": "Your edge is decaying. Lock it in.",
        "html": f"""
<div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:32px 24px;">
  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:12px;color:#d4a843;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Catalyst Edge</div>
    <h1 style="font-size:22px;margin:8px 0;color:#fff;">The Scanner Does The Work</h1>
  </div>

  <p>Over the past 3 days you've seen:</p>

  <ul style="color:#94a3b8;line-height:2;">
    <li>12 SEC form types ranked by win rate</li>
    <li>Why 424B1 outperforms at 66.7%</li>
    <li>Which catalyst tags (Cost Reduction, FDA) predict big moves</li>
  </ul>

  <p>But here's the thing — this data changes <em>daily</em>. New filings drop overnight.
  New catalysts emerge. The edge is in acting on them before 9:30 AM.</p>

  <h2 style="font-size:18px;color:#d4a843;margin:24px 0 12px;">What you get with Premium ($9/mo)</h2>

  <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:16px 0;">
    <div style="margin-bottom:12px;">
      <span style="color:#22c55e;">&#10003;</span>
      <strong> Full 1,600+ ticker CSV</strong>
      <span style="color:#94a3b8;font-size:13px;"> — every scored filing, not just top 10</span>
    </div>
    <div style="margin-bottom:12px;">
      <span style="color:#22c55e;">&#10003;</span>
      <strong> Form type + catalyst tag breakdown</strong>
      <span style="color:#94a3b8;font-size:13px;"> — updated nightly</span>
    </div>
    <div style="margin-bottom:12px;">
      <span style="color:#22c55e;">&#10003;</span>
      <strong> Squeeze radar + dark pool signals</strong>
      <span style="color:#94a3b8;font-size:13px;"> — high-short-float + block volume</span>
    </div>
    <div>
      <span style="color:#22c55e;">&#10003;</span>
      <strong> Insider cluster alerts</strong>
      <span style="color:#94a3b8;font-size:13px;"> — multiple Form 4 buys at same company</span>
    </div>
  </div>

  <div style="text-align:center;margin:24px 0;">
    <a href="https://buy.stripe.com/your-link"
       style="display:inline-block;padding:14px 36px;background:#d4a843;color:#000;font-weight:700;
              border-radius:8px;text-decoration:none;font-size:16px;">
      Upgrade to Premium — $9/mo
    </a>
  </div>

  <p style="text-align:center;color:#94a3b8;font-size:13px;">
    Or stay on the free tier — you'll still get the top 10 picks every morning.
  </p>

  <div style="text-align:center;border-top:1px solid #1e293b;margin-top:32px;padding-top:16px;font-size:12px;color:#64748b;">
    Catalyst Edge &middot; catalystedgescanner.com
  </div>
</div>""",
    },
}


def main() -> int:
    _load_env()

    smtp_cfg = {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": os.environ.get("SMTP_PORT", "587"),
        "user": os.environ.get("SMTP_USER", ""),
        "pass": os.environ.get("SMTP_PASS", ""),
        "from": os.environ.get("EMAIL_FROM", os.environ.get("SMTP_USER", "")),
        "tls": os.environ.get("SMTP_USE_TLS", "1"),
    }

    if not smtp_cfg["user"] or not smtp_cfg["pass"]:
        print("send_cheatsheet_drip: SMTP credentials not configured — skipping")
        return 0

    leads = _load_leads()
    if not leads:
        print("send_cheatsheet_drip: no leads in leads.json — skipping")
        return 0

    today = dt.date.today().isoformat()
    sent_count = 0

    for lead in leads:
        email = lead.get("email", "").strip()
        if not email:
            continue

        signup_date = lead.get("signup_date", today)
        try:
            signup = dt.date.fromisoformat(signup_date)
        except ValueError:
            signup = dt.date.today()

        day_num = (dt.date.today() - signup).days
        sent_days = set(lead.get("sent_days", []))

        if day_num not in EMAILS:
            continue
        if day_num in sent_days:
            continue

        email_data = EMAILS[day_num]
        try:
            _send_email(smtp_cfg, email, email_data["subject"], email_data["html"])
            sent_days.add(day_num)
            lead["sent_days"] = sorted(sent_days)
            sent_count += 1
            print(f"  Sent day {day_num} to {email}")
        except Exception as e:
            print(f"  Failed day {day_num} to {email}: {e}")

    _save_leads(leads)
    print(f"send_cheatsheet_drip: {sent_count} emails sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
