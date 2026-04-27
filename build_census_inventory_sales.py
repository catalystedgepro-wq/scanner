#!/usr/bin/env python3
"""build_census_inventory_sales.py — Census MTIS (Manufacturing &
Trade Inventories & Sales).

Monthly US business sales + inventories + inventory-to-sales
ratio (I/S) across four categories:
  MNFCTR  — Manufacturing
  RETAIL  — Retail
  WHLSLR  — Wholesale
  TOTBUS  — Total business (combined)

Why I/S ratio matters for trading:
- I/S > 1.50 + rising = inventory glut, recession signal (2008,
  2022 destockings). Short XLI, XRT, long XLP defensive.
- Manufacturing I/S leads industrial production by 2-3 months.
- Retail I/S > 1.30 + sales decelerating = holiday-season markdown
  risk → TGT/BBY/M margin compression.
- Wholesale I/S > 1.35 = distributor backlog clearing → GWW, FAST,
  WSO, HDS pricing pressure.
- Divergence (manufacturing inventory +15% YoY, sales flat) = hard
  landing setup.

MTIS releases 45 days after reference month (Feb data ~mid-April).

Source: api.census.gov/data/timeseries/eits/mtis (no key).

Data types captured:
  SM      — Sales, seasonally adjusted $ millions
  IM      — Inventories, seasonally adjusted $ millions
  IR      — Inventory-to-sales ratio
  MPCSM   — Sales MoM % change
  MPCIM   — Inventories MoM % change

Output: census_inventory_sales.csv
Columns: month, category, sales_mm, inventory_mm, i_to_s,
         sales_mom_pct, inv_mom_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_inventory_sales.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.census.gov/data/timeseries/eits/mtis"

CATEGORIES = ["MNFCTR", "RETAIL", "WHLSLR", "TOTBUS"]


def fetch_category(code: str, from_month: str) -> list[dict]:
    qs = urllib.parse.urlencode({
        "get": ("cell_value,data_type_code,category_code,"
                "time_slot_id,seasonally_adj"),
        "for": "us:*",
        "time": f"from {from_month}",
        "time_slot_id": "0",
        "seasonally_adj": "yes",
        "category_code": code,
    })
    url = f"{API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if not body:
                return []
            raw = body.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"inventory_sales {code}: {e}")
        return []
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"inventory_sales parse {code}: {e}")
        return []
    if not data or len(data) < 2:
        return []
    hdr = data[0]
    vi = hdr.index("cell_value")
    di = hdr.index("data_type_code")
    ti = hdr.index("time")
    out: list[dict] = []
    for row in data[1:]:
        out.append({
            "month": str(row[ti]),
            "type": str(row[di]),
            "value": row[vi],
        })
    return out


def main() -> None:
    today = dt.date.today()
    from_month = f"{today.year - 2}-01"

    # month -> category -> type -> value
    combined: dict[str, dict[str, dict[str, str]]] = {}
    for cat in CATEGORIES:
        records = fetch_category(cat, from_month)
        for r in records:
            m = r["month"]
            combined.setdefault(m, {}).setdefault(cat, {})[r["type"]] = r["value"]

    if not combined and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"census_inventory_sales: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for m in sorted(combined.keys(), reverse=True):
        for cat in CATEGORIES:
            rec = combined[m].get(cat, {})
            if not rec:
                continue
            rows.append({
                "month": m,
                "category": cat,
                "sales_mm": rec.get("SM", ""),
                "inventory_mm": rec.get("IM", ""),
                "i_to_s": rec.get("IR", ""),
                "sales_mom_pct": rec.get("MPCSM", ""),
                "inv_mom_pct": rec.get("MPCIM", ""),
            })

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["month", "category", "sales_mm", "inventory_mm",
                  "i_to_s", "sales_mom_pct", "inv_mom_pct",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        latest_month = rows[0]["month"]
        msg_parts = []
        for r in rows:
            if r["month"] != latest_month:
                break
            msg_parts.append(
                f"{r['category']} I/S={r['i_to_s']} "
                f"(sales {r['sales_mom_pct']}%)"
            )
        print(f"census_inventory_sales: {len(rows)} pts | "
              f"{latest_month} | {' | '.join(msg_parts)} "
              f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
