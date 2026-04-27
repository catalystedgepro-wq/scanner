#!/usr/bin/env python3
"""build_boc_yields.py — Bank of Canada benchmark bond yields.

Canada is the 12th largest equity market and hosts major energy,
mining, and rail names (SU, CNQ, TECK, FCX, CNI, CP, BMO, RY, TD).
Canadian bond yields lead US by 30-60 minutes thanks to shorter time
zone, so moves in GoC 2Y/10Y often telegraph the US 2Y/10Y open reaction.

Yield-curve inversion signal: 2Y-10Y spread flip is a global
recession tell. Canada inverts ~3 months before the US historically.

Output: boc_yields.csv
Columns: tenor, yield_pct, observation_date, captured_at

Source: www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json
(no key, live, 5 most recent business days).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "boc_yields.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www.bankofcanada.ca/valet/observations/group/"
       "bond_yields_benchmark/json?recent=30")

# Valet series ID -> (tenor label, sort order).
SERIES = [
    ("BD.CDN.2YR.DQ.YLD", "2Y",   1),
    ("BD.CDN.3YR.DQ.YLD", "3Y",   2),
    ("BD.CDN.5YR.DQ.YLD", "5Y",   3),
    ("BD.CDN.7YR.DQ.YLD", "7Y",   4),
    ("BD.CDN.10YR.DQ.YLD", "10Y", 5),
    ("BD.CDN.LONG.DQ.YLD", "30Y", 6),
    ("BD.CDN.RRB.DQ.YLD", "RRB",  7),  # real-return bond
]


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"boc_yields: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"boc_yields: keeping existing {OUT_CSV.name}")
        return

    obs = d.get("observations") or []
    if not obs:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"boc_yields: no obs, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for o in obs:
        obs_date = o.get("d") or ""
        if not obs_date:
            continue
        for sid, tenor, order in SERIES:
            cell = o.get(sid)
            if not isinstance(cell, dict):
                continue
            val = cell.get("v")
            try:
                y = float(val) if val not in (None, "", "NA") else None
            except (TypeError, ValueError):
                y = None
            if y is None:
                continue
            rows.append({
                "tenor": tenor,
                "yield_pct": f"{y:.4f}",
                "observation_date": obs_date,
                "series_id": sid,
                "sort_order": str(order),
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"boc_yields: empty, keeping existing {OUT_CSV.name}")
        return

    # Sort: recent date first, then tenor order.
    rows.sort(key=lambda r: (r["observation_date"], int(r["sort_order"])),
              reverse=False)
    rows.sort(key=lambda r: r["observation_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["observation_date", "tenor", "yield_pct",
                  "series_id", "sort_order", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Compute 2-10 spread from latest day.
    latest = rows[0]["observation_date"]
    day = {r["tenor"]: float(r["yield_pct"])
           for r in rows if r["observation_date"] == latest}
    two = day.get("2Y")
    ten = day.get("10Y")
    spread_bits = ""
    if two is not None and ten is not None:
        spread = (ten - two) * 100.0
        spread_bits = f" | 2s10s={spread:+.0f}bp"
    print(f"boc_yields: {len(rows)} rows | {latest} "
          f"2Y={day.get('2Y','?')}% 10Y={day.get('10Y','?')}%"
          f"{spread_bits} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
