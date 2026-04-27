#!/usr/bin/env python3
"""post_eod_telegram_recap.py — Post EOD performance recap to Telegram.

Runs at 4:15 PM ET via the eod-recap GitHub Actions job.
Reads gap_alert_log.csv for alerts fired today, fetches closing prices from
Yahoo Finance, calculates gain/loss from alert price to close, and posts a
formatted summary to the Telegram channel.

Required env vars:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHANNEL

Optional (loaded from .sec_email_env as fallback for local testing):
  NEWSLETTER_URL
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
ALERT_LOG      = ROOT / "gap_alert_log.csv"
SCANNER_URL    = "https://catalystedgescanner.com"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
YAHOO_QUOTE    = (
    "https://query1.finance.yahoo.com/v7/finance/quote"
    "?symbols={symbol}"
    "&fields=regularMarketPrice,regularMarketPreviousClose,shortName"
)


# ── Env loader ───────────────────────────────────────────────────────────────

def _load_env() -> None:
    env_file = ROOT / ".sec_email_env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v.strip()


# ── Flag gating ──────────────────────────────────────────────────────────────

def already_posted(date_str: str) -> bool:
    return (ROOT / f".telegram_eod_{date_str}").exists()


def mark_posted(date_str: str) -> None:
    (ROOT / f".telegram_eod_{date_str}").touch()


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_today_alerts() -> list[dict]:
    """Return alert rows for today from gap_alert_log.csv."""
    today = dt.date.today().isoformat()
    if not ALERT_LOG.exists():
        return []
    try:
        with ALERT_LOG.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return [r for r in rows if r.get("alert_date") == today]
    except Exception:
        return []


def fetch_close_price(symbol: str) -> float | None:
    """Fetch current/closing price from Yahoo Finance."""
    url = YAHOO_QUOTE.format(symbol=symbol)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("quoteResponse", {}).get("result", [])
        if results:
            return float(results[0].get("regularMarketPrice") or 0) or None
    except Exception:
        pass
    return None


# ── Message builder ───────────────────────────────────────────────────────────

def build_recap_message(alerts: list[dict], today_str: str) -> str:
    """Build the EOD recap Telegram message."""
    today_label = dt.date.today().strftime("%b %-d, %Y")

    lines: list[str] = [
        f"\U0001f4ca EOD RECAP -- {today_label}",
        "",
        "Today's gap alerts vs close:",
        "",
    ]

    wins    = 0
    losses  = 0
    results = []

    for row in alerts:
        ticker = row.get("ticker", "").upper()
        try:
            alert_price = float(row.get("alert_price") or 0)
            gap_pct     = float(row.get("gap_pct") or 0)
        except (TypeError, ValueError):
            continue

        if not ticker or alert_price <= 0:
            continue

        close = fetch_close_price(ticker)
        if close and close > 0 and alert_price > 0:
            actual_pct = (close - alert_price) / alert_price * 100
            if actual_pct >= 0:
                wins += 1
                icon = "\U0001f7e2"
                result_str = f"+{actual_pct:.0f}% \u2705"
            else:
                losses += 1
                icon = "\U0001f534"
                result_str = f"{actual_pct:.0f}% \u274c"
            results.append(
                f"{icon} ${ticker} +{gap_pct:.0f}% alert -> closed {result_str}"
            )
        else:
            results.append(
                f"\u26aa ${ticker} +{gap_pct:.0f}% alert -> close unavailable"
            )

    if results:
        lines.extend(results)
        lines.append("")
        total = wins + losses
        if total > 0:
            acc_str = f"{wins}/{total} ({100 * wins // total}%)"
        else:
            acc_str = "—"
        lines.append(f"Scanner accuracy today: {acc_str}")
    else:
        lines.append("No gap alerts fired today.")
        lines.append("")
        lines.append("The scanner ran but no setups met our thresholds.")
        lines.append("Pre-market scan resumes at 4:00 AM ET tomorrow.")

    lines.extend([
        "",
        "\u2501" * 20,
        f"\U0001f5a5\ufe0f Live Scanner -> {SCANNER_URL}",
        f"\U0001f4ec Tomorrow's picks -> {NEWSLETTER_URL}",
        "\U0001f4f2 Live alerts -> @CatalystEdgePro",
    ])

    return "\n".join(lines)


# ── Telegram sender ───────────────────────────────────────────────────────────

def send_telegram(token: str, channel: str, text: str) -> bool:
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id":    channel,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            msg_id = result.get("result", {}).get("message_id", "")
            print(f"  Telegram EOD recap posted message_id={msg_id}")
            return True
        print(f"  Telegram error: {result.get('description', 'unknown')}")
        return False
    except Exception as e:
        print(f"  Telegram send error: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    _load_env()

    today_str = dt.date.today().isoformat()

    if already_posted(today_str):
        print(f"post_eod_telegram_recap: already posted today ({today_str}) — skipping")
        return 0

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()

    if not token or not channel:
        print("post_eod_telegram_recap: TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL not set — skipping")
        return 0

    alerts  = load_today_alerts()
    message = build_recap_message(alerts, today_str)

    print(f"post_eod_telegram_recap: sending recap ({len(alerts)} alerts today)")
    print(f"\n{message}\n")

    if send_telegram(token, channel, message):
        mark_posted(today_str)
        print("post_eod_telegram_recap: done")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
