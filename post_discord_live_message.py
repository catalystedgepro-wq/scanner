#!/usr/bin/env python3
"""post_discord_live_message.py — Live pinned watchlist message in Discord.

First run: creates a #📊-live-watchlist text channel, posts the watchlist
           embed, pins it, and saves channel_id + message_id to config.
Every run: edits the same pinned message with fresh prices.

Runs every 5 min via GitHub Actions (*/5 8-23 * * 1-5).
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

YAHOO_CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1m&range=1d"
)
YAHOO_PREMARKET = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1m&range=1d&prePost=true"
)

MAX_SLOTS  = 10
CHANNEL_NAME = "📊-live-watchlist"

# Embed colors
COLOR_LIVE    = 0x00FF88   # green — market open
COLOR_PRE     = 0xFFAA00   # amber — pre-market
COLOR_CLOSED  = 0xFF4444   # red   — market closed


# ── Discord API helpers ───────────────────────────────────────────────────────

def discord(method: str, endpoint: str, data: dict | None = None) -> dict | list | None:
    body = json.dumps(data).encode() if data is not None else None
    req  = urllib.request.Request(
        f"{BASE}{endpoint}", data=body, method=method, headers=HEADERS
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 429:
            try:
                retry = json.loads(e.read()).get("retry_after", 5)
            except Exception:
                retry = 5
            print(f"  rate limited — waiting {retry:.1f}s")
            time.sleep(float(retry) + 0.5)
            return None
        body_text = ""
        try:
            body_text = e.read().decode()[:200]
        except Exception:
            pass
        print(f"  {method} {endpoint} → {e.code}: {body_text}")
        return None
    except Exception as e:
        print(f"  {method} {endpoint} error: {e}")
        return None


# ── ET time helpers ───────────────────────────────────────────────────────────

def et_now() -> dt.datetime:
    utc      = dt.datetime.now(dt.timezone.utc)
    march    = dt.datetime(utc.year, 3,  1, tzinfo=dt.timezone.utc)
    november = dt.datetime(utc.year, 11, 1, tzinfo=dt.timezone.utc)
    dst_start = march    + dt.timedelta(days=(6 - march.weekday())    % 7 + 7)
    dst_end   = november + dt.timedelta(days=(6 - november.weekday()) % 7)
    offset = -4 if dst_start <= utc < dst_end else -5
    return utc + dt.timedelta(hours=offset)


def market_state() -> str:
    """Returns 'pre', 'open', or 'closed'."""
    now = et_now()
    if now.weekday() >= 5:
        return "closed"
    t = now.time()
    if dt.time(4, 0) <= t < dt.time(9, 30):
        return "pre"
    if dt.time(9, 30) <= t <= dt.time(20, 0):
        return "open"
    return "closed"


# ── Yahoo Finance quotes ──────────────────────────────────────────────────────

def fetch_quote_v8(symbol: str, pre: bool = False) -> dict | None:
    """Fetch live quote for one ticker via v8 chart endpoint."""
    url = (YAHOO_PREMARKET if pre else YAHOO_CHART).format(symbol=symbol.upper())
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        meta   = result.get("meta", {})
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        volumes = result.get("indicators", {}).get("quote", [{}])[0].get("volume", [])

        # Current price = last non-None close
        price = None
        for c in reversed(closes):
            if c is not None:
                price = c
                break
        if price is None:
            price = meta.get("regularMarketPrice", 0)

        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        chg_pct    = ((price - prev_close) / prev_close * 100) if prev_close else 0

        # Total volume today
        vol = sum(v for v in volumes if v is not None)

        return {
            "regularMarketPrice":         price,
            "regularMarketChangePercent": chg_pct,
            "regularMarketVolume":        vol,
            "preMarketPrice":             meta.get("preMarketPrice", price),
            "preMarketChangePercent":     meta.get("preMarketChangePercent", chg_pct),
        }
    except Exception as e:
        print(f"  quote error {symbol}: {e}")
        return None


def fetch_quotes(tickers: list[str], pre: bool = False) -> dict[str, dict]:
    results = {}
    for symbol in tickers:
        q = fetch_quote_v8(symbol, pre=pre)
        if q:
            results[symbol] = q
        time.sleep(0.2)
    return results


# ── Load top tickers ──────────────────────────────────────────────────────────

def load_top_tickers() -> list[str]:
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
    src = TICKER_FILE if TICKER_FILE.exists() else SEC_FILE
    if src.exists():
        with src.open(encoding="utf-8") as f:
            for line in f:
                t = line.strip().upper()
                if t:
                    tickers.append(t)
    return tickers[:MAX_SLOTS]


# ── Build Discord embed ───────────────────────────────────────────────────────

def build_embed(tickers: list[str], quotes: dict[str, dict], state: str, now_et: dt.datetime) -> dict:
    premarket = (state == "pre")

    rows = []
    for ticker in tickers:
        q = quotes.get(ticker)
        if not q:
            rows.append(f"⬜  `{ticker:<6}`  —")
            continue

        if premarket:
            price = float(q.get("preMarketPrice") or q.get("regularMarketPrice") or 0)
            chg   = float(q.get("preMarketChangePercent") or 0)
            icon  = "🌙"
        else:
            price = float(q.get("regularMarketPrice") or 0)
            chg   = float(q.get("regularMarketChangePercent") or 0)
            icon  = "📈" if chg >= 0 else "📉"

        vol = q.get("regularMarketVolume") or 0
        vol_str = f"{vol/1_000_000:.1f}M" if vol >= 1_000_000 else f"{vol/1_000:.0f}K"

        sign = "+" if chg >= 0 else ""
        rows.append(f"{icon}  `{ticker:<6}`  **${price:.2f}**  {sign}{chg:.1f}%   Vol {vol_str}")

    # Pad to MAX_SLOTS
    while len(rows) < MAX_SLOTS:
        rows.append("⬜  `——————`  —")

    if state == "closed":
        title  = "🔴  Market Closed"
        color  = COLOR_CLOSED
        desc   = "_Market is closed. Watchlist refreshes at 4:00 AM ET._"
        footer = f"Catalyst Edge • catalystedge.agency • {now_et.strftime('%I:%M %p ET')}"
        return {
            "embeds": [{
                "title":       title,
                "description": desc,
                "color":       color,
                "footer":      {"text": footer},
            }]
        }

    label  = "🌙  PRE-MARKET GAP WATCHLIST" if premarket else "📊  LIVE GAP WATCHLIST"
    color  = COLOR_PRE if premarket else COLOR_LIVE
    desc   = "\n".join(rows)
    footer = f"Catalyst Edge • catalystedge.agency • t.me/CatalystEdgePro • Updated {now_et.strftime('%I:%M %p ET')}"

    return {
        "embeds": [{
            "title":       label,
            "description": desc,
            "color":       color,
            "footer":      {"text": footer},
            "timestamp":   dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }]
    }


# ── Channel / message bootstrap ───────────────────────────────────────────────

def ensure_text_channel(guild_id: str, category_id: str | None) -> str:
    """Return existing or newly created text channel ID for the live watchlist."""
    channels = discord("GET", f"/guilds/{guild_id}/channels") or []
    for ch in channels:
        if isinstance(ch, dict) and ch.get("name") == CHANNEL_NAME and ch.get("type") == 0:
            print(f"  Found existing channel: {ch['id']}")
            return ch["id"]

    payload: dict = {"name": CHANNEL_NAME, "type": 0}
    if category_id:
        payload["parent_id"] = category_id
    ch = discord("POST", f"/guilds/{guild_id}/channels", payload)
    if ch and "id" in ch:
        print(f"  Created channel #{CHANNEL_NAME}: {ch['id']}")
        return ch["id"]
    raise RuntimeError("Failed to create watchlist text channel")


def post_and_pin(channel_id: str, embed_payload: dict) -> str:
    """Post the embed and pin it. Returns message_id."""
    msg = discord("POST", f"/channels/{channel_id}/messages", embed_payload)
    if not msg or "id" not in msg:
        raise RuntimeError("Failed to post watchlist message")
    message_id = msg["id"]
    discord("PUT", f"/channels/{channel_id}/pins/{message_id}")
    print(f"  Posted and pinned message: {message_id}")
    return message_id


def edit_message(channel_id: str, message_id: str, embed_payload: dict) -> bool:
    result = discord("PATCH", f"/channels/{channel_id}/messages/{message_id}", embed_payload)
    return result is not None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if not TOKEN:
        print("post_discord_live_message: DISCORD_BOT_TOKEN not set — skipping")
        return 0

    if not CONFIG_FILE.exists():
        print("post_discord_live_message: no config file — run setup_discord_watchlist.py first")
        return 1

    config   = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    guild_id = config.get("guild_id", "")
    if not guild_id:
        print("post_discord_live_message: no guild_id in config")
        return 1

    now_et = et_now()
    state  = market_state()
    print(f"post_discord_live_message: {now_et.strftime('%H:%M ET')} — state={state}")

    # Load tickers & quotes
    if state == "closed":
        tickers = []
        quotes  = {}
    else:
        tickers = load_top_tickers()
        quotes  = fetch_quotes(tickers, pre=(state == "pre")) if tickers else {}
        print(f"  {len(tickers)} tickers, {len(quotes)} quotes")

    embed_payload = build_embed(tickers, quotes, state, now_et)

    # Ensure text channel exists
    channel_id = config.get("live_message_channel_id")
    if not channel_id:
        category_id = config.get("category_id")
        channel_id  = ensure_text_channel(guild_id, category_id)
        config["live_message_channel_id"] = channel_id
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Ensure pinned message exists
    message_id = config.get("live_message_id")
    if not message_id:
        message_id = post_and_pin(channel_id, embed_payload)
        config["live_message_id"] = message_id
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print("post_discord_live_message: initial message posted and pinned")
        return 0

    # Edit existing message
    if edit_message(channel_id, message_id, embed_payload):
        print(f"post_discord_live_message: message updated ({state})")
    else:
        print("post_discord_live_message: edit failed — will retry next cycle")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
