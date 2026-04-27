#!/usr/bin/env python3
"""post_to_telegram.py — Post daily SEC catalyst picks to Telegram channel.

Posts a formatted daily picks message to @CatalystEdgeDaily each morning.
Gated by .telegram_posted_{date} flag (once per day).

Required env vars:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHANNEL  (e.g. @CatalystEdgeDaily)
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
SCANNER_URL    = "https://catalystedgescanner.com"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
AGENCY_URL     = "https://www.catalystedge.agency"
DISCORD_URL    = "https://discord.gg/8aJEHghHVy"


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def load_polymarket() -> dict | None:
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        age_h = (datetime.datetime.now(datetime.timezone.utc) -
                 datetime.datetime.fromisoformat(data.get("generated_at", "1970-01-01T00:00:00+00:00"))
                 ).total_seconds() / 3600
        if age_h > 36:
            return None
        sigs = [s for s in data.get("signals", []) if 10 <= s.get("probability", 0) <= 90]
        return min(sigs, key=lambda x: abs(x["probability"] - 50)) if sigs else None
    except Exception:
        return None


def get_signal(ticker: str) -> str:
    tag_map = [
        ("fda_approval",         "FDA approval"),
        ("fda_clearance",        "FDA clearance"),
        ("definitive_agreement", "merger agreement"),
        ("contract_award",       "contract award"),
        ("raises_guidance",      "raised guidance"),
        ("record_revenue",       "record revenue"),
        ("earnings_beat",        "earnings beat"),
        ("share_repurchase",     "buyback"),
        ("insider_buy",          "insider buying"),
        ("special_dividend",     "special dividend"),
        ("patent",               "patent filing"),
    ]
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv"]:
        for row in read_csv(ROOT / fname):
            if row.get("ticker", "").upper() == ticker.upper():
                tags = (row.get("tags") or "").lower()
                for key, label in tag_map:
                    if key in tags:
                        return label
                form_map = {"8-K": "8-K event", "4": "Form 4 insider buy",
                            "SC 13D": "activist 13D", "6-K": "6-K filing"}
                return form_map.get(row.get("form", ""), "SEC catalyst")
    return "SEC catalyst"


# ── Message builder ───────────────────────────────────────────────────────────

def build_message(picks: dict) -> str:
    today    = datetime.date.today().strftime("%b %-d, %Y")
    top5     = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    total    = picks.get("total_combined", 0)

    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    # Pick lines
    emojis = ["🥇", "📌", "📌", "📌", "📌"]
    pick_lines = []
    for i, t in enumerate(top5[:5]):
        signal = get_signal(t)
        em = emojis[i] if i < len(emojis) else "📌"
        pick_lines.append(f"{em} ${t} — {signal}")

    picks_text = "\n".join(pick_lines)

    # Squeeze radar
    squeeze_rows = read_csv(ROOT / "squeeze_candidates.csv")
    coiled = [r.get("ticker", "").upper() for r in squeeze_rows
              if r.get("stage") in ("COILED", "IGNITION")][:3]
    squeeze_line = ""
    if coiled:
        squeeze_line = f"\n🔥 *Squeeze Radar:* {' | '.join('$'+t for t in coiled)}"

    # Polymarket
    pm = load_polymarket()
    pm_line = ""
    if pm:
        pm_line = (f"\n\n🎲 *Polymarket:* {pm['probability']:.0f}% odds on "
                   f"\"{pm['title'][:55]}\"\n"
                   f"→ {pm['impact']}")

    message = (
        f"⚡ *CATALYST EDGE — {today}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Today's top picks from {total}+ SEC filings:\n\n"
        f"{picks_text}"
        f"{squeeze_line}"
        f"{pm_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥️ Live Scanner → {SCANNER_URL}\n"
        f"📬 Newsletter → {NEWSLETTER_URL}\n"
        f"💬 Discord → {DISCORD_URL}\n"
        f"📲 Share this channel → @CatalystEdgePro\n\n"
        f"#fintwit #stocks #SEC #stockstowatch #daytrading #pennystocks"
    )
    return message


# ── Telegram sender ───────────────────────────────────────────────────────────

def send_message(token: str, channel: str, text: str) -> bool:
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id":    channel,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if data.get("ok"):
            msg_id = data.get("result", {}).get("message_id", "")
            print(f"  Telegram: posted message_id={msg_id}")
            return True
        else:
            print(f"  Telegram error: {data.get('description', 'unknown')}")
            return False
    except Exception as e:
        print(f"  Telegram send error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    stamp = datetime.date.today().isoformat()
    flag  = ROOT / f".telegram_posted_{stamp}"
    if flag.exists():
        print(f"post_to_telegram: already posted today ({stamp}) — skipping")
        return 0

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()

    if not token or not channel:
        print("post_to_telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL not set — skipping")
        return 0

    picks = load_picks()
    if not picks:
        print("post_to_telegram: no picks found — skipping")
        return 0

    message = build_message(picks)
    print(f"post_to_telegram: sending to {channel}")
    print(f"\n{message}\n")

    if send_message(token, channel, message):
        flag.touch()
        print(f"post_to_telegram: done")
        return 0
    else:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
