#!/usr/bin/env python3
"""post_discord_watchlist.py — Update Discord voice channel watchlist with live prices.

Runs every 5 min via GitHub Actions. Reads top gap plays from gap_scanner_top.csv,
fetches live Yahoo Finance quotes, and renames the 10 watchlist voice channels.

Channels appear in the left sidebar of Discord as:
  📊 LIVE WATCHLIST
    📈 OLPX • $2.01 • +50.0%
    📈 VSA  • $1.37 • +150%
    ...

Discord rate limit: 2 channel renames per 10 minutes per channel.
We stagger updates with a small delay to stay within limits.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT        = Path(__file__).parent
CONFIG_FILE = ROOT / "discord_watchlist_config.json"
GAP_CSV     = ROOT / "gap_scanner_top.csv"
TICKER_FILE = ROOT / "penny_universe.txt"
SEC_FILE    = ROOT / "sec_catalyst_tickers.txt"
TOKEN       = os.environ.get("DISCORD_BOT_TOKEN", "")
BASE        = "https://discord.com/api/v10"

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type":  "application/json",
    "User-Agent":    "CatalystEdge/1.0",
}

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v7/finance/quote"
    "?symbols={symbols}"
    "&fields=regularMarketPrice,regularMarketPreviousClose,"
    "regularMarketChangePercent,preMarketPrice,preMarketChangePercent,"
    "regularMarketVolume,averageDailyVolume3Month,shortName"
)

MAX_SLOTS   = 10
MIN_PRICE   = 0.50
MAX_PRICE   = 10.00
MIN_VOLUME  = 50_000


# ── Discord API ───────────────────────────────────────────────────────────────

def rename_channel(channel_id: str, name: str) -> bool:
    """Rename a Discord voice channel. Returns True on success."""
    # Discord channel names: max 100 chars, no special chars except - and spaces
    safe = name[:100]
    body = json.dumps({"name": safe}).encode()
    req  = urllib.request.Request(
        f"{BASE}/channels/{channel_id}",
        data=body, method="PATCH", headers=HEADERS,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # Rate limited — back off
            try:
                retry = json.loads(e.read()).get("retry_after", 5)
            except Exception:
                retry = 5
            print(f"  rate limited — waiting {retry:.1f}s")
            time.sleep(float(retry) + 0.5)
            return False
        print(f"  rename error {channel_id}: {e.code}")
        return False
    except Exception as e:
        print(f"  rename error {channel_id}: {e}")
        return False


# ── Yahoo Finance live quotes ─────────────────────────────────────────────────

def fetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """Returns {ticker: quote_dict}."""
    results = {}
    for i in range(0, len(tickers), 80):
        chunk = tickers[i:i + 80]
        url   = YAHOO_URL.format(symbols=",".join(chunk))
        req   = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read())
            for q in data.get("quoteResponse", {}).get("result", []):
                sym = q.get("symbol", "").upper()
                if sym:
                    results[sym] = q
        except Exception as e:
            print(f"  quote fetch error: {e}")
        time.sleep(0.3)
    return results


# ── DST-aware ET time ─────────────────────────────────────────────────────────

def et_now() -> dt.datetime:
    utc = dt.datetime.now(dt.timezone.utc)
    march    = dt.datetime(utc.year, 3,  1, tzinfo=dt.timezone.utc)
    november = dt.datetime(utc.year, 11, 1, tzinfo=dt.timezone.utc)
    dst_start = march    + dt.timedelta(days=(6 - march.weekday())    % 7 + 7)
    dst_end   = november + dt.timedelta(days=(6 - november.weekday()) % 7)
    offset = -4 if dst_start <= utc < dst_end else -5
    return utc + dt.timedelta(hours=offset)


def is_market_hours() -> bool:
    now = et_now()
    return now.weekday() < 5 and dt.time(4, 0) <= now.time() <= dt.time(20, 0)


# ── Load top tickers from gap scanner ────────────────────────────────────────

def load_top_tickers() -> list[str]:
    """Load tickers from gap_scanner_top.csv, fall back to penny universe."""
    tickers = []
    if GAP_CSV.exists():
        try:
            with GAP_CSV.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker", "").strip().upper()
                    if t:
                        tickers.append(t)
        except Exception:
            pass
    if tickers:
        return tickers[:MAX_SLOTS]

    # Fallback: first N from penny universe
    src = TICKER_FILE if TICKER_FILE.exists() else SEC_FILE
    if src.exists():
        with src.open(encoding="utf-8") as f:
            for line in f:
                t = line.strip().upper()
                if t:
                    tickers.append(t)
    return tickers[:MAX_SLOTS]


# ── Format channel name ───────────────────────────────────────────────────────

def format_channel(ticker: str, q: dict, premarket: bool) -> str:
    try:
        if premarket:
            price  = float(q.get("preMarketPrice")           or q.get("regularMarketPrice") or 0)
            chg    = float(q.get("preMarketChangePercent")   or 0)
            prefix = "🌙"
        else:
            price  = float(q.get("regularMarketPrice")       or 0)
            chg    = float(q.get("regularMarketChangePercent") or 0)
            prefix = "📈" if chg >= 0 else "📉"

        sign = "+" if chg >= 0 else ""
        return f"{prefix} {ticker} ╸ ${price:.2f} ╸ {sign}{chg:.1f}%"
    except Exception:
        return f"📊 {ticker}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if not TOKEN:
        print("post_discord_watchlist: DISCORD_BOT_TOKEN not set — skipping")
        return 0

    if not CONFIG_FILE.exists():
        print("post_discord_watchlist: no config file — run setup_discord_watchlist.py first")
        return 1

    config      = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    channel_ids = config.get("channel_ids", [])
    if not channel_ids:
        print("post_discord_watchlist: no channel IDs in config")
        return 1

    now_et    = et_now()
    premarket = now_et.weekday() < 5 and dt.time(4, 0) <= now_et.time() < dt.time(9, 30)

    print(f"post_discord_watchlist: updating watchlist @ {now_et.strftime('%H:%M ET')} "
          f"({'pre-market' if premarket else 'market hours'})")

    if not is_market_hours():
        # Outside trading hours — show "Market Closed" in first slot
        rename_channel(channel_ids[0], "🔴 Market Closed")
        for cid in channel_ids[1:]:
            rename_channel(cid, "╸ ╸ ╸ ╸ ╸ ╸ ╸ ╸")
            time.sleep(1.5)
        print("  outside market hours — showing closed state")
        return 0

    tickers = load_top_tickers()
    if not tickers:
        print("  no tickers found")
        return 0

    print(f"  fetching live quotes for {len(tickers)} tickers...")
    quotes = fetch_quotes(tickers)

    # Build slot names
    slots: list[str] = []
    for ticker in tickers:
        q = quotes.get(ticker)
        if q:
            slots.append(format_channel(ticker, q, premarket))
        else:
            slots.append(f"📊 {ticker}")

    # Pad remaining slots
    while len(slots) < len(channel_ids):
        slots.append("╸ ╸ ╸ ╸ ╸ ╸ ╸ ╸")

    # Update each channel — stagger to respect rate limits
    updated = 0
    for cid, name in zip(channel_ids, slots):
        print(f"  → {name}")
        if rename_channel(cid, name):
            updated += 1
        time.sleep(1.5)   # ~1.5s between renames stays well within rate limits

    print(f"post_discord_watchlist: {updated}/{len(channel_ids)} channels updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
