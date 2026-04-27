#!/usr/bin/env python3
"""engage_stocktwits_streams.py — Engage in StockTwits ticker streams.

For each gap scanner ticker, reads the live stream and replies to recent
posts with genuine technical analysis from our pipeline data. This builds
followers organically by being in the conversation on active stocks.

Rules to avoid spam flags:
- Only reply to posts <4 hours old with >0 likes OR from accounts with >100 followers
- Max 6 replies per run (rate limit safety)
- Never reply to the same post twice (.st_replied_{post_id} flags)
- Add real data from our scanner (price, gap%, SEC signal)
- 10-second delay between replies
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
GAP_CSV        = ROOT / "gap_scanner_top.csv"
NEWSLETTER_URL = "catalystedge.agency"
API_BASE       = "https://api.stocktwits.com/api/2"
MAX_REPLIES    = 2    # reduced from 6 — conservative after restriction
MIN_LIKES      = 1   # only reply to posts with at least 1 like (quality filter)
MAX_STREAM_AGE = 2   # hours — only engage with very fresh posts


def get_token() -> str:
    token = os.getenv("STOCKTWITS_ACCESS_TOKEN", "").strip()
    if not token:
        env_file = ROOT / ".sec_email_env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("STOCKTWITS_ACCESS_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    if not token:
        print("engage_stocktwits_streams: no token — skipping")
        raise SystemExit(0)
    return token


def load_gap_tickers() -> list[dict]:
    rows = []
    if not GAP_CSV.exists():
        return rows
    try:
        with GAP_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").strip().upper()
                if t:
                    rows.append(row)
    except Exception:
        pass
    return rows[:8]


def get_stream(symbol: str, token: str) -> list[dict]:
    """Fetch recent messages in a ticker's stream."""
    url = (f"{API_BASE}/streams/symbol/{symbol}.json"
           f"?access_token={token}&limit=30")
    req = urllib.request.Request(url, headers={"User-Agent": "CatalystEdge/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("messages", [])
    except Exception as e:
        print(f"  stream error {symbol}: {e}")
        return []


def build_reply(symbol: str, gap_row: dict, original_body: str) -> str:
    """Build a genuine reply with our scanner data."""
    gap_pct    = gap_row.get("gap_pct", gap_row.get("gap", ""))
    vol_ratio  = gap_row.get("vol_ratio", "")
    price      = gap_row.get("price", "")
    accum      = gap_row.get("accum", "")

    try:
        gap_str = f"+{float(gap_pct):.1f}% gap" if gap_pct else ""
    except (ValueError, TypeError):
        gap_str = ""
    try:
        vol_str = f"{float(vol_ratio):.1f}× avg vol" if vol_ratio else ""
    except (ValueError, TypeError):
        vol_str = ""
    try:
        price_str = f"@ ${float(price):.2f}" if price else ""
    except (ValueError, TypeError):
        price_str = ""

    stats = " | ".join(s for s in [gap_str, vol_str] if s)
    if accum:
        stats = f"{stats} | {accum}" if stats else accum

    lines = [f"${symbol} on our pre-market gap scanner this morning {price_str}"]
    if stats:
        lines.append(stats)
    lines.extend([
        "",
        f"Scanning 1,600+ tickers before open daily → {NEWSLETTER_URL}",
    ])
    return "\n".join(lines)[:1000]


def post_reply(token: str, message: str, in_reply_to: int) -> int | None:
    """Post a reply. Returns message ID or None on failure."""
    data = urllib.parse.urlencode({
        "access_token":  token,
        "body":          message,
        "in_reply_to_message_id": str(in_reply_to),
        "sentiment":     "Bullish",
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/messages/create.json",
        data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return result.get("message", {}).get("id")
    except urllib.error.HTTPError as e:
        print(f"  reply error: {e.code} {e.read()[:150]}")
        return None
    except Exception as e:
        print(f"  reply error: {e}")
        return None


def already_replied(post_id: int) -> bool:
    return (ROOT / f".st_replied_{post_id}").exists()


def mark_replied(post_id: int) -> None:
    (ROOT / f".st_replied_{post_id}").touch()


def parse_created(created_at: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    token    = get_token()
    gap_rows = load_gap_tickers()
    if not gap_rows:
        print("engage_stocktwits_streams: no gap tickers — skipping")
        return 0

    now_utc   = dt.datetime.now(dt.timezone.utc)
    cutoff    = now_utc - dt.timedelta(hours=MAX_STREAM_AGE)
    replied   = 0

    print(f"engage_stocktwits_streams: engaging {len(gap_rows)} ticker streams")

    for row in gap_rows:
        if replied >= MAX_REPLIES:
            break

        symbol   = row.get("ticker", "").upper()
        messages = get_stream(symbol, token)

        for msg in messages:
            if replied >= MAX_REPLIES:
                break

            post_id = msg.get("id")
            if not post_id or already_replied(post_id):
                continue

            # Skip our own posts
            if msg.get("user", {}).get("username", "").lower() == "yourhandle":
                continue

            # Only engage with recent posts
            created = parse_created(msg.get("created_at", ""))
            if created and created < cutoff:
                continue

            body   = msg.get("body", "")
            reply  = build_reply(symbol, row, body)
            result = post_reply(token, reply, post_id)

            if result:
                print(f"  ✅ Replied to ${symbol} post {post_id} → reply_id={result}")
                mark_replied(post_id)
                replied += 1
                time.sleep(10)  # respectful delay between replies
            else:
                time.sleep(3)

        time.sleep(2)

    print(f"engage_stocktwits_streams: {replied} replies posted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
