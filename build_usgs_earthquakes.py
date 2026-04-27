#!/usr/bin/env python3
"""build_usgs_earthquakes.py — USGS earthquakes 7d (M4.5+).

Major EQ (>M7) in tech corridors → TSMC/INTC/MU/STM supply chain risk,
semiconductor ETF (SOXX, SMH) volatility. Japan/Taiwan M7+ = SOXX down,
TSMC ADR gaps. California M7+ = insurance hits (ALL, TRV, PGR, MET)
and data center risk (EQIX, DLR).

Source: earthquake.usgs.gov/fdsnws/event/1/query GeoJSON.
Output: usgs_earthquakes.csv
Columns: eq_id, magnitude, place, time, longitude, latitude, depth_km,
         tsunami_flag, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usgs_earthquakes.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
    "4.5_week.geojson"
)


def fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"usgs: {e}")
        return []
    return data.get("features", []) or []


def main() -> None:
    feats = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for f in feats:
        p = f.get("properties", {}) or {}
        g = f.get("geometry", {}) or {}
        coords = g.get("coordinates") or [0, 0, 0]
        t_ms = p.get("time", 0) or 0
        try:
            iso = dt.datetime.fromtimestamp(
                t_ms / 1000.0, tz=dt.timezone.utc
            ).isoformat(timespec="seconds")
        except Exception:
            iso = ""
        rows.append({
            "eq_id": f.get("id", ""),
            "magnitude": p.get("mag", 0),
            "place": p.get("place", "")[:120],
            "time": iso,
            "longitude": coords[0] if len(coords) > 0 else 0,
            "latitude": coords[1] if len(coords) > 1 else 0,
            "depth_km": coords[2] if len(coords) > 2 else 0,
            "tsunami_flag": p.get("tsunami", 0),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r.get("magnitude") or 0, reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "eq_id", "magnitude", "place", "time",
                "longitude", "latitude", "depth_km",
                "tsunami_flag", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"usgs_eq: {len(rows)} quakes | strongest "
          f"M{top.get('magnitude','?')} {top.get('place','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
