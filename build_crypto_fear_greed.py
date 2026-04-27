#!/usr/bin/env python3
"""build_crypto_fear_greed.py — Crypto Fear & Greed Index (alternative.me).

Separate from CNN equity F&G. Sentiment score 0-100 weighted from 6
sub-indicators: volatility (25%), momentum/volume (25%), social media
(15%), surveys (15%), bitcoin dominance (10%), trends (10%).

Trade uses:
- Score < 20 (Extreme Fear) 3+ sessions: BTC bottom setup. COIN/MSTR/
  MARA historically outperform BTC by 3-5x on reversal.
- Score > 85 (Extreme Greed): blow-off top risk. Long-dated vol cheap;
  rotate into stables.
- Divergence: BTC at new high + score dropping = distribution. Crypto
  equities (MARA/RIOT) lag BTC on the way up when this happens.
- Sustained Extreme Fear during broad SPX weakness: decorrelation
  signal — BTC becoming macro-hedge asset temporarily.

Source: alternative.me/fng/api — free, no key, rate-limited ~1/sec.
Returns 1 value per day going back to Feb 2018.

Output: crypto_fear_greed.csv
Columns: date, score, rating, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_fear_greed.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.alternative.me/fng/?limit=90&format=json"


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"crypto_fear_greed: {e}")
        return None


def main() -> None:
    data = fetch() or {}
    series = data.get("data") or []
    if not series and OUT_CSV.exists() and OUT_CSV.stat().st_size > 80:
        print(f"crypto_fear_greed: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    rows: list[dict] = []
    for item in series:
        ts = item.get("timestamp")
        try:
            d = dt.datetime.utcfromtimestamp(int(ts)).date().isoformat()
        except (ValueError, TypeError):
            continue
        rows.append({
            "date": d,
            "score": item.get("value", ""),
            "rating": item.get("value_classification", ""),
        })
    rows.sort(key=lambda r: r["date"])
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "score", "rating", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"crypto_fear_greed: {len(rows)} days | latest "
          f"{latest.get('date','?')} score={latest.get('score','?')} "
          f"({latest.get('rating','?')}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
