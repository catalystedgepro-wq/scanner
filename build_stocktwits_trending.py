#!/usr/bin/env python3
"""build_stocktwits_trending.py — StockTwits trending symbols (free JSON).

StockTwits exposes a public trending-symbols endpoint with no auth.
Velocity = number of messages per unit time. Retail-flow signal.

Output: stocktwits_trending.csv
Columns: ticker, watchers, bullish_pct, bearish_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "stocktwits_trending.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
API = "https://api.stocktwits.com/api/2/trending/symbols/equities.json?limit=30"
SENT = "https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"


def fetch(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"stocktwits: {url[-30:]} -> {e}")
        return None


def main():
    data = fetch(API)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows: list[dict] = []
    if not data or "symbols" not in data:
        print("stocktwits: no data")
        with OUT_CSV.open("w", newline="") as f:
            csv.DictWriter(
                f, fieldnames=["ticker", "watchers", "bullish_pct", "bearish_pct", "captured_at"]
            ).writeheader()
        return
    for s in data.get("symbols", [])[:30]:
        rows.append({
            "ticker": (s.get("symbol") or "").upper(),
            "watchers": s.get("watchlist_count", 0),
            "bullish_pct": "",
            "bearish_pct": "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["ticker", "watchers", "bullish_pct", "bearish_pct", "captured_at"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"stocktwits_trending: {len(rows)} tickers -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
