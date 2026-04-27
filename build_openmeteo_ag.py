#!/usr/bin/env python3
"""build_openmeteo_ag.py — Weather forecast for ag commodity hubs.

Open-Meteo gives 7-day numerical weather forecasts with no API key.
Corn/soy/wheat yields are driven by temperature anomalies and
precipitation timing during the April-September growing window.
Hurricanes in Gulf shipping lanes disrupt LNG/oil tanker berthing.

Locations tracked:
- Iowa corn/soy belt   Des Moines, IA       41.6, -93.6
- Illinois grain       Springfield, IL      39.8, -89.6
- Kansas wheat         Wichita, KS          37.7, -97.3
- Nebraska corn        Lincoln, NE          40.8, -96.7
- Minnesota soy        Minneapolis, MN      44.98, -93.26
- Texas cotton         Lubbock, TX          33.58, -101.86
- California almonds   Fresno, CA           36.75, -119.77
- Florida citrus       Orlando, FL          28.54, -81.38
- Brazil soy (Mato Gro.) Cuiaba              -15.60, -56.1
- Argentine soy        Rosario              -32.95, -60.65
- Gulf LNG             Sabine Pass, TX      29.73, -93.87
- NYC power+heat       Manhattan, NY        40.78, -73.96

Output columns (daily, 3-day window):
  location, lat, lon, forecast_date, tmax_c, tmin_c, precip_mm,
  wind_max_ms, captured_at

Signal for trading:
- Iowa/IL tmax > 33 C + precip_mm < 2 over 7d = yield stress window
  late June-Aug -> bid CORN, SOYB; fade ADM/BG input-cost exposure.
- Gulf wind_max > 25 m/s forecast + fixed path = hurricane lane
  disruption -> bid RB (RBOB gasoline), fade CCL/RCL (cruises).
- NYC tmax > 32 C + 5-day heatwave = power peaker burn -> bid VST,
  CEG, NRG.

Source: api.open-meteo.com/v1/forecast (no key, CC-BY).

Output: openmeteo_ag.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "openmeteo_ag.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

LOCATIONS = [
    ("iowa_corn", 41.60, -93.60),
    ("illinois_grain", 39.80, -89.60),
    ("kansas_wheat", 37.70, -97.30),
    ("nebraska_corn", 40.80, -96.70),
    ("minnesota_soy", 44.98, -93.26),
    ("texas_cotton", 33.58, -101.86),
    ("california_almond", 36.75, -119.77),
    ("florida_citrus", 28.54, -81.38),
    ("brazil_soy", -15.60, -56.10),
    ("argentina_soy", -32.95, -60.65),
    ("gulf_lng", 29.73, -93.87),
    ("nyc_power", 40.78, -73.96),
]


def _fetch(lat: float, lon: float) -> dict | None:
    qs = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": ("temperature_2m_max,temperature_2m_min,"
                  "precipitation_sum,wind_speed_10m_max"),
        "timezone": "UTC",
        "forecast_days": "7",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"openmeteo_ag {lat},{lon}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for name, lat, lon in LOCATIONS:
        d = _fetch(lat, lon)
        if not d or "daily" not in d:
            continue
        daily = d["daily"]
        dates = daily.get("time", []) or []
        tmax = daily.get("temperature_2m_max", []) or []
        tmin = daily.get("temperature_2m_min", []) or []
        precip = daily.get("precipitation_sum", []) or []
        wind = daily.get("wind_speed_10m_max", []) or []
        for i, date_s in enumerate(dates):
            rows.append({
                "location": name,
                "lat": f"{lat:.4f}",
                "lon": f"{lon:.4f}",
                "forecast_date": date_s,
                "tmax_c": (f"{float(tmax[i]):.1f}"
                           if i < len(tmax) and tmax[i] is not None
                           else ""),
                "tmin_c": (f"{float(tmin[i]):.1f}"
                           if i < len(tmin) and tmin[i] is not None
                           else ""),
                "precip_mm": (f"{float(precip[i]):.2f}"
                              if i < len(precip)
                              and precip[i] is not None else ""),
                "wind_max_ms": (f"{float(wind[i]) / 3.6:.1f}"
                                if i < len(wind) and wind[i] is not None
                                else ""),
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"openmeteo_ag: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["location"], r["forecast_date"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["location", "lat", "lon", "forecast_date",
                  "tmax_c", "tmin_c", "precip_mm", "wind_max_ms",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    locs = len(set(r["location"] for r in rows))
    # Peek Iowa + Gulf for summary.
    ia = [r for r in rows if r["location"] == "iowa_corn"]
    gl = [r for r in rows if r["location"] == "gulf_lng"]
    ia_s = (f"IA tmax 7d avg {sum(float(r['tmax_c']) for r in ia if r['tmax_c']) / max(1, len(ia)):.1f}C"
            if ia else "")
    gl_s = (f"Gulf wind peak={max((float(r['wind_max_ms']) for r in gl if r['wind_max_ms']), default=0):.1f} m/s"
            if gl else "")
    print(f"openmeteo_ag: {len(rows)} rows across {locs} locations "
          f"| {ia_s} | {gl_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
