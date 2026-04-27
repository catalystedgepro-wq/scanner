#!/usr/bin/env python3
"""build_reddit_investing.py — Retail finance subreddits rollup.

r/investing + r/stocks + r/ValueInvesting + r/dividends + r/options
+ r/pennystocks = non-WSB retail sentiment. Broader than WSB meme
flows. Cashtag frequency → retail accumulation signal for
non-meme names (mid-cap divs, REITs, ETFs).

Source: reddit.com/r/{sub}/hot.json (no auth, 60req/min).
Output: reddit_investing.csv
Columns: subreddit, ticker, mentions, top_post_score, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "reddit_investing.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SUBS = [
    "investing", "stocks", "ValueInvesting", "dividends",
    "options", "pennystocks", "SecurityAnalysis",
    "thetagang", "Bogleheads", "StockMarket",
]

TICKER_RE = re.compile(r"\b\$?([A-Z]{2,5})\b")

STOPLIST = {
    "USA", "USD", "GDP", "CPI", "EPS", "PE", "YTD", "ETF", "IPO",
    "CEO", "CFO", "COO", "FOMC", "FED", "OPEC", "SEC", "WTF", "LOL",
    "IMO", "LMAO", "OMG", "FYI", "DD", "YOLO", "IMHO", "AFAIK", "DM",
    "BTC", "ETH", "NFT", "API", "SEO", "AI", "ML", "AMA",
}


def fetch(sub: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=50"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"reddit {sub}: {e}")
        return []
    return [c.get("data", {}) for c in data.get("data", {}).get("children", [])]


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for sub in SUBS:
        mentions: dict[str, int] = defaultdict(int)
        top_scores: dict[str, int] = defaultdict(int)
        for p in fetch(sub):
            text = (p.get("title", "") or "") + " " + (p.get("selftext", "") or "")
            score = p.get("score", 0) or 0
            for m in TICKER_RE.findall(text):
                if m in STOPLIST or len(m) < 2:
                    continue
                mentions[m] += 1
                if score > top_scores[m]:
                    top_scores[m] = score
        for t, n in sorted(mentions.items(), key=lambda x: -x[1])[:15]:
            rows.append({
                "subreddit": sub,
                "ticker": t,
                "mentions": n,
                "top_post_score": top_scores[t],
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "subreddit", "ticker", "mentions",
                "top_post_score", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"reddit_invest: {len(rows)} rows across {len(SUBS)} subs "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
