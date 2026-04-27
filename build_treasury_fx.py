#!/usr/bin/env python3
"""build_treasury_fx.py — US Treasury Official Reporting Rates of Exchange.

US Government's official FX rates (quarter-end), used for all federal
financial statements. Tracks 170+ currencies against USD. Not spot —
this is the official rate the US uses for cross-border GAAP reporting.

Trade context:
- ADR price vs Treasury official rate → ADR premium/discount detection
- Countries with one-way rate moves quarter-over-quarter → EM currency
  stress signal (RSX, EWZ, EEM, TUR, INDA)
- Rate break >5% QoQ → FX crisis candidate, short EM financials

Source: api.fiscaldata.treasury.gov (free, no key).

Output: treasury_fx.csv
Columns: record_date, country, currency, country_currency_desc,
         exchange_rate, effective_date, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_fx.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
       "v1/accounting/od/rates_of_exchange"
       "?sort=-record_date&page%5Bsize%5D=500")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"treasury_fx: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_fx: keeping existing {OUT_CSV.name}")
        return

    data = d.get("data") or []
    if not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_fx: no data, keeping existing {OUT_CSV.name}")
        return

    latest_date = max((row.get("record_date", "") for row in data),
                      default="")
    current = [r for r in data if r.get("record_date") == latest_date]

    rows: list[dict] = []
    for r in current:
        if not isinstance(r, dict):
            continue
        try:
            rate = float(r.get("exchange_rate", 0) or 0)
        except ValueError:
            continue
        rows.append({
            "record_date": (r.get("record_date") or "")[:10],
            "country": (r.get("country") or "")[:32],
            "currency": (r.get("currency") or "")[:24],
            "country_currency_desc": (r.get("country_currency_desc") or "")[:56],
            "exchange_rate": f"{rate:.6g}",
            "effective_date": (r.get("effective_date") or "")[:10],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_fx: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["country"])

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["record_date", "country", "currency",
                  "country_currency_desc", "exchange_rate",
                  "effective_date", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"treasury_fx: {len(rows)} currencies @ {latest_date} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
