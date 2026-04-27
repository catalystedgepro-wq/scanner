#!/usr/bin/env python3
"""build_wildfires.py — WFIGS Interagency Fire Perimeters (current).

Wildland Fire Interagency Geospatial Services (WFIGS) publishes
all current wildfire perimeter polygons across the United States
from federal + state + local agencies, updated continuously.
Fire activity in specific corridors has direct equity effects:

- Big California fires near PG&E / Edison service areas: PSPS
  shutoffs + inverse condemnation liability (EIX, PCG). Perimeter
  > 5,000 acres within 10mi of grid = likely blackout event.
- Texas / Oklahoma Panhandle fires: cattle herd losses drive live
  cattle futures (LE=F) + feeder cattle (GF=F); packer margin
  implications (TSN, PPC).
- Colorado / Wyoming / Montana fires + ski-season smoke: hotel
  (MAR, H), short-term rental (ABNB booking-cancel headwind).
- Oregon / Washington fires: lumber supply (WY, LPX) + rail
  disruption signals (UNP/BNSF routing through smoke zones).

Output (top 50 largest active fires):
  incident_name, state, size_acres, cause, discovery_date,
  containment_pct, is_complex, category, captured_at

Source: WFIGS Interagency_Perimeters_Current FeatureServer
(ArcGIS REST, no key, free, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "wildfires.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

BASE = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/"
        "services/WFIGS_Interagency_Perimeters_Current/"
        "FeatureServer/0/query")


def main() -> None:
    qs = urllib.parse.urlencode({
        "where": "attr_IncidentSize > 100",
        "outFields": ("poly_IncidentName,attr_POOState,"
                      "attr_IncidentSize,attr_FireCause,"
                      "attr_FireDiscoveryDateTime,"
                      "attr_PercentContained,"
                      "attr_IsCpxChild,attr_IncidentTypeCategory"),
        "f": "json",
        "returnGeometry": "false",
        "resultRecordCount": "200",
        "orderByFields": "attr_IncidentSize DESC",
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"wildfires: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"wildfires: keeping existing {OUT_CSV.name}")
        return

    feats = d.get("features", []) or []
    rows: list[dict] = []
    for f in feats:
        a = f.get("attributes", {}) or {}
        size = a.get("attr_IncidentSize")
        try:
            size_f = float(size) if size is not None else 0.0
        except (TypeError, ValueError):
            continue
        if size_f <= 0:
            continue
        disc = a.get("attr_FireDiscoveryDateTime")
        disc_iso = ""
        if isinstance(disc, (int, float)) and disc > 0:
            disc_iso = (dt.datetime.fromtimestamp(
                disc / 1000, tz=dt.timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"))
        rows.append({
            "incident_name": (a.get("poly_IncidentName") or "")[:80],
            "state": a.get("attr_POOState") or "",
            "size_acres": f"{size_f:.0f}",
            "cause": (a.get("attr_FireCause") or "")[:40],
            "discovery_date": disc_iso,
            "containment_pct": (f"{float(a['attr_PercentContained']):.0f}"
                                if a.get("attr_PercentContained")
                                is not None else ""),
            "is_complex": ("1"
                           if a.get("attr_IsCpxChild") in (1, "Y", True)
                           else "0"),
            "category": (a.get("attr_IncidentTypeCategory") or "")[:20],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"wildfires: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: -float(r["size_acres"]))
    rows = rows[:50]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["incident_name", "state", "size_acres", "cause",
                  "discovery_date", "containment_pct", "is_complex",
                  "category", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: largest fire + state breakdown for top 10.
    top = rows[0]
    ca = sum(1 for r in rows[:20] if r["state"] == "US-CA")
    tx = sum(1 for r in rows[:20] if r["state"] == "US-TX")
    big = sum(1 for r in rows if float(r["size_acres"]) >= 10000)
    print(f"wildfires: {len(rows)} fires ({big} >10k acres) | "
          f"top: {top['incident_name'][:30]} ({top['state']}) "
          f"{top['size_acres']}a | top20: CA={ca} TX={tx} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
