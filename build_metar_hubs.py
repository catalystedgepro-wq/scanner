#!/usr/bin/env python3
"""build_metar_hubs.py — Airport METAR conditions at major hubs.

METAR reports give ground-truth weather at airports every hour. At
hub airports, fog/snow/low-ceiling conditions trigger ATC ground
stops that cascade into carrier ops costs, fuel waste, and missed
connections. Cross-referenced with FAA FIS-B delay feed this gives a
forward-looking logistics signal.

Hubs tracked (IATA/ICAO primary + top traffic):
- KATL (Delta), KDFW (AA), KDEN (UA/WN), KORD (UA/AA),
  KLAX (AA/UA/DL), KCLT (AA), KLAS (WN), KPHX (AA/WN),
  KMIA (AA), KSEA (AS/DL), KIAH (UA), KJFK (DL/AA),
  KEWR (UA), KSFO (UA), KBOS (DL/B6), KMCO (WN/B6),
  KFLL (B6/NK), KDTW (DL), KMSP (DL), KPHL (AA)

Signal for trading:
- Visibility < 1 SM or ceiling < 500 ft at 3+ hubs simultaneously =
  wide ATC reroutes; fade AAL/DAL/UAL/LUV 1-day burst, bid B6/SAVE
  on disruption rebooking spread.
- Wind gusts > 45 kt at KJFK/KBOS/KEWR = Nor'easter ops; fade XOM/
  VLO (refinery receipts), bid AXP (business travel rebook revenue).
- Temp < -10 C sustained at KORD/KMSP + precip = heating fuel demand;
  bid UNG/BOIL.

Source: aviationweather.gov/api/data/metar (no key, JSON).

Output: metar_hubs.csv
Columns: icao_id, observed_at, temp_c, dewpoint_c, wind_dir_deg,
         wind_speed_kt, wind_gust_kt, visibility_sm,
         altimeter_in_hg, flight_category, raw_ob, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "metar_hubs.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

HUBS = [
    "KATL", "KDFW", "KDEN", "KORD", "KLAX", "KCLT", "KLAS", "KPHX",
    "KMIA", "KSEA", "KIAH", "KJFK", "KEWR", "KSFO", "KBOS", "KMCO",
    "KFLL", "KDTW", "KMSP", "KPHL",
]
URL = ("https://aviationweather.gov/api/data/metar"
       "?ids={}&format=json&hours=2")


def _flight_cat(vis_sm: float, ceil_ft: float) -> str:
    # FAA flight category thresholds.
    if ceil_ft > 0 and ceil_ft < 500:
        return "LIFR"
    if vis_sm > 0 and vis_sm < 1:
        return "LIFR"
    if ceil_ft > 0 and ceil_ft < 1000:
        return "IFR"
    if vis_sm > 0 and vis_sm < 3:
        return "IFR"
    if ceil_ft > 0 and ceil_ft < 3000:
        return "MVFR"
    if vis_sm > 0 and vis_sm < 5:
        return "MVFR"
    if vis_sm > 0 and ceil_ft > 0:
        return "VFR"
    return ""


def main() -> None:
    url = URL.format(",".join(HUBS))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"metar_hubs: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"metar_hubs: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(d, list):
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"metar_hubs: unexpected payload, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Keep only latest observation per ICAO.
    latest: dict[str, dict] = {}
    for m in d:
        icao = m.get("icaoId") or ""
        if not icao:
            continue
        obs = m.get("obsTime") or 0
        cur = latest.get(icao)
        if cur is None or obs > (cur.get("obsTime") or 0):
            latest[icao] = m

    rows: list[dict] = []
    for icao in HUBS:
        m = latest.get(icao)
        if not m:
            continue
        obs_ts = m.get("obsTime") or 0
        obs_iso = ""
        if isinstance(obs_ts, (int, float)) and obs_ts > 0:
            obs_iso = (dt.datetime.fromtimestamp(
                obs_ts, tz=dt.timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"))
        try:
            vis = float(m.get("visib") or 0) if m.get("visib") else 0.0
        except (TypeError, ValueError):
            vis = 0.0
        # Cloud layers — find lowest ceiling (BKN/OVC).
        ceil = 0.0
        for cld in m.get("clouds", []) or []:
            cov = cld.get("cover") or ""
            base = cld.get("base")
            if cov in ("BKN", "OVC") and base:
                try:
                    b = float(base)
                except (TypeError, ValueError):
                    continue
                if ceil == 0.0 or b < ceil:
                    ceil = b
        rows.append({
            "icao_id": icao,
            "observed_at": obs_iso,
            "temp_c": (f"{float(m['temp']):.1f}"
                       if m.get("temp") is not None else ""),
            "dewpoint_c": (f"{float(m['dewp']):.1f}"
                           if m.get("dewp") is not None else ""),
            "wind_dir_deg": str(m.get("wdir") or ""),
            "wind_speed_kt": str(m.get("wspd") or ""),
            "wind_gust_kt": str(m.get("wgst") or ""),
            "visibility_sm": f"{vis:.1f}" if vis else "",
            "altimeter_in_hg": (f"{float(m['altim']) / 33.8639:.2f}"
                                if m.get("altim") else ""),
            "flight_category": _flight_cat(vis, ceil),
            "raw_ob": (m.get("rawOb") or "")[:160],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"metar_hubs: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["icao_id", "observed_at", "temp_c", "dewpoint_c",
                  "wind_dir_deg", "wind_speed_kt", "wind_gust_kt",
                  "visibility_sm", "altimeter_in_hg",
                  "flight_category", "raw_ob", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Count IFR/LIFR for trading summary.
    ifr = sum(1 for r in rows if r["flight_category"] in ("IFR", "LIFR"))
    mvfr = sum(1 for r in rows if r["flight_category"] == "MVFR")
    print(f"metar_hubs: {len(rows)} reports | {ifr} IFR+, {mvfr} MVFR "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
