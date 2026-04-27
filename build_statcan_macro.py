#!/usr/bin/env python3
"""build_statcan_macro.py — Statistics Canada macro indicators.

Canadian equity macro overlay for TSX-listed names with US dual-listings
(CNQ, SU, BNS, TD, RY, CM, BMO, NA, ENB, TRP, MFC, SLF, CNR, CP, NTR,
WCN, CSU, SHOP, GIB).

Series (StatCan vector IDs):
- v41690973 — CPI all-items YoY%
- v62305752 — unemployment rate
- v65201210 — CAD/USD spot
- v1001828100 — housing starts
- v52367097 — 10Y benchmark yield

Trade context:
- CAD inflation surprise → BMO/RY/TD net interest margin tailwind
- Unemployment up → energy sector (CNQ/SU) weakness signal
- USDCAD break above 1.40 → dual-listed ADR premium compression
- Housing starts collapse → XHB:Canada weakness, CNR/CP rail volume

Source: StatCan WDS REST (free, no key).

Output: statcan_macro.csv
Columns: vector_id, series_name, ref_period, value, decimals, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "statcan_macro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www150.statcan.gc.ca/t1/wds/rest/"
       "getDataFromVectorsAndLatestNPeriods")

# Vector-ID → friendly name.
VECTORS = [
    (41690973,   "cpi_all_items_yoy"),
    (62305752,   "unemployment_rate"),
    (65201210,   "cad_usd_spot"),
    (1001828100, "housing_starts_urban"),
    (52367097,   "yield_10y_bench"),
    (80691038,   "gdp_growth_expenditure"),
    (41996044,   "retail_trade_total"),
    (42158012,   "manufacturing_sales"),
]


def main() -> None:
    body = json.dumps([
        {"vectorId": vid, "latestN": 3} for vid, _ in VECTORS
    ]).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"statcan_macro: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"statcan_macro: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(d, list):
        print(f"statcan_macro: unexpected payload")
        return

    name_by_vid = {vid: nm for vid, nm in VECTORS}
    rows: list[dict] = []
    for resp in d:
        if not isinstance(resp, dict):
            continue
        obj = resp.get("object") or {}
        vid = obj.get("vectorId")
        if vid is None:
            continue
        pts = obj.get("vectorDataPoint") or []
        for pt in pts:
            if not isinstance(pt, dict):
                continue
            rows.append({
                "vector_id": str(vid),
                "series_name": name_by_vid.get(vid, "?"),
                "ref_period": (pt.get("refPer") or "")[:10],
                "value": f"{float(pt.get('value') or 0):.4f}",
                "decimals": str(pt.get("decimals") or ""),
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"statcan_macro: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["series_name"], r["ref_period"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["vector_id", "series_name", "ref_period", "value",
                  "decimals", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    series_count = len(set(r["series_name"] for r in rows))
    latest = {r["series_name"]: r for r in rows
              if r["series_name"] not in
              {x["series_name"] for x in rows[:0]}}
    # pick one representative for summary
    latest_map = {}
    for r in rows:
        if r["series_name"] not in latest_map:
            latest_map[r["series_name"]] = r
    sample = latest_map.get("cad_usd_spot") or next(iter(latest_map.values()))
    print(f"statcan_macro: {len(rows)} obs ({series_count} series) | "
          f"{sample.get('series_name','?')}={sample.get('value','?')} "
          f"@ {sample.get('ref_period','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
