#!/usr/bin/env python3
"""collision_engine.py — Domain 3: NOAA/USGS Spatial Collision Detection.

Checks if corporate geospatial assets (from extract_geo_assets.py) overlap
with NOAA hurricane forecast cones or USGS earthquake zones.

Physics: When a company's physical asset is inside a threat polygon:
    - Inject "Physical Shock" velocity boost (+15) into collision_alerts.json
    - scoring_engine.py reads these alerts and adds them to catalyst_events
    - HUD: ticker node pulses red/yellow with "Domain 3 Violation" border

Lead Latency: Monitors NOAA FORECAST CONES (not just current storm positions)
    so threats are flagged before the storm arrives — pre-market blindness
    eliminated.

Feeds:
    NOAA NHC: https://www.nhc.noaa.gov/CurrentStorms.json (active storms)
              https://www.nhc.noaa.gov/storm_graphics/{id}/refresh/AL{id}+{date}A_cone_lalo.json
    NOAA IEM: https://mesonet.agron.iastate.edu/geojson/sbw.geojson (all active warnings)
    USGS:     https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson

Output: collision_alerts.json
    {
      "timestamp": "...",
      "collisions": [
        {
          "ticker": "NVDA",
          "asset_type": "Manufacturing",
          "address": "...",
          "lat": 37.33, "lon": -122.03,
          "threat_type": "hurricane|earthquake|severe_storm",
          "threat_name": "Hurricane Milton",
          "threat_level": "CRITICAL|HIGH|MEDIUM",
          "shock_velocity": 15.0,
          "hud_pulse": "red"
        }
      ]
    }

Run modes:
    python3 collision_engine.py              # single check + write
    python3 collision_engine.py --watch      # continuous 5-min polling
    python3 collision_engine.py --status     # print active collisions

Pure stdlib — no shapely/numpy/pandas.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
UA   = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 contact@catalystedge.com")

# Physical Shock velocity injected when a corporate asset is inside a threat zone
SHOCK_VELOCITY_CRITICAL = 15.0   # direct overlap
SHOCK_VELOCITY_HIGH     = 8.0    # forecast cone overlap
SHOCK_VELOCITY_MEDIUM   = 3.0    # nearby warning zone

# Earthquake magnitude thresholds
EQ_CRITICAL_MAG = 6.5
EQ_HIGH_MAG     = 5.5

# Polling interval for --watch mode (5 minutes)
WATCH_INTERVAL_SEC = 5 * 60


# ── Pure-Python point-in-polygon (ray casting, O(n) per point) ───────────────
def _point_in_ring(lon: float, lat: float, ring: list) -> bool:
    """Ray casting algorithm — True if (lon, lat) is inside the ring polygon."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_intersect:
                inside = not inside
        j = i
    return inside


def point_in_polygon(lon: float, lat: float, rings: list) -> bool:
    """
    Test point against a GeoJSON Polygon ring set.
    rings[0] = outer boundary, rings[1:] = holes to exclude.
    """
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if _point_in_ring(lon, lat, hole):
            return False  # inside a hole = outside the polygon
    return True


def point_in_feature(lon: float, lat: float, feature: dict) -> bool:
    """Test point against a GeoJSON Feature (Polygon or MultiPolygon)."""
    geom  = feature.get("geometry") or {}
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if gtype == "Polygon":
        return point_in_polygon(lon, lat, coords)
    elif gtype == "MultiPolygon":
        return any(point_in_polygon(lon, lat, poly) for poly in coords)
    return False


# ── Haversine distance (km) — for earthquake radius checks ───────────────────
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _fetch_json(url: str, timeout: int = 15) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        print(f"  WARN: fetch {url[:70]}: {exc}")
        return None


# ── Data feeds ────────────────────────────────────────────────────────────────
def fetch_noaa_active_warnings() -> list[dict]:
    """
    Fetch all active NOAA severe weather polygons from IEM GeoJSON feed.
    Includes tornadoes, severe thunderstorms, flash floods, tropical storms.
    Returns list of GeoJSON features.
    """
    url = "https://mesonet.agron.iastate.edu/geojson/sbw.geojson"
    data = _fetch_json(url)
    if not data:
        return []
    return data.get("features", [])


def fetch_noaa_current_storms() -> list[dict]:
    """
    Fetch NOAA NHC active tropical storms.
    Returns list of storm dicts with name, id.
    """
    url  = "https://www.nhc.noaa.gov/CurrentStorms.json"
    data = _fetch_json(url)
    if not data:
        return []
    return data.get("activeStorms", [])


