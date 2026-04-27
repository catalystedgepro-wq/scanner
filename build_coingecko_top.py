#!/usr/bin/env python3
"""build_coingecko_top.py — CoinGecko top-50 spot + trending.

Broad crypto macro for equity-adjacent names:
- $COIN revenue proxy via total-volume aggregate (top-50 daily turnover)
- $MSTR leverage via BTC spot
- $MARA/$RIOT/$CLSK hashprice proxy via BTC price + difficulty proxy
- $HOOD crypto-arm narrative via ETH/SOL/DOGE trading volumes
- $SQ / $BLOCK bitcoin-holding mark-to-market

Trade context:
- Top-50 total volume > $300B/day → $COIN Q-over-Q revenue upside
- Trending list composition shift (memes vs majors) → $HOOD retail mix
- >10 coins up >20% 24h → altseason narrative, $COIN beat likely
- BTC/ETH >7d% gap >15 pct points → alt rotation signal

Source: api.coingecko.com (public tier, no key, ~30 req/min).

Output: coingecko_top.csv
Columns: bucket, rank, coin_id, symbol, name, price_usd,
         market_cap, volume_24h, change_24h, change_7d, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "coingecko_top.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.coingecko.com/api/v3"


def _fetch(path: str) -> list | dict | None:
    req = urllib.request.Request(f"{BASE}{path}",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"coingecko {path[:30]}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []

    # Top-50 by market cap with 24h+7d change.
    markets = _fetch("/coins/markets?vs_currency=usd&order=market_cap_desc"
                     "&per_page=50&page=1&price_change_percentage=24h,7d")
    if isinstance(markets, list):
        for c in markets:
            if not isinstance(c, dict):
                continue
            rows.append({
                "bucket": "top50",
                "rank": str(c.get("market_cap_rank", "")),
                "coin_id": (c.get("id") or "")[:32],
                "symbol": (c.get("symbol") or "")[:10].upper(),
                "name": (c.get("name") or "")[:32],
                "price_usd": f"{float(c.get('current_price') or 0):.6g}",
                "market_cap": str(int(c.get("market_cap") or 0)),
                "volume_24h": str(int(c.get("total_volume") or 0)),
                "change_24h": f"{float(c.get('price_change_percentage_24h') or 0):.3f}",
                "change_7d": (f"{float(c.get('price_change_percentage_7d_in_currency') or 0):.3f}"
                              if c.get('price_change_percentage_7d_in_currency') is not None else ""),
            })

    # Trending (top-7 on CoinGecko attention).
    trend = _fetch("/search/trending")
    if isinstance(trend, dict):
        for i, item in enumerate(trend.get("coins") or []):
            if not isinstance(item, dict):
                continue
            inner = item.get("item") or {}
            rows.append({
                "bucket": "trending",
                "rank": str(i + 1),
                "coin_id": (inner.get("id") or "")[:32],
                "symbol": (inner.get("symbol") or "")[:10].upper(),
                "name": (inner.get("name") or "")[:32],
                "price_usd": "",
                "market_cap": "",
                "volume_24h": "",
                "change_24h": "",
                "change_7d": "",
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"coingecko_top: no data, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["bucket", "rank", "coin_id", "symbol", "name", "price_usd",
                  "market_cap", "volume_24h", "change_24h", "change_7d",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top50 = [r for r in rows if r["bucket"] == "top50"]
    total_vol = sum(int(r["volume_24h"] or 0) for r in top50)
    up_big = sum(1 for r in top50 if r["change_24h"] and float(r["change_24h"]) > 10)
    dn_big = sum(1 for r in top50 if r["change_24h"] and float(r["change_24h"]) < -10)
    btc = next((r for r in top50 if r["symbol"] == "BTC"), None)
    btc_p = f"BTC=${btc['price_usd']}" if btc else "BTC=?"
    print(f"coingecko_top: {len(rows)} rows | {btc_p} | "
          f"vol24h=${total_vol/1e9:.1f}B | "
          f"up>10%={up_big} dn>10%={dn_big} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
