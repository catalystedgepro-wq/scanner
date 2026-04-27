#!/usr/bin/env python3
"""build_cboe_vix_gaps.py - CBOE vol-of-vol + 6M + Russell vol gaps.

Three CBOE volatility indices NOT covered by build_vix_complex.py (FRED
only has VIXCLS/VXNCLS/VXDCLS/VIX9DCLS/VXVCLS/SKEW) and NOT covered by
build_vix_term.py:

- VVIX  = vol-of-VIX. Spike = panic-on-panic, SPX tail-hedge bid.
- VIX6M = 6-month VIX (curve long-end). VIX6M < VIX = backwardation.
- RVX   = Russell 2000 VIX. RVX - VIX spread = small-cap stress gauge.

Source: CBOE delayed-quotes JSON (free, no key, ~15min delay).
Output: cboe_vix_gaps.csv
Columns: captured_at, symbol, price, chg, chg_pct, open, high, low,
         prev_close, timestamp_source
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cboe_vix_gaps.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/"

SYMBOLS = [
    ("_VVIX",  "VVIX"),
    ("_VIX6M", "VIX6M"),
    ("_RVX",   "RVX"),
]


def fetch(code: str) -> dict | None:
    url = f"{BASE}{code}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"cboe {code}: {exc}")
        return None
    try:
        return json.loads(body)
    except ValueError as exc:
        print(f"cboe {code} json: {exc}")
        return None


def row_for(symbol: str, payload: dict) -> dict | None:
    data = payload.get("data") or {}
    price = data.get("current_price")
    if price is None:
        return None
    return {
        "captured_at": dt.datetime.utcnow().replace(microsecond=0).isoformat(),
        "symbol": symbol,
        "price": f"{float(price):.4f}",
        "chg": f"{float(data.get('price_change') or 0.0):.4f}",
        "chg_pct": f"{float(data.get('price_change_percent') or 0.0):.4f}",
        "open": f"{float(data.get('open') or 0.0):.4f}",
        "high": f"{float(data.get('high') or 0.0):.4f}",
        "low": f"{float(data.get('low') or 0.0):.4f}",
        "prev_close": f"{float(data.get('prev_day_close') or 0.0):.4f}",
        "timestamp_source": payload.get("timestamp") or "",
    }


def main() -> None:
    rows: list[dict] = []
    for code, symbol in SYMBOLS:
        payload = fetch(code)
        if not payload:
            continue
        row = row_for(symbol, payload)
        if row:
            rows.append(row)

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"cboe_vix_gaps: no rows; preserved {OUT_CSV.name}")
        return

    fields = ["captured_at", "symbol", "price", "chg", "chg_pct",
              "open", "high", "low", "prev_close", "timestamp_source"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    summary = " ".join(f"{r['symbol']}={r['price']}" for r in rows)
    print(f"cboe_vix_gaps: {len(rows)} indices | {summary}")


if __name__ == "__main__":
    main()
