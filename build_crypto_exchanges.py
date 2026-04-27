#!/usr/bin/env python3
"""build_crypto_exchanges.py — Crypto exchange volumes (CoinGecko).

Exchange spot volume = retail crypto engagement proxy. Binance/Coinbase
volume rising = COIN/BYON/HOOD crypto fee revenue up. Kraken outage →
COIN market share gain. Deriv exchange (Bybit, OKX) dominance =
institutional speculation signal.

Source: api.coingecko.com/api/v3/exchanges (public, rate-limited).
Output: crypto_exchanges.csv
Columns: exchange, trust_score, vol_btc_24h, coins_listed,
         country, year_established, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_exchanges.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch() -> list[dict]:
    url = "https://api.coingecko.com/api/v3/exchanges?per_page=50&page=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"coingecko_exch: {e}")
        return []


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for ex in items[:50]:
        rows.append({
            "exchange": (ex.get("name") or "")[:40],
            "trust_score": ex.get("trust_score", 0) or 0,
            "vol_btc_24h": f"{ex.get('trade_volume_24h_btc', 0) or 0:.2f}",
            "coins_listed": "",
            "country": ex.get("country", "") or "",
            "year_established": ex.get("year_established", "") or "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "exchange", "trust_score", "vol_btc_24h",
                "coins_listed", "country", "year_established", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"crypto_exch: {len(rows)} exchanges | #1 {top.get('exchange','?')} "
          f"vol={top.get('vol_btc_24h','?')} BTC -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
