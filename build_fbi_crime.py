#!/usr/bin/env python3
"""build_fbi_crime.py — FBI Crime Data Explorer agency coverage.

State-level NIBRS (National Incident-Based Reporting System) coverage
by law-enforcement agency. Regional crime signal with sector overlays:
- Retail theft surge → TGT, WMT, COST, LOW, HD shrinkage narrative
- Urban precinct NIBRS downtime → insurance underwriting risk
  (TRV, ALL, PGR)
- Rural/small-agency non-coverage → physical-security demand (ADT, CGEM)

Source: api.usa.gov/crime/fbi/cde (free public endpoint).

Output: fbi_crime.csv
Columns: state, ori, county, agency_name, agency_type, nibrs,
         nibrs_start, lat, lon, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fbi_crime.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.usa.gov/crime/fbi/cde/agency/byStateAbbr"

# 15 states with heaviest retail/insurance/logistics exposure.
STATES = ["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI",
          "NJ", "VA", "WA", "AZ", "MA"]


def _fetch(state: str) -> dict:
    url = f"{BASE}/{state}?API_KEY=DEMO_KEY"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        return d if isinstance(d, dict) else {}
    except Exception as e:
        print(f"fbi_crime {state}: {e}")
        return {}


def main() -> None:
    rows: list[dict] = []
    seen_oris: set[str] = set()

    for state in STATES:
        d = _fetch(state)
        for county, agencies in d.items():
            if not isinstance(agencies, list):
                continue
            for a in agencies[:12]:  # top 12 per county
                if not isinstance(a, dict):
                    continue
                ori = (a.get("ori") or "")[:12]
                if not ori or ori in seen_oris:
                    continue
                seen_oris.add(ori)
                rows.append({
                    "state": state,
                    "ori": ori,
                    "county": str(county)[:24],
                    "agency_name": (a.get("agency_name") or "")[:48],
                    "agency_type": (a.get("agency_type_name") or "")[:16],
                    "nibrs": "1" if a.get("is_nibrs") else "0",
                    "nibrs_start": (a.get("nibrs_start_date") or "")[:10],
                    "lat": f"{float(a.get('latitude', 0) or 0):.4f}",
                    "lon": f"{float(a.get('longitude', 0) or 0):.4f}",
                })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fbi_crime: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["state"], r["county"], r["agency_name"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["state", "ori", "county", "agency_name", "agency_type",
                  "nibrs", "nibrs_start", "lat", "lon", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    nibrs_cov = sum(1 for r in rows if r["nibrs"] == "1")
    per_state: dict[str, int] = {}
    for r in rows:
        per_state[r["state"]] = per_state.get(r["state"], 0) + 1
    print(f"fbi_crime: {len(rows)} agencies ({len(per_state)} states) | "
          f"NIBRS={nibrs_cov}/{len(rows)} "
          f"({100*nibrs_cov/max(len(rows),1):.0f}%) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
