#!/usr/bin/env python3
"""build_noaa_hurricane.py — NHC Atlantic active tropical systems.

Active hurricanes in Gulf/Atlantic = direct catalyst chain:
- Insurance hits (ALL, TRV, PGR, CB, AIG, HIG, WRB)
- Oil refinery disruption (VLO, PSX, MPC, DINO)
- Nat gas LNG export (LNG, TELL, VENI, SHEL)
- Agriculture (Florida citrus → FDP parent, OJ futures)
- Lumber (WY, PCH, LPX) for rebuild
- Home Depot / Lowe's storm prep surges
- Generators (GNRC, Briggs, Kohler)

Source: NHC Atlantic active storms JSON feed.
Output: noaa_hurricane.csv
Columns: storm_id, name, basin, classification, intensity_kt, pressure_mb,
         latitude, longitude, update_time, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "noaa_hurricane.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = "https://www.nhc.noaa.gov/CurrentStorms.json"


def fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"noaa_hurricane: {e}")
        return []
    return data.get("activeStorms", []) or []


def main() -> None:
    storms = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for s in storms:
        rows.append({
            "storm_id": s.get("id", ""),
            "name": s.get("name", ""),
            "basin": s.get("binNumber", ""),
            "classification": s.get("classification", ""),
            "intensity_kt": s.get("intensity", ""),
            "pressure_mb": s.get("pressure", ""),
            "latitude": s.get("latitudeNumeric", ""),
            "longitude": s.get("longitudeNumeric", ""),
            "update_time": s.get("lastUpdate", ""),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "storm_id", "name", "basin", "classification",
                "intensity_kt", "pressure_mb", "latitude", "longitude",
                "update_time", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"noaa_hurricane: {len(rows)} active storms -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