def fetch_nhc_cone(storm_id: str, basin: str = "al") -> list[dict]:
    """
    Fetch the NHC forecast cone GeoJSON for a named storm.
    Returns list of GeoJSON features (the 5-day cone polygon).
    Lead Latency: this is the FORECAST cone, not the current position.
    """
    url = (f"https://www.nhc.noaa.gov/storm_graphics/{basin.upper()}"
           f"/{basin.upper()}{storm_id}_latest/refresh/"
           f"{basin.upper()}{storm_id}_cone_lalo.json")
    data = _fetch_json(url)
    if not data:
        return []
    return data.get("features", []) if isinstance(data, dict) else []


def fetch_usgs_earthquakes() -> list[dict]:
    """
    Fetch significant USGS earthquakes from the past week.
    Returns list of GeoJSON features.
    """
    url  = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0"
            "/summary/significant_week.geojson")
    data = _fetch_json(url)
    if not data:
        return []
    return data.get("features", [])


# ── Collision detection ───────────────────────────────────────────────────────
def _earthquake_radius_km(magnitude: float) -> float:
    """Approximate felt-radius in km for a given earthquake magnitude."""
    # Rough empirical: M5.5 ≈ 200km, M6.5 ≈ 500km, M7.5 ≈ 1000km
    if magnitude >= 7.5:
        return 1000.0
    elif magnitude >= 6.5:
        return 500.0
    elif magnitude >= 5.5:
        return 200.0
    return 100.0


def check_collisions(entity_master: dict,
                     noaa_warnings: list[dict],
                     noaa_storms: list[dict],
                     usgs_quakes: list[dict]) -> list[dict]:
    """
    Perform spatial join between corporate geospatial_nodes and threat polygons.

    Parameters
    ----------
    entity_master : dict   Full entity_master.json
    noaa_warnings : list   IEM severe weather GeoJSON features
    noaa_storms   : list   NHC active storm list
    usgs_quakes   : list   USGS earthquake GeoJSON features

    Returns
    -------
    list of collision dicts (one per ticker-asset-threat combination)
    """
    collisions: list[dict] = []

    for ticker, rec in entity_master.items():
        nodes = rec.get("geospatial_nodes", [])
        if not nodes:
            continue

        for node in nodes:
            lat = node.get("lat")
            lon = node.get("lon")
            if lat is None or lon is None:
                continue

            # ── NOAA severe weather polygons ─────────────────────────────────
            for feature in noaa_warnings:
                props = feature.get("properties", {})
                phenom = props.get("phenomena", "")
                sig    = props.get("significance", "")
                evtype = props.get("eventtype", "")

                # Only flag warnings with actual polygons (not points)
                if not feature.get("geometry"):
                    continue

                if point_in_feature(lon, lat, feature):
                    # Determine threat level by warning type
                    if phenom in ("HU", "TY"):   # hurricane/typhoon warning
                        level = "CRITICAL"
                        shock = SHOCK_VELOCITY_CRITICAL
                    elif phenom in ("TO",):       # tornado warning
                        level = "CRITICAL"
                        shock = SHOCK_VELOCITY_CRITICAL
                    elif phenom in ("FF", "FA"):  # flash flood
                        level = "HIGH"
                        shock = SHOCK_VELOCITY_HIGH
                    else:
                        level = "MEDIUM"
                        shock = SHOCK_VELOCITY_MEDIUM

                    collisions.append({
                        "ticker":       ticker,
                        "asset_type":   node.get("type", "unknown"),
                        "address":      node.get("address", ""),
                        "lat":          lat,
                        "lon":          lon,
                        "threat_type":  "severe_weather",
                        "threat_name":  evtype or f"{phenom}.{sig}",
                        "threat_level": level,
                        "shock_velocity": shock,
                        "hud_pulse":    "red" if level == "CRITICAL" else "yellow",
                    })

            # ── USGS earthquakes (radius-based) ──────────────────────────────
            for feature in usgs_quakes:
                props = feature.get("properties", {})
                mag   = props.get("mag", 0) or 0
                if mag < EQ_HIGH_MAG:
                    continue
                geom  = feature.get("geometry", {})
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue
                eq_lon, eq_lat = coords[0], coords[1]

                dist_km = haversine_km(lat, lon, eq_lat, eq_lon)
                radius  = _earthquake_radius_km(mag)

                if dist_km <= radius:
                    level = "CRITICAL" if mag >= EQ_CRITICAL_MAG else "HIGH"
                    collisions.append({
                        "ticker":       ticker,
                        "asset_type":   node.get("type", "unknown"),
                        "address":      node.get("address", ""),
                        "lat":          lat,
                        "lon":          lon,
                        "threat_type":  "earthquake",
                        "threat_name":  props.get("place", f"M{mag:.1f} earthquake"),
                        "threat_level": level,
                        "magnitude":    mag,
                        "distance_km":  round(dist_km, 1),
                        "shock_velocity": SHOCK_VELOCITY_CRITICAL if level == "CRITICAL"
                                          else SHOCK_VELOCITY_HIGH,
                        "hud_pulse":    "red" if level == "CRITICAL" else "orange",
                    })

    return collisions


