#!/usr/bin/env python3
"""send_daily_digest.py — daily Catalyst Edge digest email.

Pulls top picks from existing CSVs/JSONs:
  - Top 5 SEC catalyst calls (sec_catalyst_ranked.csv → priority_score desc)
  - Top 3 cross-border setups (cross_border_convergence.json → STRONG, then TRADE)
  - Top 3 A-grade DCFs (intl_dcf.json → top_undervalued, grade=A)

Sends a single multipart HTML+plaintext email via SMTP using stdlib.
Reads SMTP creds from .sec_email_env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
EMAIL_FROM, EMAIL_TO (default opensource@example.com).

Usage:
  python3 send_daily_digest.py                  # send to EMAIL_TO (or default)
  python3 send_daily_digest.py --to a@b.com     # override recipient
  python3 send_daily_digest.py --dry-run        # write preview to /tmp/digest_preview.html, no SMTP
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
SEC_CSV = ROOT / "sec_catalyst_ranked.csv"
COMBINED_CSV = ROOT / "combined_priority.csv"
CB_JSON = ROOT / "docs/data/cross_border_convergence.json"
DCF_JSON = ROOT / "docs/data/intl_dcf.json"
STATUS_OUT = ROOT / "docs/data/daily_digest_status.json"
LOG = ROOT / "logs/daily_digest.log"
LOG.parent.mkdir(exist_ok=True)
STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_TO = "opensource@example.com"
SITE = "https://catalystedgescanner.com"


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def write_status(payload: dict) -> None:
    payload.setdefault("last_attempt_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    STATUS_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Data loaders — all tolerant of missing/empty files

def top_sec(n: int = 5) -> list[dict]:
    if not SEC_CSV.exists():
        return []
    rows: list[dict] = []
    with SEC_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                r["_score"] = float(r.get("priority_score") or 0)
            except ValueError:
                r["_score"] = 0.0
            rows.append(r)
    rows.sort(key=lambda r: r["_score"], reverse=True)
    return rows[:n]


def top_crossborder(n: int = 3) -> list[dict]:
    if not CB_JSON.exists():
        return []
    try:
        d = json.loads(CB_JSON.read_text())
    except Exception:
        return []
    setups = d.get("top_setups") or []
    strong = [s for s in setups if s.get("conviction") == "STRONG"]
    trade = [s for s in setups if s.get("conviction") == "TRADE"]
    out = strong[:n]
    if len(out) < n:
        out += trade[: n - len(out)]
    return out


def top_dcf(n: int = 3) -> list[dict]:
    if not DCF_JSON.exists():
        return []
    try:
        d = json.loads(DCF_JSON.read_text())
    except Exception:
        return []
    rows = d.get("top_undervalued") or []
    a_grade = [r for r in rows if (r.get("grade") or "").upper() == "A"]
    a_grade.sort(key=lambda r: float(r.get("upside_pct") or 0), reverse=True)
    return a_grade[:n]


# ---------------------------------------------------------------------------
# Render

def fmt_pct(v) -> str:
    try:
        f = float(v)
        sign = "+" if f >= 0 else ""
        return f"{sign}{f:.1f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_score(v) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "—"


def render_text(today: str, sec: list[dict], cb: list[dict], dcf: list[dict]) -> str:
    lines = [
        f"Catalyst Edge daily digest · {today}",
        "=" * 56,
        "",
        f"Top {len(sec)} SEC catalyst calls",
        "-" * 56,
    ]
    for i, r in enumerate(sec, 1):
        lines.append(
            f"{i}. {r.get('ticker','?'):<7} score={fmt_score(r.get('priority_score'))}  "
            f"form={r.get('form','?')}  recency={r.get('recency_min','?')}m"
        )
    lines += ["", f"Top {len(cb)} cross-border setups", "-" * 56]
    for i, s in enumerate(cb, 1):
        lines.append(
            f"{i}. {s.get('us_ticker','?')} ↔ {s.get('foreign_ticker','?'):<10} "
            f"{s.get('conviction','?')} score={s.get('score','?')}/4  "
            f"US={fmt_pct(s.get('us_gap_pct'))}  foreign={fmt_pct(s.get('foreign_gap_pct'))}"
        )
    lines += ["", f"Top {len(dcf)} A-grade DCF picks", "-" * 56]
    for i, r in enumerate(dcf, 1):
        lines.append(
            f"{i}. {r.get('ticker','?'):<10} {r.get('country','?'):<14} "
            f"upside={fmt_pct(r.get('upside_pct'))}  sector={r.get('sector','?')}"
        )
    lines += [
        "",
        "—",
        f"Live scanner: {SITE}/scanner",
        f"Audit + methodology: {SITE}/trust",
        f"Unsubscribe: reply STOP",
    ]
    return "\n".join(lines)


def render_html(today: str, sec: list[dict], cb: list[dict], dcf: list[dict]) -> str:
    def esc(v) -> str:
        return html.escape(str(v)) if v is not None else "—"

    sec_rows = "".join(
        f"<tr>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-family:monospace'>{i:02d}</td>"
        f"<td style='padding:8px 10px;color:#e6f1ff;font-weight:600'>{esc(r.get('ticker'))}</td>"
        f"<td style='padding:8px 10px;color:#5ad7ff;font-family:monospace'>{esc(fmt_score(r.get('priority_score')))}</td>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-family:monospace;font-size:12px'>{esc(r.get('form'))}</td>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-family:monospace;font-size:12px'>{esc(r.get('recency_min'))}m</td>"
        f"</tr>"
        for i, r in enumerate(sec, 1)
    )
    cb_rows = "".join(
        f"<tr>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-family:monospace'>{i:02d}</td>"
        f"<td style='padding:8px 10px;color:#e6f1ff;font-weight:600'>{esc(s.get('us_ticker'))} ↔ {esc(s.get('foreign_ticker'))}</td>"
        f"<td style='padding:8px 10px;color:{'#5cf2a4' if s.get('conviction')=='STRONG' else '#f5c662'};font-family:monospace;font-size:12px'>"
        f"{esc(s.get('conviction'))} {esc(s.get('score'))}/4</td>"
        f"<td style='padding:8px 10px;color:#5ad7ff;font-family:monospace;font-size:12px'>{esc(fmt_pct(s.get('us_gap_pct')))}</td>"
        f"<td style='padding:8px 10px;color:#5ad7ff;font-family:monospace;font-size:12px'>{esc(fmt_pct(s.get('foreign_gap_pct')))}</td>"
        f"</tr>"
        for i, s in enumerate(cb, 1)
    )
    dcf_rows = "".join(
        f"<tr>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-family:monospace'>{i:02d}</td>"
        f"<td style='padding:8px 10px;color:#e6f1ff;font-weight:600'>{esc(r.get('ticker'))}</td>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-size:12px'>{esc(r.get('country'))}</td>"
        f"<td style='padding:8px 10px;color:#5cf2a4;font-family:monospace'>{esc(fmt_pct(r.get('upside_pct')))}</td>"
        f"<td style='padding:8px 10px;color:#9bb0c8;font-size:12px'>{esc(r.get('sector'))}</td>"
        f"</tr>"
        for i, r in enumerate(dcf, 1)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalyst Edge daily digest · {esc(today)}</title>
</head>
<body style="margin:0;padding:0;background:#04070d;color:#e6f1ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#04070d">
<tr><td align="center" style="padding:24px 12px">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%">
    <tr><td style="padding:0 0 18px">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.18em;color:#f5c662;text-transform:uppercase;margin-bottom:8px">⚡ Catalyst Edge · daily digest · {esc(today)}</div>
      <h1 style="margin:0 0 6px;font-size:26px;color:#e6f1ff;letter-spacing:-0.01em">Today's three feeds, one email.</h1>
      <p style="margin:0;color:#9bb0c8;font-size:14px;line-height:1.5">Top SEC catalysts, cross-border setups, and A-grade DCF picks — auto-generated from the same data powering the public scanner.</p>
    </td></tr>

    <tr><td style="padding:8px 0 16px">
      <div style="background:linear-gradient(180deg,#0f1c30,#070e1c);border:1px solid rgba(110,140,180,0.18);border-radius:14px;padding:16px">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.18em;color:#f5c662;text-transform:uppercase;margin-bottom:10px">Top {len(sec)} · SEC catalyst calls</div>
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;font-size:13px">
          <thead><tr><th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">#</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Ticker</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Score</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Form</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Recency</th></tr></thead>
          <tbody>{sec_rows or '<tr><td colspan="5" style="padding:10px;color:#6e8198">No SEC catalysts ranked today.</td></tr>'}</tbody>
        </table>
      </div>
    </td></tr>

    <tr><td style="padding:8px 0 16px">
      <div style="background:linear-gradient(180deg,#0f1c30,#070e1c);border:1px solid rgba(110,140,180,0.18);border-radius:14px;padding:16px">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.18em;color:#f5c662;text-transform:uppercase;margin-bottom:10px">Top {len(cb)} · cross-border setups</div>
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;font-size:13px">
          <thead><tr><th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">#</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Pair</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Conviction</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">US gap</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Foreign gap</th></tr></thead>
          <tbody>{cb_rows or '<tr><td colspan="5" style="padding:10px;color:#6e8198">No STRONG/TRADE setups in this window.</td></tr>'}</tbody>
        </table>
      </div>
    </td></tr>

    <tr><td style="padding:8px 0 16px">
      <div style="background:linear-gradient(180deg,#0f1c30,#070e1c);border:1px solid rgba(110,140,180,0.18);border-radius:14px;padding:16px">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.18em;color:#f5c662;text-transform:uppercase;margin-bottom:10px">Top {len(dcf)} · A-grade DCF picks</div>
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;font-size:13px">
          <thead><tr><th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">#</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Ticker</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Country</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Upside</th>
            <th align="left" style="padding:6px 10px;color:#6e8198;font-family:monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase">Sector</th></tr></thead>
          <tbody>{dcf_rows or '<tr><td colspan="5" style="padding:10px;color:#6e8198">No A-grade DCF picks today.</td></tr>'}</tbody>
        </table>
      </div>
    </td></tr>

    <tr><td style="padding:18px 0 0;text-align:center;border-top:1px solid rgba(110,140,180,0.18);margin-top:18px">
      <a href="{SITE}/scanner" style="display:inline-block;background:#f5c662;color:#1a1304;font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:0.16em;text-transform:uppercase;padding:11px 22px;border-radius:10px;text-decoration:none;font-weight:700">Open the scanner →</a>
    </td></tr>

    <tr><td style="padding:24px 0 0;text-align:center;color:#6e8198;font-size:11px;line-height:1.6">
      <div><a href="{SITE}/trust" style="color:#5ad7ff;text-decoration:none">Audit · methodology</a> · <a href="{SITE}/changelog" style="color:#5ad7ff;text-decoration:none">Changelog</a> · <a href="{SITE}/pricing" style="color:#5ad7ff;text-decoration:none">Pricing</a></div>
      <div style="margin-top:6px">Reply STOP to unsubscribe · not investment advice · trade at your own risk</div>
    </td></tr>
  </table>
</td></tr></table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# SMTP send

def send(msg: MIMEMultipart, host: str, port: int, user: str, pw: str, use_tls: bool) -> None:
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            smtp.login(user, pw)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(user, pw)
            smtp.send_message(msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default=None, help="Override recipient (default: EMAIL_TO env or " + DEFAULT_TO + ")")
    ap.add_argument("--dry-run", action="store_true", help="Write preview to /tmp/digest_preview.html and exit; no SMTP")
    args = ap.parse_args()

    load_env()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sec = top_sec(5)
    cb = top_crossborder(3)
    dcf = top_dcf(3)
    log(f"loaded sec={len(sec)} cb={len(cb)} dcf={len(dcf)}")

    text = render_text(today, sec, cb, dcf)
    html_body = render_html(today, sec, cb, dcf)

    subject = f"Catalyst Edge daily digest · {today}"

    if args.dry_run:
        preview = Path("/tmp/digest_preview.html")
        preview.write_text(html_body, encoding="utf-8")
        log(f"DRY-RUN preview written to {preview} ({preview.stat().st_size} bytes)")
        write_status({
            "ok": True,
            "dry_run": True,
            "subject": subject,
            "sec_count": len(sec),
            "cb_count": len(cb),
            "dcf_count": len(dcf),
            "preview_path": str(preview),
        })
        return 0

    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "0") or 0)
    user = os.environ.get("SMTP_USER", "").strip()
    pw = os.environ.get("SMTP_PASS", "").strip()
    use_tls = (os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in ("0", "false", "no"))
    sender = os.environ.get("EMAIL_FROM", "").strip() or user
    recipient = args.to or os.environ.get("EMAIL_TO", "").strip() or DEFAULT_TO

    if not (host and port and user and pw and sender):
        log("ABORT: SMTP creds incomplete in .sec_email_env")
        write_status({"ok": False, "reason": "smtp_creds_missing"})
        return 0  # non-fatal

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        send(msg, host, port, user, pw, use_tls)
        log(f"sent to={recipient} sec={len(sec)} cb={len(cb)} dcf={len(dcf)}")
        write_status({
            "ok": True,
            "subject": subject,
            "to": recipient,
            "sec_count": len(sec),
            "cb_count": len(cb),
            "dcf_count": len(dcf),
        })
        return 0
    except Exception as e:
        log(f"ABORT send: {e}")
        write_status({"ok": False, "reason": str(e)[:200], "to": recipient})
        return 0  # non-fatal in autonomous loop


if __name__ == "__main__":
    sys.exit(main())
