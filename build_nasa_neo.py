#!/usr/bin/env python3
"""build_nasa_neo.py — NASA Near-Earth Object 7-day feed.

Close-approach asteroid list for the next 7 days. Hazardous NEOs or
large close approaches drive one-day spikes in:
- Space-sector names (LMT, NOC, BA, ASTR, RKLB)
- Insurance reinsurance headlines (TRV, AIG, RNR)
- Defense/DoD planetary defense contracts
- Meme trades when media picks up near-miss stories

Source: api.nasa.gov/neo/rest/v1/feed (NASA, DEMO_KEY rate-limited).

Output: nasa_neo.csv
Columns: neo_id, name, close_date, miss_km, velocity_kps,
         diameter_m, is_hazardous, orbit_body, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nasa_neo.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.nasa.gov/neo/rest/v1/feed"


def main() -> None:
    today = dt.date.today()
    end = today + dt.timedelta(days=7)
    qs = urllib.parse.urlencode({
        "start_date": today.isoformat(),
        "end_date": end.isoformat(),
        "api_key": "DEMO_KEY",
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nasa_neo: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasa_neo: keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    neos_by_date = d.get("near_earth_objects") or {}
    for date_str, items in neos_by_date.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            ests = (item.get("estimated_diameter") or {}).get("meters") or {}
            dmax = ests.get("estimated_diameter_max") or 0
            cads = item.get("close_approach_data") or []
            if not cads:
                continue
            cad = cads[0]
            rel = cad.get("relative_velocity") or {}
            miss = cad.get("miss_distance") or {}
            rows.append({
                "neo_id": str(item.get("id") or "")[:12],
                "name": (item.get("name") or "")[:40],
                "close_date": (cad.get("close_approach_date") or "")[:10],
                "miss_km": f"{float(miss.get('kilometers') or 0):.0f}",
                "velocity_kps": f"{float(rel.get('kilometers_per_second') or 0):.2f}",
                "diameter_m": f"{float(dmax):.1f}",
                "is_hazardous": "1" if item.get("is_potentially_hazardous_asteroid") else "0",
                "orbit_body": (cad.get("orbiting_body") or "")[:12],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasa_neo: empty, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["close_date"], float(r["miss_km"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["neo_id", "name", "close_date", "miss_km",
                  "velocity_kps", "diameter_m", "is_hazardous",
                  "orbit_body", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    haz = sum(1 for r in rows if r["is_hazardous"] == "1")
    closest = min(rows, key=lambda r: float(r["miss_km"]))
    print(f"nasa_neo: {len(rows)} NEOs (7-d) | hazardous={haz} | "
          f"closest: {closest['name']} at {closest['miss_km']} km -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
