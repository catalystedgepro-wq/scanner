#!/usr/bin/env python3
"""build_solar_cycle.py — NOAA SWPC observed solar cycle indices.

Monthly sunspot number (SSN) and F10.7 radio flux, 1749-present.
Solar maximum / declining cycle phase matters for:
- Satellite drag in LEO (Starlink, Planet Labs, ICEYE) — orbit decay
  rates spike during high F10.7
- Ionospheric HF conditions (shortwave broadcasters, maritime)
- Launch windows (cycle phase is part of rocket sizing budgets)
- Long-horizon power-grid risk (solar max concentrates CMEs)

Source: services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json

Output: solar_cycle.csv
Columns: month, ssn, smoothed_ssn, f107, smoothed_f107,
         cycle_phase, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "solar_cycle.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://services.swpc.noaa.gov/json/solar-cycle/"
       "observed-solar-cycle-indices.json")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"solar_cycle: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"solar_cycle: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"solar_cycle: empty, keeping existing {OUT_CSV.name}")
        return

    rows_raw: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ssn = item.get("ssn")
        sm_ssn = item.get("smoothed_ssn")
        f107 = item.get("f10.7")
        sm_f107 = item.get("smoothed_f10.7")
        try:
            ssn_v = float(ssn) if ssn is not None else -1.0
            sm_ssn_v = float(sm_ssn) if sm_ssn is not None else -1.0
            f107_v = float(f107) if f107 is not None else -1.0
            sm_f107_v = float(sm_f107) if sm_f107 is not None else -1.0
        except (TypeError, ValueError):
            continue
        rows_raw.append({
            "month": (item.get("time-tag") or "")[:7],
            "ssn": ssn_v,
            "smoothed_ssn": sm_ssn_v,
            "f107": f107_v,
            "smoothed_f107": sm_f107_v,
        })

    rows_raw.sort(key=lambda r: r["month"])
    tail = rows_raw[-72:]

    n = len(tail)
    for i, r in enumerate(tail):
        if n >= 3 and i >= 1:
            prev_sm = tail[i - 1]["smoothed_ssn"]
            cur_sm = r["smoothed_ssn"]
            if cur_sm > 0 and prev_sm > 0:
                if cur_sm - prev_sm > 1.0:
                    r["cycle_phase"] = "ascending"
                elif prev_sm - cur_sm > 1.0:
                    r["cycle_phase"] = "descending"
                else:
                    r["cycle_phase"] = "plateau"
            else:
                r["cycle_phase"] = "unknown"
        else:
            r["cycle_phase"] = "unknown"

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    out_rows: list[dict] = []
    for r in tail:
        out_rows.append({
            "month": r["month"],
            "ssn": f"{r['ssn']:.1f}",
            "smoothed_ssn": f"{r['smoothed_ssn']:.1f}",
            "f107": f"{r['f107']:.1f}",
            "smoothed_f107": f"{r['smoothed_f107']:.1f}",
            "cycle_phase": r["cycle_phase"],
            "captured_at": now,
        })

    out_rows.sort(key=lambda r: r["month"], reverse=True)

    fieldnames = ["month", "ssn", "smoothed_ssn", "f107",
                  "smoothed_f107", "cycle_phase", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    latest = out_rows[0] if out_rows else {}
    phases: dict[str, int] = {}
    for r in out_rows:
        phases[r["cycle_phase"]] = phases.get(r["cycle_phase"], 0) + 1
    print(f"solar_cycle: {len(out_rows)} months | latest "
          f"{latest.get('month', '?')} SSN={latest.get('ssn', '?')} "
          f"F10.7={latest.get('f107', '?')} phase="
          f"{latest.get('cycle_phase', '?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
