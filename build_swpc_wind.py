#!/usr/bin/env python3
"""build_swpc_wind.py — NOAA SWPC real-time solar wind (RTSW).

Real-time solar wind speed + density from DSCOVR/ACE at L1.
Sustained proton_speed > 600 km/s signals high-speed stream arrival —
the physical mechanism behind most G1/G2 storms. Combined with the
ace_mag Bz spoke, this is the cleanest leading signal ~30 min
ahead of Kp.

Source: services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json.

Output: swpc_wind.csv
Columns: time_tag, source, proton_speed_kps, proton_density_pcc,
         proton_temperature_k, active, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "swpc_wind.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"swpc_wind: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_wind: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_wind: empty, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append({
            "time_tag": (item.get("time_tag") or "")[:19],
            "source": (item.get("source") or "")[:8],
            "proton_speed_kps": f"{_f(item.get('proton_speed')):.1f}",
            "proton_density_pcc": f"{_f(item.get('proton_density')):.2f}",
            "proton_temperature_k": f"{_f(item.get('proton_temperature')):.0f}",
            "active": "1" if item.get("active") else "0",
        })

    rows.sort(key=lambda r: r["time_tag"], reverse=True)
    rows = rows[:720]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["time_tag", "source", "proton_speed_kps",
                  "proton_density_pcc", "proton_temperature_k",
                  "active", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    peak = max(rows, key=lambda r: float(r["proton_speed_kps"]))
    high_stream = sum(1 for r in rows if float(r["proton_speed_kps"]) > 600)
    print(f"swpc_wind: {len(rows)} 1-min samples | peak_speed="
          f"{peak['proton_speed_kps']} km/s @ {peak['time_tag']} | "
          f"high_stream_minutes={high_stream} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
