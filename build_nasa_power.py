#!/usr/bin/env python3
"""build_nasa_power.py — NASA POWER solar/weather for energy hubs.

Daily point-based observations at 14 US energy production hubs:
solar-farm sites (AZ, NV, TX, CA), wind-farm sites (TX, IA, KS, OK),
and gas LNG export terminals (Gulf Coast). Signals utility-scale
solar/wind generation (SRE, NEE, DUK, ED, AEP, XEL), renewables ETFs
(ICLN, TAN, FAN, PBW), and LNG export throughput (LNG, EQT, CTRA).

Parameters (NASA POWER daily RE community):
- ALLSKY_SFC_SW_DWN kWh/m²/day shortwave down (solar insolation)
- T2M             °C     air temp at 2m
- WS10M           m/s    wind speed at 10m
- PRECTOTCORR     mm/day corrected precipitation
- RH2M            %      relative humidity at 2m

Output: nasa_power.csv
Columns: hub_code, hub_name, lat, lon, date, solar_kwh_m2,
temp_c, wind_m_s, precip_mm, rh_pct, captured_at

Source: power.larc.nasa.gov (no key, live). 15-day trailing window.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nasa_power.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://power.larc.nasa.gov/api/temporal/daily/point"

# (code, name, lat, lon, sector_tag)
HUBS = [
    ("phx_solar",   "Phoenix_solar_AZ",      33.45, -112.07, "solar"),
    ("lvg_solar",   "LasVegas_solar_NV",     36.17, -115.14, "solar"),
    ("perm_solar",  "Permian_solar_TX",      31.87, -102.34, "solar"),
    ("moja_solar",  "Mojave_solar_CA",       35.01, -117.29, "solar"),
    ("stx_solar",   "SouthTX_solar",         27.50, -99.50,  "solar"),
    ("pan_wind",    "Panhandle_wind_TX",     35.22, -101.83, "wind"),
    ("iac_wind",    "CentralIowa_wind",      41.59, -93.62,  "wind"),
    ("kss_wind",    "WesternKansas_wind",    38.38, -100.54, "wind"),
    ("oks_wind",    "OklahomaCity_wind",     35.46, -97.52,  "wind"),
    ("wyo_wind",    "Wyoming_wind",          41.14, -104.82, "wind"),
    ("sab_lng",     "SabinePass_LNG_LA",     29.73, -93.88,  "lng"),
    ("cor_lng",     "CorpusChristi_LNG_TX",  27.80, -97.40,  "lng"),
    ("fre_lng",     "Freeport_LNG_TX",       28.95, -95.36,  "lng"),
    ("cam_lng",     "Cameron_LNG_LA",        29.80, -93.32,  "lng"),
]

PARAMS = "ALLSKY_SFC_SW_DWN,T2M,WS10M,PRECTOTCORR,RH2M"


def _fetch(lat: float, lon: float, d_start: str, d_end: str) -> dict | None:
    qs = urllib.parse.urlencode({
        "parameters": PARAMS,
        "community": "RE",
        "longitude": f"{lon:.3f}",
        "latitude": f"{lat:.3f}",
        "start": d_start,
        "end": d_end,
        "format": "JSON",
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nasa_power fetch {lat},{lon}: {e}")
        return None


def _clean(v) -> str:
    try:
        f = float(v)
        if f <= -990.0:
            return ""
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return ""


def main() -> None:
    today = dt.date.today()
    # POWER daily has a ~3-5 day lag; request trailing 15 days so
    # we get at least 10 usable rows per hub.
    d_end = today
    d_start = today - dt.timedelta(days=15)
    s_start = d_start.strftime("%Y%m%d")
    s_end = d_end.strftime("%Y%m%d")

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    for code, name, lat, lon, tag in HUBS:
        data = _fetch(lat, lon, s_start, s_end)
        if not data:
            continue
        param = ((data.get("properties") or {}).get("parameter") or {})
        solar = param.get("ALLSKY_SFC_SW_DWN") or {}
        t2m = param.get("T2M") or {}
        ws = param.get("WS10M") or {}
        pr = param.get("PRECTOTCORR") or {}
        rh = param.get("RH2M") or {}
        dates = sorted(solar.keys())
        for d in dates:
            sv = _clean(solar.get(d))
            if not sv and not _clean(t2m.get(d)):
                continue
            rows.append({
                "hub_code": code,
                "hub_name": name,
                "sector": tag,
                "lat": f"{lat:.3f}",
                "lon": f"{lon:.3f}",
                "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "solar_kwh_m2": sv,
                "temp_c": _clean(t2m.get(d)),
                "wind_m_s": _clean(ws.get(d)),
                "precip_mm": _clean(pr.get(d)),
                "rh_pct": _clean(rh.get(d)),
                "captured_at": now,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasa_power: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["hub_code"], r["date"]))

    fieldnames = ["hub_code", "hub_name", "sector", "lat", "lon", "date",
                  "solar_kwh_m2", "temp_c", "wind_m_s", "precip_mm",
                  "rh_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_by_hub: dict[str, dict] = {}
    for r in rows:
        latest_by_hub[r["hub_code"]] = r
    phx = latest_by_hub.get("phx_solar", {})
    pan = latest_by_hub.get("pan_wind", {})
    sab = latest_by_hub.get("sab_lng", {})
    print(f"nasa_power: {len(rows)} rows across {len(latest_by_hub)} hubs | "
          f"Phoenix solar={phx.get('solar_kwh_m2','?')}kWh/m2 "
          f"Panhandle wind={pan.get('wind_m_s','?')}m/s "
          f"Sabine temp={sab.get('temp_c','?')}C -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
