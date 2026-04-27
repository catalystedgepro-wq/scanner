#!/usr/bin/env python3
"""build_crypto_treasury.py — Public company crypto treasury exposure.

Critical for pricing MSTR, MARA, RIOT, COIN, CLSK, SMLR, HUT, BTDR, TSLA,
SQ, and other corporate BTC/ETH treasury plays whose equity moves 1:1 with
coin price. Tracks holdings from latest 10-Q/10-K public disclosures and
marks-to-market with live CoinGecko spot.

Sources (all free, primary):
  - Curated holdings from latest SEC 10-Q / 8-K disclosures
  - CoinGecko /simple/price for live BTC + ETH spot (free, no key)

Output: crypto_treasury.csv
Columns:
  ticker, company, btc_holdings, eth_holdings,
  btc_mark_to_market_usd, eth_mark_to_market_usd, total_mtm_usd,
  cost_basis_usd, unrealized_pnl_usd, last_filing_date,
  btc_spot_usd, eth_spot_usd, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_treasury.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Curated from most recent 10-Q / 8-K / press releases (Q1 2026 cycle).
# Holdings refresh on filing events; script re-scores mark-to-market daily.
#   btc / eth   = coin units held on balance sheet
#   cost        = aggregate USD cost basis (from filings)
#   filing      = last public-disclosure date the holding was confirmed
HOLDINGS = [
    # (ticker, company, btc, eth, cost_basis_usd, last_filing)
    ("MSTR", "MicroStrategy",         580250,  0,  41100000000, "2026-02-05"),
    ("MARA", "MARA Holdings",          47531,  0,   2650000000, "2026-02-26"),
    ("RIOT", "Riot Platforms",         17722,  0,   1090000000, "2026-02-24"),
    ("CLSK", "CleanSpark",             10191,  0,    640000000, "2026-02-05"),
    ("TSLA", "Tesla",                  11509,  0,    336000000, "2024-07-23"),
    ("COIN", "Coinbase",               10350,  0,    475000000, "2026-02-13"),
    ("HUT",  "Hut 8",                  10273,  0,    690000000, "2026-03-12"),
    ("SQ",   "Block",                   8485,  0,    220000000, "2026-02-20"),
    ("SMLR", "Semler Scientific",       3808,  0,    367000000, "2026-02-24"),
    ("HIVE", "HIVE Digital",            2620,  0,    185000000, "2026-02-12"),
    ("BITF", "Bitfarms",                1294,  0,     95000000, "2026-03-12"),
    ("CIFR", "Cipher Mining",           1063,  0,     82000000, "2026-02-25"),
    ("BTDR", "Bitdeer Technologies",    1039,  0,     78000000, "2026-03-13"),
    ("BTBT", "Bit Digital",              873,  27800, 140000000, "2026-02-13"),
    ("GLXY", "Galaxy Digital",           912,  0,     76000000, "2026-03-03"),
    ("WULF", "TeraWulf",                 213,  0,     17000000, "2026-03-05"),
    ("IREN", "IREN Limited",              95,  0,      7500000, "2026-02-26"),
    ("NAKA", "Nakamoto (KindlyMD)",     5764,  0,    430000000, "2026-03-10"),
    ("DJT",  "Trump Media & Technology", 8420, 0,    750000000, "2026-03-17"),
    ("GME",  "GameStop",                4710,  0,    420000000, "2026-03-25"),
    ("APLD", "Applied Digital",            0,  0,            0, "2026-02-14"),
    ("CORZ", "Core Scientific",          200,  0,     15500000, "2026-02-26"),
    ("EXOD", "Exodus Movement",         2010,  0,    155000000, "2026-03-11"),
    ("CAN",  "Canaan Inc",               207,  0,     14000000, "2026-03-25"),
    ("BRPHF","Brera Holdings",           158,  0,     11500000, "2026-03-14"),
    ("KULR", "KULR Technology",          926,  0,     83000000, "2026-03-12"),
    ("SQNS", "Sequans Communications",  2264,  0,    200000000, "2026-03-07"),
    ("MTPLF","Metaplanet (ADR)",       18991,  0,   1980000000, "2026-03-26"),
    ("BMNR", "BitMine Immersion",          0, 1020000, 2400000000, "2026-03-20"),
    ("BTCS", "BTCS Inc",                  0,  90318,   185000000, "2026-03-14"),
]


def fetch_json(url: str, timeout: int = 15) -> dict | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"crypto_treasury: {url[:60]} -> {e}")
        return None


def fetch_spot() -> tuple[float, float]:
    """CoinGecko simple/price — free, no key needed."""
    url = ("https://api.coingecko.com/api/v3/simple/price"
           "?ids=bitcoin,ethereum&vs_currencies=usd")
    data = fetch_json(url)
    if not isinstance(data, dict):
        return 0.0, 0.0
    btc = float((data.get("bitcoin") or {}).get("usd") or 0)
    eth = float((data.get("ethereum") or {}).get("usd") or 0)
    return btc, eth


def main() -> None:
    btc_spot, eth_spot = fetch_spot()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows: list[dict] = []
    for ticker, company, btc, eth, cost, filing in HOLDINGS:
        btc_mtm = btc * btc_spot
        eth_mtm = eth * eth_spot
        total = btc_mtm + eth_mtm
        pnl = total - cost if cost else 0
        rows.append({
            "ticker": ticker,
            "company": company,
            "btc_holdings": btc,
            "eth_holdings": eth,
            "btc_mark_to_market_usd": f"{btc_mtm:.0f}",
            "eth_mark_to_market_usd": f"{eth_mtm:.0f}",
            "total_mtm_usd": f"{total:.0f}",
            "cost_basis_usd": cost,
            "unrealized_pnl_usd": f"{pnl:.0f}",
            "last_filing_date": filing,
            "btc_spot_usd": f"{btc_spot:.2f}",
            "eth_spot_usd": f"{eth_spot:.2f}",
            "captured_at": now,
        })
    rows.sort(key=lambda r: float(r["total_mtm_usd"]), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ticker", "company", "btc_holdings", "eth_holdings",
                "btc_mark_to_market_usd", "eth_mark_to_market_usd",
                "total_mtm_usd", "cost_basis_usd", "unrealized_pnl_usd",
                "last_filing_date", "btc_spot_usd", "eth_spot_usd",
                "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"crypto_treasury: {len(rows)} cos | BTC=${btc_spot:,.0f} ETH=${eth_spot:,.0f} "
          f"| leader {top.get('ticker','?')} ${int(float(top.get('total_mtm_usd',0))):,} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
