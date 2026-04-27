#!/usr/bin/env python3
"""build_crypto_correlation.py — Crypto correlation feed (BTC + alts).

BTC/ETH pumps drag crypto-exposed equities (COIN, MSTR, MARA, RIOT, CLSK,
HOOD, SQ, HUT). Free APIs: CoinGecko (public) and Binance (public).

Source: CoinGecko /coins/markets (top 100 by market cap, no key).
Output: crypto_correlation.csv
Columns: symbol, name, price_usd, change_1h, change_24h, change_7d, market_cap
"""
from __future__ import annotations
import csv
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_correlation.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
    "&price_change_percentage=1h,24h,7d"
)


def fetch(url: str, timeout: int = 20) -> list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"crypto: {e}")
        return None


def main():
    data = fetch(API) or []
    rows: list[dict] = []
    for c in data:
        rows.append({
            "symbol": (c.get("symbol") or "").upper(),
            "name": (c.get("name") or "")[:80],
            "price_usd": f"{float(c.get('current_price') or 0):.6f}",
            "change_1h": f"{float(c.get('price_change_percentage_1h_in_currency') or 0):+.2f}",
            "change_24h": f"{float(c.get('price_change_percentage_24h_in_currency') or 0):+.2f}",
            "change_7d": f"{float(c.get('price_change_percentage_7d_in_currency') or 0):+.2f}",
            "market_cap": f"{int(c.get('market_cap') or 0)}",
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol", "name", "price_usd",
                "change_1h", "change_24h", "change_7d", "market_cap",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"crypto_correlation: {len(rows)} coins -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
