#!/usr/bin/env python3
"""build_reddit_velocity.py — Reddit ticker mention velocity via ApeWisdom.

Reddit's own JSON API blocks datacenter IPs with a blanket 403. ApeWisdom
aggregates mention counts across wallstreetbets, stocks, investing, pennystocks,
Wallstreetbetsnew, options, shortsqueeze, etc. — their public JSON endpoint
has no auth and returns normalised 24h/4h mention deltas.

Endpoint: https://apewisdom.io/api/v1.0/filter/all-stocks/page/1

Output: reddit_velocity.csv
Columns: rank, ticker, mentions, mentions_24h_ago, upvotes, rank_24h_ago,
         name, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "reddit_velocity.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
API = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}"


def fetch(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"reddit: {url[-30:]} -> {e}")
        return None


def main():
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows = []
    for page in (1, 2, 3):
        data = fetch(API.format(page=page))
        if not data or "results" not in data:
            break
        for r in data["results"]:
            try:
                mentions = int(r.get("mentions") or 0)
                prior = int(r.get("mentions_24h_ago") or 0)
            except Exception:
                continue
            rows.append({
                "rank": int(r.get("rank") or 0),
                "ticker": (r.get("ticker") or "").upper(),
                "mentions": mentions,
                "mentions_24h_ago": prior,
                "velocity_pct": f"{((mentions-prior)/prior*100):+.0f}" if prior else "",
                "upvotes": int(r.get("upvotes") or 0),
                "rank_24h_ago": int(r.get("rank_24h_ago") or 0),
                "name": (r.get("name") or "")[:80],
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank", "ticker", "mentions", "mentions_24h_ago",
                "velocity_pct", "upvotes", "rank_24h_ago", "name", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"reddit_velocity: {len(rows)} tickers -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
