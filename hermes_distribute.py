#!/usr/bin/env python3
"""
hermes_distribute.py — Bridge between SEC pipeline output and Hermes gateway.

Reads pipeline data (newsletter_picks.json, squeeze_candidates.csv, convergence_alerts.csv)
and posts formatted content to Telegram and Discord via their APIs directly.

This replaces the fragile Playwright-based posting for API-native platforms.
Called by Hermes cron or run_social_posts.sh.

Usage:
    python3 hermes_distribute.py                  # post to all API platforms
    python3 hermes_distribute.py --telegram       # Telegram only
    python3 hermes_distribute.py --discord        # Discord only
    python3 hermes_distribute.py --dry-run        # preview without posting
"""

import json
import csv
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent
PICKS_JSON = WORKSPACE / "newsletter_picks.json"
SQUEEZE_CSV = WORKSPACE / "squeeze_candidates.csv"
CONVERGENCE_CSV = WORKSPACE / "convergence_alerts.csv"

# Load from .sec_email_env
def load_env():
    env_file = WORKSPACE / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

def load_picks():
    if not PICKS_JSON.exists():
        return {}
    try:
        return json.loads(PICKS_JSON.read_text())
    except Exception:
        return {}

def parse_csv(path):
    if not path.exists():
        return []
    lines = path.read_text().strip().split("\n")
    if len(lines) < 2:
        return []
    reader = csv.DictReader(lines)
    return list(reader)

def build_telegram_message(picks, squeeze_rows, convergence_rows):
    date = datetime.now().strftime("%B %d, %Y")
    top_pick = picks.get("top_pick", "N/A")
    total = picks.get("total_combined", 0)
    top5 = picks.get("top5_tickers", [])[:5]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    m = int(picks.get("moat_count", 0))
    total_picks = g + v + m

    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:5]
    conv = [r for r in convergence_rows if r.get("conviction_level") in ("HIGH", "ELEVATED")][:4]

    lines = []
    lines.append(f"\U0001F4CA *Daily SEC Catalyst Scan — {date}*")
    lines.append(f"Screened *{total}* tickers across 8-K, Form 4, S-3 filings")
    lines.append(f"\U0001F4A5 *{g}* Gapper · *{v}* Deep Value · *{m}* Wide Moat")
    lines.append("")

    lines.append("\U0001F3AF *Top Picks*")
    if top5:
        for t in top5:
            lines.append(f"  • *${t}*")
    else:
        lines.append(f"  • *${top_pick}*")
    lines.append("")

    if coiled:
        lines.append("\U0001F525 *Squeeze Radar*")
        for r in coiled:
            si = f"SI {r.get('short_pct_float', '?')}%" if r.get("short_pct_float") else ""
            dtc = f"DTC {r.get('days_to_cover', '?')}d" if r.get("days_to_cover") else ""
            detail = " · ".join(filter(None, [si, dtc]))
            lines.append(f"  • *${r.get('ticker', '?')}* `{r.get('stage', '?')}` — {detail}")
        lines.append("")

    if conv:
        lines.append("\U0001F4A1 *Convergence Alerts*")
        for r in conv:
            signals = (r.get("signals_fired", "") or "").replace(";", " · ")
            lines.append(f"  • *${r.get('ticker', '?')}* score {r.get('convergence_score', '—')} — {signals}")
        lines.append("")

    lines.append("—")
    lines.append(f"\U0001F4E8 Full breakdown: https://catalystedge.agency")
    lines.append(f"\U0001F916 Talk to Catalyst AI: https://www.catalystedge.agency/")
    lines.append("")
    lines.append("_Not financial advice. Do your own DD._")

    return "\n".join(lines)

def build_discord_message(picks, squeeze_rows, convergence_rows):
    date = datetime.now().strftime("%B %d, %Y")
    top_pick = picks.get("top_pick", "N/A")
    total = picks.get("total_combined", 0)
    top5 = picks.get("top5_tickers", [])[:5]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    m = int(picks.get("moat_count", 0))

    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:5]
    conv = [r for r in convergence_rows if r.get("conviction_level") in ("HIGH", "ELEVATED")][:4]

    lines = []
    lines.append(f"# Daily SEC Catalyst Scan — {date}")
    lines.append(f"Screened **{total}** tickers across 8-K, Form 4, S-3 filings")
    lines.append(f"**{g}** Gapper · **{v}** Deep Value · **{m}** Wide Moat")
    lines.append("")

    lines.append("## Top Picks")
    if top5:
        for t in top5:
            lines.append(f"- **${t}**")
    else:
        lines.append(f"- **${top_pick}**")
    lines.append("")

    if coiled:
        lines.append("## Squeeze Radar")
        for r in coiled:
            si = f"SI {r.get('short_pct_float', '?')}%" if r.get("short_pct_float") else ""
            dtc = f"DTC {r.get('days_to_cover', '?')}d" if r.get("days_to_cover") else ""
            detail = " · ".join(filter(None, [si, dtc]))
            lines.append(f"- **${r.get('ticker', '?')}** `{r.get('stage', '?')}` — {detail}")
        lines.append("")

    if conv:
        lines.append("## Convergence Alerts")
        for r in conv:
            signals = (r.get("signals_fired", "") or "").replace(";", " · ")
            lines.append(f"- **${r.get('ticker', '?')}** score {r.get('convergence_score', '—')} — {signals}")
        lines.append("")

    lines.append("---")
    lines.append("Full breakdown: <https://catalystedge.agency>")
    lines.append("*Not financial advice. Do your own DD.*")

    return "\n".join(lines)

def post_telegram(message, dry_run=False):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    channel = os.environ.get("TELEGRAM_CHANNEL", "@CatalystEdgeDaily")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return False

    if dry_run:
        print(f"\n--- TELEGRAM ({channel}) ---")
        print(message)
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": channel,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "false",
    }).encode()

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"Telegram: posted to {channel}")
                return True
            else:
                print(f"Telegram error: {result}")
                return False
    except Exception as e:
        print(f"Telegram failed: {e}")
        return False

def post_discord(message, dry_run=False):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL not set")
        return False

    if dry_run:
        print(f"\n--- DISCORD ---")
        print(message)
        return True

    # Discord webhook limit is 2000 chars
    if len(message) > 1950:
        message = message[:1950] + "\n..."

    data = json.dumps({"content": message}).encode()

    try:
        req = urllib.request.Request(
            webhook_url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 204):
                print("Discord: posted via webhook")
                return True
            else:
                print(f"Discord error: HTTP {resp.status}")
                return False
    except Exception as e:
        print(f"Discord failed: {e}")
        return False

def main():
    load_env()
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    do_telegram = "--telegram" in args or not (args - {"--dry-run"})
    do_discord = "--discord" in args or not (args - {"--dry-run"})

    picks = load_picks()
    squeeze_rows = parse_csv(SQUEEZE_CSV)
    convergence_rows = parse_csv(CONVERGENCE_CSV)

    if not picks:
        print("WARNING: newsletter_picks.json empty or missing — posting with minimal data")

    success = False

    if do_telegram:
        msg = build_telegram_message(picks, squeeze_rows, convergence_rows)
        if post_telegram(msg, dry_run):
            success = True

    if do_discord:
        msg = build_discord_message(picks, squeeze_rows, convergence_rows)
        if post_discord(msg, dry_run):
            success = True

    if success or dry_run:
        print("\nDistribution complete.")
    else:
        print("\nAll distribution attempts failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
