#!/usr/bin/env python3
"""build_coingecko_derivatives.py — crypto derivatives OI + volume.

Open interest and 24h volume across crypto derivatives exchanges.
Complements build_crypto_funding (per-asset funding rate) and
build_coinbase_spot (spot price) with leverage-capital distribution.

Signal:
- Rising aggregate BTC OI while spot flat = gearing up for move
- OI concentration shifting between Binance/OKX/Bybit flags regional
  flow (Asia/US exchange divergence)
- Volume/OI ratio extremes front-run blow-off tops or capitulation

Drives:
- COIN (exchange flow visibility)
- MSTR (BTC leverage proxy)
- Miners (MARA, RIOT, CLSK, HUT, IREN) — on funding/leverage regime
- Crypto ETFs (IBIT, FBTC, GBTC) — institutional demand
- MicroStrategy-adjacent (SMLR, META BTC treasury)

Source: api.coingecko.com/api/v3 (free, no key).
Output: coingecko_derivatives.csv
Columns: exchange_id, name, country, year, oi_btc, volume_btc,
         perp_pairs, futures_pairs, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "coingecko_derivatives.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.coingecko.com/api/v3/derivatives/exchanges"


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"coingecko_derivatives: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"coingecko_derivatives: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"coingecko_derivatives: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        oi = _f(item.get("open_interest_btc"))
        vol = _f(item.get("trade_volume_24h_btc"))
        if oi == 0 and vol == 0:
            continue
        rows.append({
            "exchange_id": str(item.get("id") or "")[:24],
            "name": str(item.get("name") or "")[:40],
            "country": str(item.get("country") or "")[:24],
            "year": str(item.get("year_established") or "")[:4],
            "oi_btc": f"{oi:.2f}",
            "volume_btc": f"{vol:.2f}",
            "perp_pairs": str(item.get("number_of_perpetual_pairs") or 0),
            "futures_pairs": str(item.get("number_of_futures_pairs") or 0),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"coingecko_derivatives: 0 rows, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: -float(r["oi_btc"]))
    rows = rows[:40]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["exchange_id", "name", "country", "year", "oi_btc",
                  "volume_btc", "perp_pairs", "futures_pairs",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total_oi = sum(float(r["oi_btc"]) for r in rows)
    total_vol = sum(float(r["volume_btc"]) for r in rows)
    top = rows[0]
    print(f"coingecko_derivatives: {len(rows)} exchanges | "
          f"aggregate OI={total_oi:.0f} BTC, 24h vol={total_vol:.0f} BTC | "
          f"leader: {top['name']}={top['oi_btc']} BTC "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
