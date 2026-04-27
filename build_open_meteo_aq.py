#!/usr/bin/env python3
"""build_open_meteo_aq.py — Air quality at major metro areas.

Air-quality spikes are direct economic catalysts via:
- Wildfire smoke (California tech, Pacific NW): remote-work days,
  reduced retail foot traffic, BA/RTX aerospace production pauses,
  utility liability (PCG, EIX fire lawsuits).
- Dust storms: ag (Kansas/Oklahoma wheat), solar (SPWR/FSLR panel
  efficiency), airline diversions (LUV, AAL Midwest routes).
- Industrial incidents (China PM2.5 spike > 500): manufacturing
  slowdown flag, supply-chain delay risk for AAPL/TSLA cells.

US AQI scale: 0-50 Good, 51-100 Moderate, 101-150 USG, 151-200
Unhealthy, 201-300 Very Unhealthy, 301+ Hazardous.

Tracked cities span US semi-corridor (SJ, Austin, Phoenix), industrial
hubs (Houston, Detroit), port cities (LA, Shanghai, Singapore), plus
key policy-sensitive capitals (DC, Beijing, Delhi, London).

Output: open_meteo_aq.csv
Columns: city, country, lat, lon, pm10, pm2_5, carbon_monoxide, ozone,
us_aqi, european_aqi, observation_time, captured_at

Source: air-quality-api.open-meteo.com (CAMS + EEA, no key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "open_meteo_aq.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://air-quality-api.open-meteo.com/v1/air-quality"
       "?latitude={lat}&longitude={lon}"
       "&current=pm10,pm2_5,carbon_monoxide,ozone,us_aqi,european_aqi"
       "&timezone=UTC")

CITIES = [
    ("NYC", "US", 40.7128, -74.0060),
    ("LA", "US", 34.0522, -118.2437),
    ("SF", "US", 37.7749, -122.4194),
    ("SanJose", "US", 37.3382, -121.8863),
    ("Seattle", "US", 47.6062, -122.3321),
    ("Portland", "US", 45.5152, -122.6784),
    ("Phoenix", "US", 33.4484, -112.0740),
    ("Denver", "US", 39.7392, -104.9903),
    ("Dallas", "US", 32.7767, -96.7970),
    ("Houston", "US", 29.7604, -95.3698),
    ("Chicago", "US", 41.8781, -87.6298),
    ("Detroit", "US", 42.3314, -83.0458),
    ("Atlanta", "US", 33.7490, -84.3880),
    ("Miami", "US", 25.7617, -80.1918),
    ("Boston", "US", 42.3601, -71.0589),
    ("DC", "US", 38.9072, -77.0369),
    ("Austin", "US", 30.2672, -97.7431),
    ("London", "GB", 51.5074, -0.1278),
    ("Paris", "FR", 48.8566, 2.3522),
    ("Frankfurt", "DE", 50.1109, 8.6821),
    ("Beijing", "CN", 39.9042, 116.4074),
    ("Shanghai", "CN", 31.2304, 121.4737),
    ("HK", "HK", 22.3193, 114.1694),
    ("Tokyo", "JP", 35.6762, 139.6503),
    ("Seoul", "KR", 37.5665, 126.9780),
    ("Singapore", "SG", 1.3521, 103.8198),
    ("Delhi", "IN", 28.6139, 77.2090),
    ("Mumbai", "IN", 19.0760, 72.8777),
    ("Dubai", "AE", 25.2048, 55.2708),
    ("SaoPaulo", "BR", -23.5505, -46.6333),
    ("Mexico", "MX", 19.4326, -99.1332),
    ("Sydney", "AU", -33.8688, 151.2093),
]


def _fetch(lat: float, lon: float) -> dict | None:
    url = URL.format(lat=lat, lon=lon)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"open_meteo_aq {lat},{lon}: {e}")
        return None


def _num(v) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return ""


def main() -> None:
    rows: list[dict] = []
    for city, cc, lat, lon in CITIES:
        d = _fetch(lat, lon)
        if not d:
            continue
        cur = d.get("current") or {}
        rows.append({
            "city": city,
            "country": cc,
            "lat": f"{lat:.4f}",
            "lon": f"{lon:.4f}",
            "pm10": _num(cur.get("pm10")),
            "pm2_5": _num(cur.get("pm2_5")),
            "carbon_monoxide": _num(cur.get("carbon_monoxide")),
            "ozone": _num(cur.get("ozone")),
            "us_aqi": _num(cur.get("us_aqi")),
            "european_aqi": _num(cur.get("european_aqi")),
            "observation_time": cur.get("time") or "",
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"open_meteo_aq: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    # Sort by us_aqi desc (worst air first).
    def aqi(r: dict) -> float:
        try:
            return -float(r["us_aqi"]) if r["us_aqi"] else 0.0
        except ValueError:
            return 0.0

    rows.sort(key=aqi)

    fieldnames = ["city", "country", "lat", "lon",
                  "pm10", "pm2_5", "carbon_monoxide", "ozone",
                  "us_aqi", "european_aqi",
                  "observation_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary.
    unhealthy = [r for r in rows
                 if r["us_aqi"] and float(r["us_aqi"]) >= 150]
    worst = rows[0] if rows else None
    worst_bit = (f"{worst['city']} us_aqi={worst['us_aqi']}"
                 if worst and worst["us_aqi"] else "")
    print(f"open_meteo_aq: {len(rows)} cities "
          f"({len(unhealthy)} unhealthy) | {worst_bit} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
