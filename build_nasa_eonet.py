#!/usr/bin/env python3
"""build_nasa_eonet.py — NASA EONET natural events feed.

Earth Observatory Natural Event Tracker aggregates wildfires, severe
storms, volcanoes, sea/lake ice, landslides, drought, water color/
temperature, dust/haze, and manmade events. Each event has source
provenance (IRWIN/InciWeb for US fires, Smithsonian for volcanoes,
GDACS for global disasters) and geometry (point or polygon).

Equity impact map:
- **Wildfires**: PCG (Pacific Gas), EIX (Edison Int'l) — California
  wildfire liability. ALL, TRV, CB on homeowner exposure. SWBI (Smith
  & Wesson) briefly hit 2018/2020 on Civil-unrest adjacent fires.
  WY (Weyerhaeuser), PCH (PotlatchDeltic) on timberland losses.
- **Volcanoes**: RCL, CCL, NCLH — Caribbean/Pacific cruise itineraries.
  Ash cloud over Europe → airline crisis (LHA.DE, AF.PA). Iceland
  volcanic eruptions = airline sympathy short-term.
- **Floods**: DE, AGCO farm-equipment delivery delays; insurance
  (ALL, TRV) loss ratio. HD/LOW rebuilding demand.
- **Landslides**: Rare but severe; coal/mining (BTU, ARCH, HCC) if near
  operations; specific company exposure needed.

Trade uses:
- Wildfire within 30mi of CA nuclear or gas infrastructure: short PCG,
  EIX over 3-5d window.
- Major volcano Smithsonian Alert "Orange/Red": avoid long-cruise trades
  on itinerary basin (watch RCL/CCL exposures).
- Multiple simultaneous catastrophe events (>3 active category RED):
  reinsurance rate-hike narrative long RE/RNR.

Source: eonet.gsfc.nasa.gov/api/v3/events (free, no key, JSON).

Output: nasa_eonet.csv
Columns: event_id, title, category, source, status, start_date,
         lat, lon, link, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nasa_eonet.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://eonet.gsfc.nasa.gov/api/v3/events?days=60&status=all"


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nasa_eonet: {e}")
        return None


def _first_point(geometry: list) -> tuple[str, str, str]:
    """Return (start_date, lat, lon) for the most-recent point/poly."""
    if not geometry:
        return "", "", ""
    # Geometries sorted oldest→newest in EONET; take last
    g = geometry[-1]
    date = (g.get("date") or "")[:10]
    coords = g.get("coordinates") or []
    gtype = g.get("type", "")
    if gtype == "Point" and len(coords) >= 2:
        return date, str(coords[1]), str(coords[0])
    # Polygon: take first ring's first vertex
    if gtype == "Polygon" and coords and coords[0]:
        first = coords[0][0]
        if len(first) >= 2:
            return date, str(first[1]), str(first[0])
    return date, "", ""


def main() -> None:
    data = fetch() or {}
    events = data.get("events") or []
    if not events and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"nasa_eonet: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for ev in events:
        cats = ev.get("categories") or []
        category = cats[0].get("title", "") if cats else ""
        sources = ev.get("sources") or []
        src = sources[0].get("id", "") if sources else ""
        start, lat, lon = _first_point(ev.get("geometry") or [])
        status = "closed" if ev.get("closed") else "open"
        rows.append({
            "event_id": ev.get("id", ""),
            "title": (ev.get("title") or "")[:120],
            "category": category,
            "source": src,
            "status": status,
            "start_date": start,
            "lat": lat,
            "lon": lon,
            "link": ev.get("link", ""),
        })

    rows.sort(key=lambda r: r["start_date"], reverse=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["event_id", "title", "category", "source",
                        "status", "start_date", "lat", "lon", "link",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    open_ev = [r for r in rows if r["status"] == "open"]
    by_cat: dict[str, int] = {}
    for r in open_ev:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    top = sorted(by_cat.items(), key=lambda kv: -kv[1])[:3]
    top_s = ", ".join(f"{c}={n}" for c, n in top)
    print(f"nasa_eonet: {len(rows)} events 60d "
          f"({len(open_ev)} open) | {top_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
