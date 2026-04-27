#!/usr/bin/env python3
"""build_nasa_neos.py — NASA JPL near-Earth object close approaches.

Tail-risk and headline risk. Close-approach events make media pushes,
drive insurance-linked securities, and are narrative fuel for space
sector (RKLB, LMT, BA, ASTR, MNTS, IRDM).

Signal:
- Asteroid within 0.01 AU (~3.9M km) with diameter > 100m = headline
  catalyst + scientific-press spike. Triggers RKLB/MNTS attention.
- NASA DART-style mitigation planning mentions = LMT/BA defense
  contract whispers.
- Close-approach dates cross-ref against space ETF (UFO, ROKT).

Output: nasa_neos.csv
Columns: designation, close_approach_dt, dist_au, dist_min_au,
v_rel_km_s, h_mag_abs, captured_at

Source: ssd-api.jpl.nasa.gov/cad.api (no key, live, 30-day window).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nasa_neos.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://ssd-api.jpl.nasa.gov/cad.api"
       "?date-min=now&date-max=%2B30&dist-max=0.1&body=Earth")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nasa_neos: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasa_neos: keeping existing {OUT_CSV.name}")
        return

    fields = d.get("fields") or []
    data = d.get("data") or []
    if not fields or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasa_neos: empty, keeping existing {OUT_CSV.name}")
        return

    idx = {f: i for i, f in enumerate(fields)}

    def g(row: list, key: str) -> str:
        i = idx.get(key)
        if i is None or i >= len(row):
            return ""
        return str(row[i] or "").strip()

    rows: list[dict] = []
    for row in data:
        try:
            dist = float(g(row, "dist"))
        except (ValueError, TypeError):
            dist = 0.0
        rows.append({
            "designation": g(row, "des")[:24],
            "close_approach_dt": g(row, "cd")[:20],
            "dist_au": g(row, "dist"),
            "dist_min_au": g(row, "dist_min"),
            "v_rel_km_s": g(row, "v_rel"),
            "v_inf_km_s": g(row, "v_inf"),
            "h_mag_abs": g(row, "h"),
            "_sort": dist,
        })

    rows.sort(key=lambda r: r["_sort"])
    for r in rows:
        del r["_sort"]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["designation", "close_approach_dt",
                  "dist_au", "dist_min_au",
                  "v_rel_km_s", "v_inf_km_s",
                  "h_mag_abs", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    closest = rows[0] if rows else None
    close_bit = (f"closest {closest['designation']} @ "
                 f"{closest['dist_au'][:7]} AU "
                 f"({closest['close_approach_dt']})"
                 if closest else "")
    print(f"nasa_neos: {len(rows)} approaches | {close_bit} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