# ── Write collision_alerts.json ───────────────────────────────────────────────
def write_collision_alerts(collisions: list[dict]) -> dict:
    """Persist collision alerts and return the snapshot dict."""
    snap = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "collision_count": len(collisions),
        "collisions": collisions,
        # Convenience dict: {ticker: [collisions]} for scoring_engine.py lookup
        "by_ticker":  {},
    }
    for c in collisions:
        t = c["ticker"]
        snap["by_ticker"].setdefault(t, []).append(c)

    out = ROOT / "collision_alerts.json"
    out.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


# ── Status display ────────────────────────────────────────────────────────────
def print_collision_status(snap: dict) -> None:
    ts    = snap.get("timestamp", "")[:19]
    count = snap.get("collision_count", 0)
    print(f"\n{'─'*60}")
    print(f"  Domain 3 Collision Engine  [{ts} UTC]")
    print(f"{'─'*60}")
    if count == 0:
        print("  No active threat collisions. All assets clear.")
    else:
        print(f"  ⚠️  {count} ACTIVE COLLISION(S) DETECTED")
        print()
        for c in snap.get("collisions", []):
            icon = "🔴" if c["threat_level"] == "CRITICAL" else "🟡"
            print(f"  {icon} [{c['threat_level']:8s}] {c['ticker']:8s} "
                  f"{c['asset_type']:15s} → {c['threat_name']}")
            print(f"    {c['address']}")
            print(f"    Shock velocity: +{c['shock_velocity']} | "
                  f"HUD pulse: {c['hud_pulse']}")
    print(f"{'─'*60}\n")


# ── Load entity master ────────────────────────────────────────────────────────
def _load_entity_master() -> dict:
    p = ROOT / "entity_master.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── Main ──────────────────────────────────────────────────────────────────────
def run_once() -> dict:
    """Single collision check pass. Returns the snapshot dict."""
    em = _load_entity_master()
    geo_count = sum(1 for r in em.values() if r.get("geospatial_nodes"))
    print(f"collision_engine: {len(em)} entities | "
          f"{geo_count} with geospatial nodes")

    if geo_count == 0:
        print("  No geospatial nodes yet — run extract_geo_assets.py first")
        snap = write_collision_alerts([])
        return snap

    print("  Fetching NOAA severe weather warnings...")
    noaa_warnings = fetch_noaa_active_warnings()
    print(f"  NOAA warnings: {len(noaa_warnings)} active polygons")

    print("  Fetching NOAA active storms...")
    noaa_storms = fetch_noaa_current_storms()
    print(f"  NOAA storms: {len(noaa_storms)} active")

    print("  Fetching USGS significant earthquakes (7d)...")
    usgs_quakes = fetch_usgs_earthquakes()
    print(f"  USGS earthquakes: {len(usgs_quakes)} significant events")

    collisions = check_collisions(em, noaa_warnings, noaa_storms, usgs_quakes)
    snap = write_collision_alerts(collisions)
    return snap


def main() -> None:
    watch  = "--watch"  in sys.argv
    status = "--status" in sys.argv

    if status:
        p = ROOT / "collision_alerts.json"
        if p.exists():
            snap = json.loads(p.read_text())
        else:
            snap = run_once()
        print_collision_status(snap)
        return

    if watch:
        print(f"collision_engine: watch mode — checking every {WATCH_INTERVAL_SEC//60} min")
        while True:
            snap = run_once()
            print_collision_status(snap)
            if snap.get("collision_count", 0) > 0:
                print(f"  ⚡ {snap['collision_count']} collision(s) written to collision_alerts.json")
            time.sleep(WATCH_INTERVAL_SEC)
    else:
        snap = run_once()
        print_collision_status(snap)
        print("collision_engine: collision_alerts.json updated")


if __name__ == "__main__":
    main()
