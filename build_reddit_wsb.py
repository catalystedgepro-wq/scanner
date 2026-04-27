#!/usr/bin/env python3
"""build_reddit_wsb.py — r/wallstreetbets hot posts + ticker frequency.

WSB is the retail sentiment firehose. Ticker cash-tag density → meme-stock
hunt list. Spikes in GME/AMC/NVDA/TSLA/PLTR/HOOD mentions precede
coordinated gamma squeezes.

Source: reddit.com/r/wallstreetbets/hot.json (public, JSON, 25 posts).
Output: reddit_wsb.csv
Columns: post_id, title, score, comments, created_utc, top_tickers, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "reddit_wsb.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://www.reddit.com/r/wallstreetbets/hot.json?limit=50"
TICKER_RE = re.compile(r"\$([A-Z]{2,5})\b|\b([A-Z]{3,5})\b")
BLACKLIST = {
    "THE", "AND", "FOR", "WITH", "THIS", "THAT", "ARE", "YOUR", "YOU",
    "ALL", "BUT", "CAN", "JUST", "LIKE", "WILL", "NOT", "HAVE", "HAS",
    "WAS", "HOW", "WHY", "WHAT", "WHEN", "WHERE", "ABOUT", "LOSS", "DD",
    "YOLO", "FDS", "CEO", "CFO", "IPO", "EPS", "CPI", "GDP", "IRS", "USA",
    "USD", "EDT", "PST", "UTC", "WSB", "EOD", "ATH", "ATL", "NYSE", "OTC",
    "API", "FED", "SEC", "FDA", "SOS", "IMO", "OMG", "LOL", "TOS", "NYT",
    "NBC", "CBS", "FOX",
}


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"wsb: {e}")
        return None


def extract_tickers(s: str) -> list[str]:
    out = []
    for m in TICKER_RE.finditer(s):
        t = m.group(1) or m.group(2)
        if t and t not in BLACKLIST:
            out.append(t)
    return out


def main() -> None:
    data = fetch() or {}
    posts = ((data.get("data") or {}).get("children")) or []
    rows: list[dict] = []
    all_tickers: Counter = Counter()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for p in posts:
        d = p.get("data", {})
        title = d.get("title", "")
        body = d.get("selftext", "")[:400]
        tickers = extract_tickers(title + " " + body)
        for t in tickers:
            all_tickers[t] += 1
        rows.append({
            "post_id": d.get("id", ""),
            "title": title[:100],
            "score": d.get("score", 0),
            "comments": d.get("num_comments", 0),
            "created_utc": dt.datetime.fromtimestamp(
                d.get("created_utc", 0), tz=dt.timezone.utc
            ).isoformat(timespec="seconds"),
            "top_tickers": "|".join(t for t, _ in Counter(tickers).most_common(5)),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "post_id", "title", "score", "comments",
                "created_utc", "top_tickers", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = all_tickers.most_common(10)
    print(f"reddit_wsb: {len(rows)} posts | top tickers: {', '.join(f'{t}:{n}' for t, n in top)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
