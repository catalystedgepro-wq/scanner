#!/usr/bin/env python3
"""build_penny_universe.py — Build a broad penny stock universe for the gap scanner.

Pulls all NASDAQ/NYSE/AMEX listed stocks, filters to penny range ($0.50–$10,
volume > 50K), merges with SEC filer universe, and writes penny_universe.txt.

The gap scanner uses this file instead of sec_catalyst_tickers.txt so it
catches ALL gapping penny stocks — not just recent SEC filers.

Outputs:
  penny_universe.txt     — merged ticker list (SEC filers + broad penny universe)
  penny_universe_stats.json — count breakdown for logging

Run time: ~30 seconds (one API call + filter).
"""

from __future__ import annotations

import json
import urllib.request
import datetime as dt
from pathlib import Path

ROOT          = Path(__file__).parent
SEC_TICKERS   = ROOT / "sec_catalyst_tickers.txt"
OUT_FILE      = ROOT / "penny_universe.txt"
STATS_FILE    = ROOT / "penny_universe_stats.json"

MIN_PRICE     = 0.50
MAX_PRICE     = 10.00
MIN_VOLUME    = 50_000

NASDAQ_URL    = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&limit=25000&offset=0&download=true"
)


def fetch_nasdaq_stocks() -> list[dict]:
    req = urllib.request.Request(
        NASDAQ_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept":     "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data.get("data", {}).get("rows", [])


def parse_price(s: str) -> float:
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def parse_volume(s: str) -> int:
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def load_sec_tickers() -> set[str]:
    if not SEC_TICKERS.exists():
        return set()
    return {
        line.strip().upper()
        for line in SEC_TICKERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def main() -> int:
    print("build_penny_universe: fetching NASDAQ stock list...")
    try:
        rows = fetch_nasdaq_stocks()
    except Exception as e:
        print(f"  fetch failed: {e}")
        return 1

    print(f"  total listed stocks: {len(rows)}")

    # Filter to penny range
    penny_tickers: set[str] = set()
    for row in rows:
        symbol = row.get("symbol", "").strip().upper()
        price  = parse_price(row.get("lastsale", "0"))
        volume = parse_volume(row.get("volume", "0"))

        # Skip warrants, rights, units, preferred shares
        if any(c in symbol for c in ["W", "R", "U", "+"]) and len(symbol) > 4:
            continue
        if not symbol or not symbol.isalpha():
            continue

        if MIN_PRICE <= price <= MAX_PRICE and volume >= MIN_VOLUME:
            penny_tickers.add(symbol)

    print(f"  penny range tickers (${MIN_PRICE}–${MAX_PRICE}, vol>{MIN_VOLUME:,}): {len(penny_tickers)}")

    # Merge with SEC filers (they get priority — put them first)
    sec_tickers = load_sec_tickers()
    print(f"  SEC filer tickers: {len(sec_tickers)}")

    # SEC filers first, then remaining penny tickers
    merged: list[str] = []
    seen:   set[str]  = set()

    for t in sorted(sec_tickers):
        if t not in seen:
            merged.append(t)
            seen.add(t)

    for t in sorted(penny_tickers):
        if t not in seen:
            merged.append(t)
            seen.add(t)

    # Write output
    OUT_FILE.write_text("\n".join(merged) + "\n", encoding="utf-8")
    print(f"  total universe: {len(merged)} tickers → {OUT_FILE.name}")

    # Stats
    stats = {
        "date":           dt.date.today().isoformat(),
        "nasdaq_total":   len(rows),
        "penny_filtered": len(penny_tickers),
        "sec_filers":     len(sec_tickers),
        "sec_only":       len(sec_tickers - penny_tickers),
        "penny_only":     len(penny_tickers - sec_tickers),
        "total_universe": len(merged),
    }
    STATS_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print(f"  SEC-only (filed but out of price range today): {stats['sec_only']}")
    print(f"  Penny-only (not recent SEC filers): {stats['penny_only']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
