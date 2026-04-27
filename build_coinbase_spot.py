#!/usr/bin/env python3
"""build_coinbase_spot.py — Coinbase spot exchange rates (638 pairs).

Coinbase's public exchange-rates endpoint returns USD conversion rates
against 638+ currencies and crypto pairs simultaneously, no key, no
rate limit visible. Covers every major crypto (BTC/ETH/SOL/XRP/DOGE),
all G10 fiats (EUR/JPY/GBP/CHF/CAD/AUD/NZD/SEK/NOK), precious metals
(XAU/XAG), regional fiats (CNY/INR/BRL/MXN/TRY/ARS/VES/RUB), and
CBDC-backing stables.

Output: coinbase_spot.csv
Columns: pair, usd_rate, inverse_usd, captured_at

Signal for trading:
- XAU USD rate breakdown = gold spot precision (NEM/GOLD miners signal).
- VES/ARS/TRY daily delta = EM currency stress.
- CNY trending above 7.30 = trade-war escalation proxy.
- BTC/ETH/SOL spot reconciliation against coinbase_exchanges feed.

Source: api.coinbase.com/v2/exchange-rates?currency=USD (no key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "coinbase_spot.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.coinbase.com/v2/exchange-rates?currency=USD"

# Focus set we always want clean. Other currencies still captured.
PRIORITY = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX", "LTC",
    "BCH", "LINK", "UNI", "MATIC", "ATOM", "TRX", "XLM", "ICP", "FIL",
    "USDT", "USDC", "DAI", "PYUSD",
    "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK",
    "CNY", "HKD", "SGD", "KRW", "TWD", "THB", "PHP", "IDR", "MYR", "INR",
    "BRL", "MXN", "CLP", "COP", "PEN", "ARS", "VES",
    "TRY", "ZAR", "RUB", "PLN", "CZK", "HUF", "ILS", "AED", "SAR", "EGP",
    "XAU", "XAG", "XPT", "XPD",
}


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"coinbase_spot: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"coinbase_spot: keeping existing {OUT_CSV.name}")
        return

    rates = (d.get("data") or {}).get("rates") or {}
    if not rates:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"coinbase_spot: no rates, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for pair, v in rates.items():
        try:
            r = float(v)
        except (TypeError, ValueError):
            continue
        if r <= 0:
            continue
        inv = 1.0 / r
        rows.append({
            "pair": pair,
            "usd_rate": f"{r:.10g}",
            "inverse_usd": f"{inv:.10g}",
            "priority": "1" if pair in PRIORITY else "0",
        })

    # Sort priority first then alpha.
    rows.sort(key=lambda x: (x["priority"] == "0", x["pair"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["pair", "usd_rate", "inverse_usd",
                  "priority", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary.
    by = {r["pair"]: r["inverse_usd"] for r in rows}
    bits = []
    for k in ("BTC", "ETH", "EUR", "JPY", "XAU", "CNY"):
        v = by.get(k)
        if v:
            bits.append(f"USD/{k} inv={v[:8]}")
    print(f"coinbase_spot: {len(rows)} pairs | {' '.join(bits)} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
