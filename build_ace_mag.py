#!/usr/bin/env python3
"""build_ace_mag.py — NOAA SWPC ACE magnetometer 1-hour feed.

Interplanetary magnetic field at L1. Southward Bz (negative GSM Bz)
reconnects with Earth's magnetosphere and drives geomagnetic storms —
early warning (30-60 min lead) before Kp responds.

Bz < -10 nT for sustained periods correlates with G1-G3 storms:
  telecoms (VSAT, IRDM), utilities (grid transformer incidents),
  airlines (polar routes), precision ag (GPS accuracy).

Source: services.swpc.noaa.gov/json/ace/mag/ace_mag_1h.json.

Output: ace_mag.csv
Columns: time_tag, bt, bz_gsm, bx_gsm, by_gsm, lat, lon, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ace_mag.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://services.swpc.noaa.gov/json/ace/mag/ace_mag_1h.json"


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
        print(f"ace_mag: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ace_mag: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ace_mag: empty, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        bx = _f(item.get("gsm_bx"))
        by = _f(item.get("gsm_by"))
        bz = _f(item.get("gsm_bz"))
        bt = math.sqrt(bx * bx + by * by + bz * bz)
        rows.append({
            "time_tag": (item.get("time_tag") or "")[:19],
            "bt": f"{bt:.2f}",
            "bz_gsm": f"{bz:.2f}",
            "bx_gsm": f"{bx:.2f}",
            "by_gsm": f"{by:.2f}",
            "lat": f"{_f(item.get('gsm_lat')):.2f}",
            "lon": f"{_f(item.get('gsm_lon')):.2f}",
        })

    rows.sort(key=lambda r: r["time_tag"], reverse=True)
    rows = rows[:168]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["time_tag", "bt", "bz_gsm", "bx_gsm", "by_gsm",
                  "lat", "lon", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    max_bt = max(rows, key=lambda r: float(r["bt"]))
    min_bz = min(rows, key=lambda r: float(r["bz_gsm"]))
    southward = sum(1 for r in rows if float(r["bz_gsm"]) < -5)
    print(f"ace_mag: {len(rows)} hourly samples | max Bt="
          f"{max_bt['bt']} nT | min Bz={min_bz['bz_gsm']} nT | "
          f"southward_hours={southward} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
