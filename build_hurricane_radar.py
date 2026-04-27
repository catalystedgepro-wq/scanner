#!/usr/bin/env python3
"""build_hurricane_radar.py — NHC active tropical systems.

Hurricane season (Jun 1 – Nov 30 Atlantic, May 15 – Nov 30 E-Pacific)
produces the single largest insurance-equity catalyst of the year.
Direct-impact Gulf/FL landfall drawdown (2-5 days out): ALL -8%, TRV
-6%, AIG -5%, PGR -4%. Models, homebuilders, and utility equities in
landfall footprint drop 5-15%.

Trade uses:
- Category-3+ advisory issued with US landfall in 5-day cone: short ALL,
  TRV, CB, HIG into news; generators (GNRC), plywood (WY), Home Depot
  (HD), Lowe's (LOW) rally pre-storm; re-insurers (RE, RNR) drop.
- Cat-4/5 major landfall: insurance 2-week drawdown 10-15% followed by
  mean-reversion bounce on reinsurance rate increases.
- Storm surge forecast > 10 ft for FL/TX: flood-loss ETF KIE drops
  -3 to -5% in sympathy.
- Season pre-position: elevated Atlantic Main Development Region SST
  May-July = active-season bias, insurance underperformance trade.

Source: www.nhc.noaa.gov/CurrentStorms.json (free, no key). Returns all
active Atlantic + Eastern Pacific systems with classification, wind,
pressure, lat/lon, and advisory URLs.

Off-season: returns empty array; spoke writes 0-row CSV + header.

Output: hurricane_radar.csv
Columns: storm_id, basin, name, classification, intensity_mph,
         pressure_mb, lat, lon, movement_mph, movement_dir,
         advisory_num, issued, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "hurricane_radar.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.nhc.noaa.gov/CurrentStorms.json"


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"hurricane_radar: {e}")
        return None


def main() -> None:
    data = fetch() or {}
    storms = data.get("activeStorms") or []
    rows: list[dict] = []
    for s in storms:
        if not isinstance(s, dict):
            continue
        rows.append({
            "storm_id": s.get("id", ""),
            "basin": s.get("binNumber", "")[:2] if s.get("binNumber") else "",
            "name": s.get("name", ""),
            "classification": s.get("classification", ""),
            "intensity_mph": s.get("intensity", ""),
            "pressure_mb": s.get("pressure", ""),
            "lat": s.get("latitudeNumeric", ""),
            "lon": s.get("longitudeNumeric", ""),
            "movement_mph": s.get("movementSpeed", ""),
            "movement_dir": s.get("movementDir", ""),
            "advisory_num": s.get("advisoryNum", ""),
            "issued": s.get("lastUpdate", ""),
        })

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["storm_id", "basin", "name", "classification",
                        "intensity_mph", "pressure_mb", "lat", "lon",
                        "movement_mph", "movement_dir", "advisory_num",
                        "issued", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    if rows:
        latest = rows[0]
        print(f"hurricane_radar: {len(rows)} active | "
              f"{latest.get('name','?')} "
              f"({latest.get('classification','?')}) "
              f"{latest.get('intensity_mph','?')} mph -> {OUT_CSV.name}")
    else:
        print(f"hurricane_radar: 0 active systems (off-season or "
              f"quiet period) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
