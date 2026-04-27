#!/usr/bin/env python3
"""build_eia_grid_930.py — EIA-930 real-time US electricity grid.

Hourly US electricity generation/demand by balancing authority.
Heatwaves → ERCOT, PJM spot prices explode → regional utility beats
(NEE, DUK, SO, D, AEP). Renewables share drives REGI, ENPH, FSLR, RUN.
EV charging demand creeps into TSLA, CHPT, EVGO capex.

Source: EIA API v2 (free, EIA_API_KEY required).
Output: eia_grid_930.csv
Columns: region, date, demand_mwh, net_generation_mwh, renewable_pct,
         interchange_mwh, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eia_grid_930.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KEY = os.environ.get("EIA_API_KEY", "")

REGIONS = ["US48", "CAL", "TEX", "NE", "MIDW", "SE", "FLA", "NW", "NY", "MIDA"]


def fetch(region: str) -> list:
    if not KEY:
        return []
    end = dt.date.today().isoformat()
    start = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    url = (
        "https://api.eia.gov/v2/electricity/rto/region-data/data"
        f"?api_key={KEY}&frequency=daily"
        f"&data[0]=value&facets[respondent][]={region}"
        f"&start={start}&end={end}"
        "&sort[0][column]=period&sort[0][direction]=desc&length=50"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
            return ((d.get("response") or {}).get("data")) or []
    except Exception as e:
        print(f"eia930 {region}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if not KEY:
        print("eia_grid_930: EIA_API_KEY not set; stub only")
    for reg in REGIONS:
        by_date: dict[str, dict[str, float]] = {}
        for rec in fetch(reg):
            d = rec.get("period", "")[:10]
            t = rec.get("type", "")
            v = rec.get("value")
            if v is None:
                continue
            by_date.setdefault(d, {})[t] = float(v)
        for d, mp in sorted(by_date.items(), reverse=True)[:14]:
            rows.append({
                "region": reg,
                "date": d,
                "demand_mwh": f"{mp.get('D', 0):.0f}",
                "net_generation_mwh": f"{mp.get('NG', 0):.0f}",
                "renewable_pct": "",
                "interchange_mwh": f"{mp.get('TI', 0):.0f}",
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "region", "date", "demand_mwh", "net_generation_mwh",
                "renewable_pct", "interchange_mwh", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"eia_grid_930: {len(rows)} obs / {len(REGIONS)} regions -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
