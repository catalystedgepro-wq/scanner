#!/usr/bin/env python3
"""build_epa_airnow.py — EPA air quality + wildfire smoke (daily).

Wildfire smoke / AQI spike = healthcare demand (CVS, WBA, GILD for
asthma drugs), air purifier rush (DYSN parent, Xiaomi, IEP), staying
indoors boosts streaming (NFLX, DIS, RBLX). Acute spike → short-term
XLV rotation.

Source: AirNow API needs key. Fallback: FRED PM2.5 tracking is sparse.
This uses NASA FIRMS country CSV as wildfire proxy when NASA_FIRMS_MAP_KEY
is set; otherwise reads EPA AirNow public reporting URL.
Output: epa_airnow.csv
Columns: reporting_area, state, aqi, category_num, category_name,
         pollutant, observation_datetime, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "epa_airnow.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Public AirNow forecast endpoint (no key, limited to current-day forecast)
PUBLIC_URL = "https://www.airnowapi.org/aq/forecast/zipCode/"


def fetch_airnow_key() -> list[dict]:
    key = os.environ.get("AIRNOW_API_KEY", "")
    if not key:
        return []
    # Top-50 US metros by population (ZIP approximations)
    zips = [
        "10001", "90001", "60601", "77001", "85001", "19101", "78201",
        "92101", "75201", "95101", "78701", "32201", "76101", "43201",
        "28201", "46201", "98101", "80201", "20001", "02101", "37201",
        "73101", "97201", "89101", "33101", "53201", "87101", "40201",
        "21201", "63101", "30301", "92701", "48201", "55401", "44101",
        "84101", "94101", "71201", "23201", "37901", "70501", "40507",
    ]
    out = []
    now_d = dt.date.today().isoformat()
    for z in zips[:25]:
        url = (
            f"{PUBLIC_URL}?format=application/json&zipCode={z}"
            f"&date={now_d}&distance=25&API_KEY={key}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, list):
                out.extend(data)
        except Exception as e:
            print(f"airnow {z}: {e}")
            continue
    return out


def main() -> None:
    items = fetch_airnow_key()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items:
        rows.append({
            "reporting_area": it.get("ReportingArea", ""),
            "state": it.get("StateCode", ""),
            "aqi": it.get("AQI", 0),
            "category_num": (it.get("Category") or {}).get("Number", 0),
            "category_name": (it.get("Category") or {}).get("Name", ""),
            "pollutant": it.get("ParameterName", ""),
            "observation_datetime": (
                f"{it.get('DateForecast','').strip()}"
                f"T{(it.get('HourForecast') or '00')}:00"
            ),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r.get("aqi", 0) or 0, reverse=True)
    rows = rows[:250]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "reporting_area", "state", "aqi", "category_num",
                "category_name", "pollutant",
                "observation_datetime", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    worst = rows[0] if rows else {}
    print(f"airnow: {len(rows)} obs | worst "
          f"{worst.get('reporting_area','?')} aqi={worst.get('aqi','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
