#!/usr/bin/env python3
"""build_ndbc_buoys.py — NOAA buoy real-time marine conditions.

Offshore buoys feed early storm, wave height, and wind data that
the public weather model spreads with a delay. Specific signal:
- Gulf of Mexico buoys 42001, 42002, 42040 track hurricanes before
  landfall (Gulf LNG export, offshore oil, FCX/XOM risk).
- NE Atlantic 44025, 44065 track nor'easters (NE utilities EIX/NEE/D,
  retail foot traffic, insurance XL/TRV).
- Pacific 46047, 46086 track Pacific storms → Port of LA/LB imports,
  ZIM/MAERSK rates.
- Alaska 46001, 46002 track Bering Sea crabbers and cargo.

Pressure drops > 10 hPa in 24h = rapid intensification flag. Wave
height > 8m = trade disruption. Wind > 25 m/s = hurricane-force
advisory.

Output: ndbc_buoys.csv
Columns: station, region, obs_time, wind_dir_deg, wind_speed_mps,
wind_gust_mps, wave_height_m, pressure_hpa, air_temp_c, water_temp_c,
captured_at

Source: ndbc.noaa.gov/data/realtime2/{station}.txt (no key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ndbc_buoys.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

# (station_id, region) — focus: hurricane lanes, port approaches,
# LNG corridors, fishing zones.
STATIONS = [
    # Gulf of Mexico (hurricane, oil, LNG)
    ("42001", "GulfMex_center"),
    ("42002", "GulfMex_west"),
    ("42040", "GulfMex_mobile"),
    ("42055", "GulfMex_yucatan"),
    # Atlantic (hurricane approach, nor'easter)
    ("41010", "Atl_CapeCanaveral"),
    ("41002", "Atl_scent"),
    ("44014", "Atl_virginia"),
    ("44025", "Atl_longisland"),
    ("44065", "Atl_nyharbor"),
    # Pacific (LA/LB approach, Pacific storms)
    ("46047", "Pac_sanpedro"),
    ("46086", "Pac_sandiego"),
    ("46042", "Pac_monterey"),
    ("46059", "Pac_offshore_calif"),
    # Alaska / Bering (crab, cargo)
    ("46001", "AK_gulf"),
    ("46002", "AK_offshore_wa_or"),
    ("46066", "AK_offshore"),
    # Great Lakes (salt, iron ore)
    ("45001", "Lake_superior"),
    ("45005", "Lake_erie"),
    # Hawaii
    ("51001", "HI_northwest"),
]


def _num(s: str) -> str:
    """Return '' for missing NDBC 'MM' placeholders."""
    s = (s or "").strip()
    if not s or s.upper() == "MM":
        return ""
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return ""


def _fetch(station: str) -> str | None:
    url = URL.format(station=station)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"ndbc_buoys {station}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for station, region in STATIONS:
        body = _fetch(station)
        if not body:
            continue
        lines = body.splitlines()
        data = [l for l in lines if l and not l.startswith("#")]
        if not data:
            continue
        # First data line is the most recent observation.
        fields = data[0].split()
        if len(fields) < 14:
            continue
        try:
            ts = (f"{fields[0]}-{fields[1]}-{fields[2]}T"
                  f"{fields[3]}:{fields[4]}Z")
        except IndexError:
            ts = ""
        rows.append({
            "station": station,
            "region": region,
            "obs_time": ts,
            "wind_dir_deg": _num(fields[5] if len(fields) > 5 else ""),
            "wind_speed_mps": _num(fields[6] if len(fields) > 6 else ""),
            "wind_gust_mps": _num(fields[7] if len(fields) > 7 else ""),
            "wave_height_m": _num(fields[8] if len(fields) > 8 else ""),
            "pressure_hpa": _num(fields[12] if len(fields) > 12 else ""),
            "air_temp_c": _num(fields[13] if len(fields) > 13 else ""),
            "water_temp_c": _num(fields[14] if len(fields) > 14 else ""),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ndbc_buoys: no data, keeping existing {OUT_CSV.name}")
        return

    # Sort by pressure ascending (lowest = strongest storm core).
    def press(r: dict) -> float:
        try:
            return float(r["pressure_hpa"]) if r["pressure_hpa"] \
                else 9999.0
        except ValueError:
            return 9999.0

    rows.sort(key=press)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["region", "station", "obs_time",
                  "wind_dir_deg", "wind_speed_mps", "wind_gust_mps",
                  "wave_height_m", "pressure_hpa",
                  "air_temp_c", "water_temp_c", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary.
    high_wave = [r for r in rows if r["wave_height_m"]
                 and float(r["wave_height_m"]) >= 5.0]
    low_press = rows[0] if rows else None
    lp_bit = (f"low_press: {low_press['region']} "
              f"{low_press['pressure_hpa']}hPa"
              if low_press and low_press["pressure_hpa"] else "")
    print(f"ndbc_buoys: {len(rows)} buoys "
          f"({len(high_wave)} wave>=5m) | {lp_bit} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
