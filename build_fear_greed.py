#!/usr/bin/env python3
"""build_fear_greed.py — CNN Fear & Greed Index (daily + 7 components).

Fear & Greed is a composite market sentiment score (0-100) CNN publishes
from 7 sub-indicators: market momentum (SPX vs 125d MA), stock price
strength (52w hi/lo ratio), stock price breadth (McClellan volume),
put/call ratio, junk bond demand, market volatility (VIX percentile),
and safe haven demand (stocks vs bonds 20d return spread).

Trade uses:
- Score <25 (Extreme Fear) for 3+ sessions: contrarian long SPY/QQQ
  historically delivers +3-5% reversion over following 2 weeks.
- Score >75 (Extreme Greed): trim exposure, lift hedges (put skew cheap).
- Divergence: SPX at highs but score dropping = distribution warning.
- Fast regime shift (20+ point move in 2 weeks) = vol regime change,
  rotate into defensives (XLU/XLP/XLV).

Source: production.dataviz.cnn.io/index/fearandgreed/graphdata. Returns
JSON with current score, rating, YoY history, and all 7 sub-indicators.
Requires Safari UA + Referer header (429s on default urllib UA).
No API key. Public.

Output: fear_greed.csv
Columns: as_of, score, rating, momentum, strength, breadth, pcr,
         junk_demand, volatility, safe_haven, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fear_greed.csv"
URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

# CNN's WAF rejects default urllib UA with "I'm a teapot". Safari works.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 "
        "Safari/605.1.15"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
    "Origin": "https://www.cnn.com",
    "Accept-Language": "en-US,en;q=0.9",
}

# Map CNN sub-indicator keys to stable short names for the CSV.
SUB_KEYS = {
    "market_momentum_sp500": "momentum",
    "stock_price_strength": "strength",
    "stock_price_breadth": "breadth",
    "put_call_options": "pcr",
    "junk_bond_demand": "junk_demand",
    "market_volatility_vix": "volatility",
    "safe_haven_demand": "safe_haven",
}


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fear_greed: {e}")
        return None


def main() -> None:
    data = fetch()
    if not data or "fear_and_greed" not in data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 80:
            print(f"fear_greed: fetch empty, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
            return
        data = {}
    fg = data.get("fear_and_greed", {})
    score = fg.get("score", "")
    rating = fg.get("rating", "")
    ts = fg.get("timestamp", "")
    as_of = ts[:10] if ts else dt.date.today().isoformat()
    row = {
        "as_of": as_of,
        "score": f"{float(score):.2f}" if score != "" else "",
        "rating": rating,
    }
    for cnn_key, short in SUB_KEYS.items():
        sub = data.get(cnn_key, {})
        val = sub.get("score", "")
        row[short] = f"{float(val):.2f}" if val not in ("", None) else ""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    row["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["as_of", "score", "rating",
                        "momentum", "strength", "breadth", "pcr",
                        "junk_demand", "volatility", "safe_haven",
                        "captured_at"],
        )
        w.writeheader()
        w.writerow(row)
    print(f"fear_greed: score={row['score']} ({row['rating']}) "
          f"as_of={row['as_of']} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
