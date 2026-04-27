#!/usr/bin/env python3
"""build_census_permits.py — Census residential construction metrics.

Pulls monthly US building permits, housing starts, and completions
from the Census Economic Indicators timeseries (seasonally adjusted,
annualized rate, thousands of units). 18-month rolling window.

Signal for trading:
- Building permits lead starts by 1-2 months → homebuilders
  (DHI, LEN, NVR, PHM, TOL, KBH) rerate 30-60d ahead of prints.
- Single-family weakness + multi-family strength = starter-home
  crunch → AMH, INVH beneficiaries (SFR).
- YoY permit decline >15% = housing-led recession tell (2006,
  2022); historical 6-mo lead on homebuilder re-rating.
- Material / supplier derivatives: LPX, WY, BLDR, BLD, IBP, MAS.
- Months of new home supply >9 = builder margin risk.

Source: api.census.gov/data/timeseries/eits/resconst (no key
required, 500 calls/day unauthenticated limit).

Categories captured:
  APERMITS = authorized permits (leading indicator)
  ASTARTS  = housing starts (coincident)
  ACOMPLETIONS = completions (lagging)
Structure types: SINGLE, MULTI (5+ unit), TOTAL.

Output: census_permits.csv
Columns: month, category, structure, value_sa, yoy_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_permits.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.census.gov/data/timeseries/eits/resconst"

CATEGORIES = ["APERMITS", "ASTARTS", "ACOMPLETIONS"]
STRUCTURES = ["SINGLE", "MULTI", "TOTAL"]


def fetch_series(category: str, structure: str,
                 from_month: str) -> list[tuple[str, float]]:
    qs = urllib.parse.urlencode({
        "get": ("cell_value,data_type_code,category_code,"
                "seasonally_adj,time_slot_id"),
        "for": "us:*",
        "time": f"from {from_month}",
        "category_code": category,
        "seasonally_adj": "yes",
        "time_slot_id": "0",
        "data_type_code": structure,
    })
    url = f"{API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"census_permits {category}/{structure}: {e}")
        return []
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"census_permits parse {category}/{structure}: {e}")
        return []
    if not data or len(data) < 2:
        return []
    header = data[0]
    # Figure out index of cell_value + time.
    try:
        vi = header.index("cell_value")
        # Duplicate 'time' may exist; use first.
        ti = header.index("time")
    except ValueError:
        return []
    out: list[tuple[str, float]] = []
    for row in data[1:]:
        try:
            v = float(row[vi])
        except Exception:
            continue
        t = str(row[ti])
        out.append((t, v))
    return out


def main() -> None:
    today = dt.date.today()
    from_month = f"{today.year - 2}-01"

    rows: list[dict] = []
    for cat in CATEGORIES:
        for struct in STRUCTURES:
            series = fetch_series(cat, struct, from_month)
            by_month = {t: v for t, v in series}
            for t in sorted(by_month.keys(), reverse=True):
                v = by_month[t]
                # YoY: same month prior year.
                y, m = t.split("-")
                prior_t = f"{int(y) - 1}-{m}"
                prior_v = by_month.get(prior_t)
                yoy = (((v - prior_v) / prior_v * 100)
                       if prior_v else None)
                rows.append({
                    "month": t,
                    "category": cat,
                    "structure": struct,
                    "value_sa": f"{v:.0f}",
                    "yoy_pct": (f"{yoy:.2f}"
                                if yoy is not None else ""),
                })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"census_permits: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["month"], r["category"], r["structure"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["month", "category", "structure", "value_sa",
                  "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        # Find latest permits TOTAL for summary.
        perm_total = [r for r in rows
                      if r["category"] == "APERMITS"
                      and r["structure"] == "TOTAL"]
        starts_total = [r for r in rows
                        if r["category"] == "ASTARTS"
                        and r["structure"] == "TOTAL"]
        pt = perm_total[0] if perm_total else None
        st = starts_total[0] if starts_total else None
        msg = f"census_permits: {len(rows)} pts"
        if pt:
            msg += (f" | {pt['month']} permits={pt['value_sa']}K "
                    f"yoy={pt['yoy_pct']}%")
        if st:
            msg += (f" starts={st['value_sa']}K "
                    f"yoy={st['yoy_pct']}%")
        print(f"{msg} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
