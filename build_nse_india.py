#!/usr/bin/env python3
"""build_nse_india.py — Global equity index snapshot via Yahoo v8.

India's NIFTY 50 + sector sub-indices are the highest-leverage
overnight read into US open (India closes 4.5h before NYSE open).
Companion Asia-Europe indices are tracked here as a single global
risk barometer feed.

Direct NSE API (nseindia.com/api/allIndices) blocks headless
clients. Yahoo Finance v8 quote endpoint returns the same index
closes with no auth, no cookies.

Indices tracked:
- ^NSEI  NIFTY 50 (India, ~80% of NSE mcap)
- ^NSEBANK  NIFTY BANK
- ^CNXIT  NIFTY IT
- ^N225  Nikkei 225 (Japan)
- ^HSI   Hang Seng (HK)
- ^KS11  KOSPI (Korea)
- ^TWII  Taiwan Weighted
- ^AXJO  S&P/ASX 200 (Australia)
- ^FTSE  FTSE 100 (UK)
- ^GDAXI DAX (Germany)
- ^FCHI  CAC 40 (France)
- ^STOXX50E EURO STOXX 50
- ^BVSP  Bovespa (Brazil)
- ^MXX   IPC (Mexico)
- ^GSPTSE TSX Composite (Canada)
- 000001.SS  Shanghai Composite
- 399001.SZ  Shenzhen Component

Signal for trading:
- NIFTY50 red + HSI red + Nikkei red = risk-off imported to US;
  fade QQQ pre-market, bid DXY (UUP).
- NIFTY BANK down > 2% = EM credit stress; bid TLT.
- TSX down + Bovespa down while SPX up = commodity reversal.
- FTSE + DAX down same morning = Europe-credit stress; bid long
  gold GLD / short XLF exposure.

Source: query1.finance.yahoo.com/v8/finance/chart (no key, free).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nse_india.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

INDICES = [
    ("^NSEI", "NIFTY 50", "India"),
    ("^NSEBANK", "NIFTY Bank", "India"),
    ("^CNXIT", "NIFTY IT", "India"),
    ("^N225", "Nikkei 225", "Japan"),
    ("^HSI", "Hang Seng", "HongKong"),
    ("^KS11", "KOSPI", "Korea"),
    ("^TWII", "Taiwan Weighted", "Taiwan"),
    ("^AXJO", "S&P/ASX 200", "Australia"),
    ("^FTSE", "FTSE 100", "UK"),
    ("^GDAXI", "DAX", "Germany"),
    ("^FCHI", "CAC 40", "France"),
    ("^STOXX50E", "EURO STOXX 50", "Europe"),
    ("^BVSP", "Bovespa", "Brazil"),
    ("^MXX", "IPC Mexico", "Mexico"),
    ("^GSPTSE", "TSX Composite", "Canada"),
    ("000001.SS", "Shanghai Composite", "China"),
    ("399001.SZ", "Shenzhen Component", "China"),
]
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=2d&interval=1d"


def _fetch(sym: str) -> dict | None:
    url = URL.format(sym)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nse_india {sym}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for sym, name, country in INDICES:
        d = _fetch(sym)
        if not d:
            continue
        chart = (d.get("chart") or {}).get("result") or []
        if not chart:
            continue
        r = chart[0]
        meta = r.get("meta", {}) or {}
        try:
            last = float(meta.get("regularMarketPrice") or 0)
            prev = float(meta.get("chartPreviousClose")
                         or meta.get("previousClose") or 0)
        except (TypeError, ValueError):
            continue
        if last <= 0 or prev <= 0:
            continue
        pct = (last - prev) / prev * 100.0
        rows.append({
            "index_symbol": sym,
            "index_name": name,
            "country": country,
            "last": f"{last:.2f}",
            "previous_close": f"{prev:.2f}",
            "percent_change": f"{pct:.2f}",
            "currency": meta.get("currency") or "",
            "exchange_tz": meta.get("exchangeTimezoneName") or "",
            "regular_market_time": str(
                meta.get("regularMarketTime") or ""),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nse_india: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort by country then pct desc.
    rows.sort(key=lambda r: (r["country"], -float(r["percent_change"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["index_symbol", "index_name", "country", "last",
                  "previous_close", "percent_change", "currency",
                  "exchange_tz", "regular_market_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary snapshot.
    ni = next((r for r in rows if r["index_symbol"] == "^NSEI"), None)
    hsi = next((r for r in rows if r["index_symbol"] == "^HSI"), None)
    n225 = next((r for r in rows if r["index_symbol"] == "^N225"), None)
    bits = []
    for r, lbl in ((ni, "NIFTY50"), (n225, "N225"), (hsi, "HSI")):
        if r:
            bits.append(f"{lbl} {r['percent_change']}%")
    print(f"nse_india: {len(rows)} indices | {' '.join(bits)} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
