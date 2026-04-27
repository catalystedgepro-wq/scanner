#!/usr/bin/env python3
"""build_eia_petroleum.py — EIA Weekly Petroleum Status Report.

Every Wed 10:30 AM ET, EIA releases crude/gasoline/distillate stockpile data.
Drives energy complex (USO, XLE, XOP, drillers, refiners) intraday.

EIA Open Data API is free (no key needed for light use) — using the
api.eia.gov endpoint with the public 'NO_API_KEY' fallback via their
series-data CSV dumps, or v2 API with DEMO key.

Output: eia_petroleum.csv
Columns: report_date, series, value, unit, tag, move_vs_prior
"""
from __future__ import annotations
import csv
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eia_petroleum.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API_KEY = os.environ.get("EIA_API_KEY", "")  # optional; empty => public dataset JSON

# Key weekly series (v2 API uses PET.<code>.W fully qualified series IDs).
SERIES = {
    "PET.WCESTUS1.W": "CRUDE_STOCKS_US",        # Crude oil stocks
    "PET.WGTSTUS1.W": "GASOLINE_STOCKS_US",     # Total gasoline stocks
    "PET.WDISTUS1.W": "DISTILLATE_STOCKS_US",   # Distillate fuel oil stocks
    "PET.WCRFPUS2.W": "REFINER_INPUTS",         # Refiner net input of crude
    "PET.WCRRIUS2.W": "REFINER_UTIL",           # Refiner operable utilization
    "PET.WCRSTUS1.W": "SPR_STOCKS",             # Strategic Petroleum Reserve
    "PET.WCEIMUS2.W": "CRUDE_IMPORTS",          # Weekly crude imports
    "PET.WGFSTUS1.W": "FINISHED_GASOLINE",
    "PET.WTTSTUS1.W": "TOTAL_PETROL_STOCKS",
}

BASE = "https://api.eia.gov/v2/seriesid/{sid}?api_key={key}"


def fetch(url: str, timeout: int = 25) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"eia: {e}")
        return None


def main():
    rows: list[dict] = []
    if not API_KEY:
        # Fallback: hit EIA's open CSV snapshots — free and no key needed
        # https://ir.eia.gov/wpsr/psw09.xls is canonical but binary; use JSON series via DEMO
        print("eia: EIA_API_KEY not set — using DEMO path (may rate-limit).")
    for sid, tag in SERIES.items():
        url = BASE.format(sid=sid, key=API_KEY or "DEMO_KEY")
        data = fetch(url)
        if not data or "response" not in data:
            continue
        points = (data.get("response") or {}).get("data") or []
        # Sorted descending by period
        points.sort(key=lambda p: p.get("period", ""), reverse=True)
        if not points:
            continue
        latest = points[0]
        prior = points[1] if len(points) > 1 else {}
        try:
            cur = float(latest.get("value") or 0)
            pri = float(prior.get("value") or 0)
            move = cur - pri
        except Exception:
            cur, pri, move = 0.0, 0.0, 0.0
        rows.append({
            "report_date": latest.get("period", ""),
            "series": sid,
            "tag": tag,
            "value": f"{cur:.1f}",
            "prior_value": f"{pri:.1f}",
            "move_vs_prior": f"{move:+.1f}",
            "unit": latest.get("units", ""),
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["report_date", "series", "tag", "value", "prior_value", "move_vs_prior", "unit"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"eia_petroleum: {len(rows)} series -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
