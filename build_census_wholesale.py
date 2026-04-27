#!/usr/bin/env python3
"""build_census_wholesale.py — Census Monthly Wholesale Trade (MWTS).

MWTS captures US wholesaler-level activity — sales, inventories, and
the inventory-to-sales ratio — one month before the same signal shows
up at retail. It's a leading indicator for:

- **Inventory build** (I/S ratio rising, sales flat): pipeline stuffing
  → expect retail discounting / margin compression downstream (TGT,
  WMT, COST, DG, DLTR, KSS, M).
- **Inventory destock** (I/S ratio falling, sales rising): supply-chain
  tightness → pricing-power tailwind for branded goods (KO, PG, CLX,
  CHD).
- **Durable-goods inventory swings** (NAICS 423): heavy-machinery and
  auto-parts pipeline → CAT, DE, CMI, PCAR, AZO, ORLY, LKQ.
- **Nondurable inventory swings** (NAICS 424): food, chemicals, paper,
  pharma wholesale → SYY, UNFI, CHEF, CVS, WBA, CAH, ABC.

Key metrics (all NAICS 42 = total wholesale):
- `SM` (Sales Monthly SA) — $ millions, seasonally-adjusted
- `IM` (Inventory Monthly SA) — $ millions, EOM inventory
- `IR` (Inventory/Sales Ratio) — leading-indicator ratio
- `MPCSM` — MoM % change in sales, SA
- `MPCIM` — MoM % change in inventory, SA

Trade uses:
- I/S ratio > 1.40 and rising 3+ months → inventory-correction risk,
  short retail/consumer discretionary ETF (XRT, RTH) 30-90d.
- I/S ratio < 1.20 and falling 3+ months → supply-chain tightness,
  long brand-owner ETF (XLP) + pricing-power plays (PG, KO).
- MoM sales surprise > +1% (MPCSM): upstream demand re-accelerating,
  bullish industrial complex (XLI).

Source: api.census.gov/data/timeseries/eits/mwts (free, no key, stdlib
only). Released ~6 weeks after month-end — lags MARTS retail by 1 month.

Output: census_wholesale.csv
Columns: period, category_code, category_name, sales_millions,
inventory_millions, inv_sales_ratio, sales_mom_pct, inv_mom_pct,
captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_wholesale.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.census.gov/data/timeseries/eits/mwts"

CATEGORIES = {
    "42":  "Total Wholesale Trade",
    "423": "Durable Goods Wholesale",
    "424": "Nondurable Goods Wholesale",
}


def fetch_category(code: str) -> list[list[str]]:
    params = {
        "get": "cell_value,data_type_code,time_slot_id",
        "time": "from 2024",
        "seasonally_adj": "yes",
        "category_code": code,
        "for": "us:*",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"census_wholesale: {code} -> {e}")
        return []


def main() -> None:
    rows: list[dict] = []

    for code, label in CATEGORIES.items():
        data = fetch_category(code)
        if len(data) <= 1:
            continue

        by_period: dict[str, dict[str, str]] = {}
        for row in data[1:]:
            if len(row) < 4:
                continue
            val, dtype, _slot, period = row[0], row[1], row[2], row[3]
            by_period.setdefault(period, {})[dtype] = val

        for period in sorted(by_period.keys()):
            rec = by_period[period]
            rows.append({
                "period": period,
                "category_code": code,
                "category_name": label,
                "sales_millions": rec.get("SM", ""),
                "inventory_millions": rec.get("IM", ""),
                "inv_sales_ratio": rec.get("IR", ""),
                "sales_mom_pct": rec.get("MPCSM", ""),
                "inv_mom_pct": rec.get("MPCIM", ""),
            })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"census_wholesale: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["period"], r["category_code"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["period", "category_code", "category_name",
                        "sales_millions", "inventory_millions",
                        "inv_sales_ratio", "sales_mom_pct",
                        "inv_mom_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Summary: latest-month headline (42 = Total)
    latest = rows[0]["period"] if rows else "?"
    total_now = next(
        (r for r in rows
         if r["period"] == latest and r["category_code"] == "42"),
        None,
    )
    if total_now:
        hdr = (f"42 Total: sales ${total_now['sales_millions']}M "
               f"({total_now['sales_mom_pct']}% MoM), "
               f"inv ${total_now['inventory_millions']}M "
               f"({total_now['inv_mom_pct']}% MoM), "
               f"I/S={total_now['inv_sales_ratio']}")
    else:
        hdr = "headline ?"

    print(f"census_wholesale: {len(rows)} rows | latest {latest} | "
          f"{hdr} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
