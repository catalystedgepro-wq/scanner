#!/usr/bin/env python3
"""Track WallStreetBets mention velocity for pipeline tickers.

Uses Reddit's public JSON API — no authentication required.
Counts posts mentioning each ticker in the last 24h on r/wallstreetbets.

Low mention count + high squeeze score = Stage 1 (best entry).
Rising mention count = Stage 2 (ignition).

Outputs: wsb_mentions.csv
Columns: ticker, mention_count_24h, mention_velocity, top_post_title,
         top_post_score, sentiment_label
"""
from __future__ import annotations

import csv
import datetime
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT       = Path(__file__).parent
SHORT_CSV  = ROOT / "short_data.csv"
OUT_CSV    = ROOT / "wsb_mentions.csv"
CACHE_FILE = ROOT / ".wsb_mentions_cache.json"
CACHE_TTL  = 3 * 3600  # refresh every 3 hours

REDDIT_SEARCH = (
    "https://www.reddit.com/r/wallstreetbets/search.json"
    "?q={ticker}&sort=new&restrict_sr=1&limit=100&t=day"
)
HEADERS = {
    "User-Agent": "CatalystEdge/1.0 (research bot; contact opensource@example.com)",
    "Accept": "application/json",
}

BULLISH = ["bull", "moon", "calls", "long", "buy", "squeeze", "rocket",
           "yolo", "pump", "rip", "print", "tendies", "catalyst"]
BEARISH = ["bear", "puts", "short", "crash", "sell", "dump", "rug",
           "bag", "down", "fall", "fade"]

FIELDNAMES = [
    "ticker", "mention_count_24h", "sentiment_label",
    "top_post_title", "top_post_score",
]


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_cache(c: dict) -> None:
    CACHE_FILE.write_text(json.dumps(c))


def fetch_wsb(ticker: str) -> dict:
    url = REDDIT_SEARCH.format(ticker=ticker)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())

        posts = data.get("data", {}).get("children", [])
        now   = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()

        mentions = 0
        bull_count, bear_count = 0, 0
        top_title, top_score = "", 0

        for p in posts:
            d = p.get("data", {})
            # Must mention the ticker as a word (avoid false positives)
            title  = d.get("title", "")
            body   = d.get("selftext", "")
            full   = (title + " " + body).lower()
            created = float(d.get("created_utc", 0))

            # Only last 24h
            if now - created > 86400:
                continue

            # Ticker must appear as standalone word
            if not re.search(rf"\b{re.escape(ticker.lower())}\b", full):
                continue

            mentions += 1
            score = int(d.get("score", 0) or 0)
            if score > top_score:
                top_score = score
                top_title = title[:100]

            bulls = sum(1 for w in BULLISH if w in full)
            bears = sum(1 for w in BEARISH if w in full)
            if bulls > bears:
                bull_count += 1
            elif bears > bulls:
                bear_count += 1

        if mentions == 0:
            sentiment = "none"
        elif bull_count > bear_count * 1.5:
            sentiment = "bullish"
        elif bear_count > bull_count * 1.5:
            sentiment = "bearish"
        else:
            sentiment = "mixed"

        return {
            "ticker":            ticker.upper(),
            "mention_count_24h": mentions,
            "sentiment_label":   sentiment,
            "top_post_title":    top_title,
            "top_post_score":    top_score,
        }
    except Exception:
        return {}


def load_candidates() -> list[str]:
    """Load tickers with short interest >= 15%."""
    if not SHORT_CSV.exists():
        # Fall back to combined_priority tickers
        cp = ROOT / "combined_priority.csv"
        if not cp.exists():
            return []
        out = []
        with cp.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("ticker") or "").strip().upper()
                if t:
                    out.append(t)
        return out[:30]

    out = []
    with SHORT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            si = float(row.get("short_pct_float", 0) or 0)
            if si >= 8.0:
                out.append(row["ticker"])
    return out[:35]


def main() -> int:
    now_ts  = int(datetime.datetime.now().timestamp())
    cache   = load_cache()
    tickers = load_candidates()
    print(f"reddit_wsb_pulse: checking {len(tickers)} tickers on r/wallstreetbets")

    rows: list[dict] = []
    for i, ticker in enumerate(tickers):
        entry = cache.get(ticker)
        if entry and now_ts - int(entry.get("ts", 0)) < CACHE_TTL:
            data = entry.get("data", {})
        else:
            data = fetch_wsb(ticker)
            cache[ticker] = {"ts": now_ts, "data": data}
            time.sleep(0.8)  # be polite to Reddit

        if data:
            rows.append(data)

    save_cache(cache)
    rows.sort(key=lambda r: int(r.get("mention_count_24h", 0) or 0), reverse=True)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    mentioned = [r for r in rows if int(r.get("mention_count_24h", 0) or 0) > 0]
    print(f"  Wrote {len(rows)} rows | {len(mentioned)} tickers mentioned on WSB today")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
