#!/usr/bin/env python3
"""build_usgs_waterflow.py — USGS river stage + discharge snapshot.

USGS NWIS serves real-time water-gage data for every major US
watershed. River stage and discharge on the Mississippi, Ohio, and
Columbia are **barge-shipping proxies** for soy/corn/coal movement;
Great Lakes levels drive iron-ore and steel logistics.

Extreme low flows at St. Louis gauges = grain barges run aground
(ADM/BG/GPRE logistics costs spike). High flows at Vicksburg =
shipping closures. Drought metrics at Colorado gauges = Western
ag water allocation squeeze.

Gauges tracked (USGS site IDs):
- 05331000  Mississippi @ St. Paul, MN (grain belt outflow)
- 07010000  Mississippi @ St. Louis, MO (soy/corn barge pinch)
- 07289000  Mississippi @ Vicksburg, MS (downstream terminal)
- 03612500  Ohio @ Metropolis, IL (coal/soybean confluence)
- 14105700  Columbia @ The Dalles, OR (wheat, apples, hydropower)
- 09380000  Colorado @ Lees Ferry, AZ (Western water compact)
- 14246900  Willamette @ Portland (Pacific NW ag)
- 02037500  James @ Richmond, VA (East-coast power cooling)

Parameter codes:
- 00060  Discharge, cubic feet per second
- 00065  Gage height, feet

Signal for trading:
- St. Louis discharge < 10,000 cfs sustained in summer = barge
  tonnage cap -> fade ADM/BG; bid rail UNP/CSX.
- Vicksburg stage > 40 ft = grain port inefficiency; fade DBA.
- Lees Ferry discharge trend < 10 KAF/month = megadrought signal;
  bid AWK/XYL (water utilities).
- Great Lakes / Columbia hydropower > 10y avg = low power prices,
  bid PNW aluminum smelters (AA).

Source: waterservices.usgs.gov/nwis/iv (no key, JSON).

Output: usgs_waterflow.csv
Columns: site_id, site_name, parameter, value, unit, measured_at,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usgs_waterflow.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SITES = [
    "05331000", "07010000", "07289000", "03612500",
    "14105700", "09380000", "14246900", "02037500",
]
URL = ("https://waterservices.usgs.gov/nwis/iv/"
       "?format=json&sites={}&parameterCd=00060,00065"
       "&siteStatus=active")


def main() -> None:
    url = URL.format(",".join(SITES))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"usgs_waterflow: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"usgs_waterflow: keeping existing {OUT_CSV.name}")
        return

    ts_list = (d.get("value", {}) or {}).get("timeSeries", []) or []
    rows: list[dict] = []
    for ts in ts_list:
        src = ts.get("sourceInfo", {}) or {}
        var = ts.get("variable", {}) or {}
        site_code_list = src.get("siteCode", []) or []
        site_id = site_code_list[0].get("value", "") if site_code_list else ""
        site_name = (src.get("siteName") or "")[:80]
        param_name = var.get("variableName") or ""
        unit = (var.get("unit") or {}).get("unitCode", "") or ""
        values_wrap = ts.get("values", []) or []
        if not values_wrap:
            continue
        points = values_wrap[0].get("value", []) or []
        if not points:
            continue
        # Latest observation
        latest = points[-1]
        val = latest.get("value", "")
        ts_iso = latest.get("dateTime", "") or ""
        try:
            v_float = float(val)
        except (TypeError, ValueError):
            continue
        rows.append({
            "site_id": site_id,
            "site_name": site_name,
            "parameter": param_name[:60],
            "value": f"{v_float:.2f}",
            "unit": unit[:20],
            "measured_at": ts_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"usgs_waterflow: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["site_id"], r["parameter"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["site_id", "site_name", "parameter", "value", "unit",
                  "measured_at", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: show Mississippi @ St. Louis discharge if present.
    stl = next((r for r in rows if r["site_id"] == "07010000"
                and "Streamflow" in r["parameter"]), None)
    vix = next((r for r in rows if r["site_id"] == "07289000"
                and "Streamflow" in r["parameter"]), None)
    stl_s = f"StL flow={stl['value']} cfs" if stl else ""
    vix_s = f"Vicksburg flow={vix['value']} cfs" if vix else ""
    print(f"usgs_waterflow: {len(rows)} rows | {stl_s} | {vix_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
