#!/usr/bin/env python3
"""build_nasa_firms.py — NASA FIRMS near-real-time wildfire detections.

NASA's Fire Information for Resource Management System publishes VIIRS
satellite fire detections every ~6h. Active wildfires → utility wildfire
liability (PCG, SRE, EIX), insurance (ALL, TRV, CB, AIG), timber (WY),
agriculture (processor plant risk). Major conflagrations move commodity
markets (lumber, cattle).

Source: firms.modaps.eosdis.nasa.gov area-based CSV (no auth key for
small-area, recent; full country data needs MAP_KEY).

Output: nasa_firms.csv
Columns: date, country, latitude, longitude, confidence, bright_ti4, frp, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "nasa_firms.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KEY = os.environ.get("NASA_FIRMS_MAP_KEY", "")

# USA VIIRS last 24h
# Format: https://firms.modaps.eosdis.nasa.gov/api/country/csv/{KEY}/VIIRS_SNPP_NRT/USA/1
# RUS dropped 2026-04-27 — NASA returns HTTP 400 (area too large) for the
# country endpoint on RUS. Substituted with Mediterranean fire-prone set.
COUNTRIES = ["USA", "CAN", "BRA", "AUS", "IDN", "GRC", "PRT", "ESP"]


def fetch(country: str) -> str:
    if not KEY:
        return ""
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/"
        f"{KEY}/VIIRS_SNPP_NRT/{country}/1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"firms {country}: {e}")
        return ""


def parse(country: str, csv_text: str) -> list[dict]:
    out = []
    buf = io.StringIO(csv_text)
    reader = csv.DictReader(buf)
    for row in reader:
        try:
            conf = row.get("confidence", "") or ""
            if conf in {"l", "low"}:  # discard low confidence
                continue
            out.append({
                "date": row.get("acq_date", ""),
                "country": country,
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
                "confidence": conf,
                "bright_ti4": row.get("bright_ti4", ""),
                "frp": row.get("frp", ""),
            })
        except Exception:
            continue
    return out


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if not KEY:
        print("nasa_firms: NASA_FIRMS_MAP_KEY not set; writing stub")
    else:
        for c in COUNTRIES:
            rows.extend(parse(c, fetch(c))[:500])  # cap per country
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "country", "latitude", "longitude",
                "confidence", "bright_ti4", "frp", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"nasa_firms: {len(rows)} fires ({'KEYED' if KEY else 'NO-KEY stub'}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
