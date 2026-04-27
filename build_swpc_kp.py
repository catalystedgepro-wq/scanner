#!/usr/bin/env python3
"""build_swpc_kp.py — NOAA SWPC planetary Kp 1-minute feed.

High-resolution Kp index. Kp >= 5 = geomagnetic storm (G1+).
Feeds alert deduplication layer for swpc_alerts and gives us a
numeric value for dashboards vs. just-text alerts.

Kp thresholds:
  5  = G1 (minor)     — mild grid fluctuations, HF aurora below 60° N
  6  = G2 (moderate)  — transformer damage possible at high lat
  7  = G3 (strong)    — pipeline corrosion, satellite drag, power surges
  8  = G4 (severe)    — widespread grid problems, voltage control issues
  9  = G5 (extreme)   — Carrington-class, continent-scale grid collapse

Source: services.swpc.noaa.gov/json/planetary_k_index_1m.json.

Output: swpc_kp.csv
Columns: time_tag, kp_index, estimated_kp, kp_label, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "swpc_kp.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"swpc_kp: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_kp: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_kp: empty, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kp_i = item.get("kp_index")
        kp_e = item.get("estimated_kp")
        try:
            kp_i_v = int(kp_i) if kp_i is not None else 0
        except (TypeError, ValueError):
            kp_i_v = 0
        try:
            kp_e_v = float(kp_e) if kp_e is not None else 0.0
        except (TypeError, ValueError):
            kp_e_v = 0.0
        if kp_e_v >= 9:
            label = "G5-extreme"
        elif kp_e_v >= 8:
            label = "G4-severe"
        elif kp_e_v >= 7:
            label = "G3-strong"
        elif kp_e_v >= 6:
            label = "G2-moderate"
        elif kp_e_v >= 5:
            label = "G1-minor"
        else:
            label = "quiet"
        rows.append({
            "time_tag": (item.get("time_tag") or "")[:19],
            "kp_index": str(kp_i_v),
            "estimated_kp": f"{kp_e_v:.2f}",
            "kp_label": label,
        })

    rows.sort(key=lambda r: r["time_tag"], reverse=True)
    rows = rows[:720]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["time_tag", "kp_index", "estimated_kp", "kp_label",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    peak = max(rows, key=lambda r: float(r["estimated_kp"]))
    storms = sum(1 for r in rows if float(r["estimated_kp"]) >= 5)
    print(f"swpc_kp: {len(rows)} samples | peak Kp="
          f"{peak['estimated_kp']} ({peak['kp_label']}) @ "
          f"{peak['time_tag']} | storm_minutes={storms} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
