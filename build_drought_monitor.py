#!/usr/bin/env python3
"""build_drought_monitor.py — US Drought Monitor weekly state-level.

Drought intensity drives ag (CORN, SOYB, WEAT), water utilities (AWK,
WTRG), beef (TSN, food costs), fire-risk insurers (AIG, TRV, ALL),
natgas (NG, low hydro → gas demand up), fertilizers (CF, NTR, MOS), and
power utilities (SRE, PCG wildfire exposure).

Source: droughtmonitor.unl.edu JSON/CSV.
Output: drought_monitor.csv
Columns: week_end, state, d0, d1, d2, d3, d4, captured_at
  (d0=abnormally dry … d4=exceptional drought; each column = % of state area)
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "drought_monitor.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# USDM Comprehensive State Statistics (most recent week, all states)
#   - statisticsType=1 means percent area
# endpoint format: .../DSCI.aspx?aoi=<state abbr>&date=<yyyymmdd>
# But simpler JSON endpoint:
#   https://usdmdataservices.unl.edu/api/StateStatistics/GetDroughtSeverityStatisticsByAreaPercent
URL = (
    "https://usdmdataservices.unl.edu/api/StateStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
    "?aoi=ALL&startdate=1/1/2026&enddate=12/31/2026&statisticsType=1"
)


def fetch() -> list:
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"drought_monitor: {e}")
        return []


def main() -> None:
    data = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # Keep most-recent week per state
    latest: dict[str, dict] = {}
    for rec in data if isinstance(data, list) else []:
        st = rec.get("StateAbbreviation") or rec.get("State") or ""
        md = rec.get("MapDate") or rec.get("ValidStart") or ""
        if not st or not md:
            continue
        key = st
        cur = latest.get(key)
        if not cur or md > cur.get("MapDate", ""):
            latest[key] = rec
    for st, rec in sorted(latest.items()):
        rows.append({
            "week_end": rec.get("MapDate", "")[:10],
            "state": st,
            "d0": rec.get("D0", ""),
            "d1": rec.get("D1", ""),
            "d2": rec.get("D2", ""),
            "d3": rec.get("D3", ""),
            "d4": rec.get("D4", ""),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["week_end", "state", "d0", "d1", "d2", "d3", "d4", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"drought_monitor: {len(rows)} states -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
