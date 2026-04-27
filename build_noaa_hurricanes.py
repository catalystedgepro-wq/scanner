#!/usr/bin/env python3
"""build_noaa_hurricanes.py — Active tropical systems from NHC + NOAA.

Tropical storm / hurricane activity directly moves insurance (TRV, ALL,
CB, PGR, RNR, RE), Gulf oil (XOM, OXY, CHX, CVX producers), cruise (RCL,
CCL, NCLH), airlines (AAL, DAL, UAL, LUV — route disruption), and retail
(HD, LOW hurricane-prep spike).

Source: National Hurricane Center CurrentStorms JSON (nhc.noaa.gov — free,
no key).

Output: noaa_hurricanes.csv
Columns: storm_id, name, classification, intensity_kt, pressure_mb,
         lat, lon, movement_dir, movement_speed_kt,
         advisory_url, tickers_exposed, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "noaa_hurricanes.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEEDS = [
    "https://www.nhc.noaa.gov/CurrentStorms.json",
]

# Basin → exposure baskets
BASIN_TICKERS = {
    "AL": "TRV,ALL,CB,RNR,RE,RCL,CCL,NCLH,XOM,OXY,HD,LOW,GNW,ALG",  # Atlantic
    "EP": "CCL,RCL,AAL,LUV,FL (FloridaAir)",                         # East Pacific
    "CP": "HA,BCH",                                                  # Central Pacific
}


def fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"noaa_hurricanes: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for u in FEEDS:
        data = fetch(u) or {}
        storms = data.get("activeStorms") or []
        for s in storms:
            storm_id = s.get("id") or ""
            basin = storm_id[:2].upper() if storm_id else ""
            intensity = s.get("intensity") or ""
            try:
                intensity_kt = float(intensity)
            except Exception:
                intensity_kt = 0.0
            rows.append({
                "storm_id": storm_id,
                "name": s.get("name", ""),
                "classification": s.get("classification", ""),
                "intensity_kt": f"{intensity_kt:.0f}",
                "pressure_mb": s.get("pressure", ""),
                "lat": s.get("latitudeNumeric", ""),
                "lon": s.get("longitudeNumeric", ""),
                "movement_dir": s.get("movementDir", ""),
                "movement_speed_kt": s.get("movementSpeed", ""),
                "advisory_url": (s.get("publicAdvisory") or {}).get("url", ""),
                "tickers_exposed": BASIN_TICKERS.get(basin, ""),
            })
    rows.sort(key=lambda r: float(r.get("intensity_kt") or 0), reverse=True)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "storm_id", "name", "classification", "intensity_kt",
                "pressure_mb", "lat", "lon", "movement_dir",
                "movement_speed_kt", "advisory_url", "tickers_exposed",
                "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"noaa_hurricanes: {len(rows)} active storms -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
