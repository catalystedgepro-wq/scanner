#!/usr/bin/env python3
"""build_census_resconst.py — Census New Residential Construction.

Monthly permits, starts, units under construction, and completions
from the Census Bureau's residential construction timeseries.
Leading indicator for homebuilders, building-products, and mortgage
finance complex. Published ~18th business day each month.

Categories tracked (seasonally adjusted, US national):
- APERMITS      authorized units (permits)           — leads starts ~1mo
- ASTARTS       housing starts                        — leads completions ~6mo
- UNDERCONST    units under construction (stock)      — labor demand proxy
- ACOMPLETIONS  housing completions                   — supply-hitting-market
- AUTHNOTSTD    authorized but not yet started        — pipeline backlog

Data types: TOTAL, SINGLE (1-unit), MULTI (2+ unit).

Signal for trading:
- Permits MoM down >5%: fade DHI/LEN/PHM/NVR/TOL/KBH/MTH/MDC
  (1–2wk lag). Also softens BLDR/LPX/WY/UFPI lumber+OSB demand.
- Permits MoM up >5%: bid DHI/LEN/PHM/BLDR/BECN; mortgage lenders
  RKT/UWMC bid on refi+purchase volume read-through.
- Multi-family ASTARTS accelerating = AMH/INVH/MAA/CPT/AVB headwind
  (supply pressure on rents 12-18mo forward).
- AUTHNOTSTD building = credit tightness/labor shortage signal;
  softens labor multiples at homebuilders.
- Completions spike with stagnant absorption = inventory buildup
  → downgrade risk on builders with high spec-home ratio.

Source: api.census.gov/data/timeseries/eits/resconst (no key).

Output: census_resconst.csv
Columns: category_code, data_type_code, period, value_thousand,
         mom_pct, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_resconst.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.census.gov/data/timeseries/eits/resconst"

# Leading-indicator first, lagging-indicator last.
CATEGORIES = [
    "APERMITS",
    "AUTHNOTSTD",
    "ASTARTS",
    "UNDERCONST",
    "ACOMPLETIONS",
]
DATA_TYPES = {"TOTAL", "SINGLE", "MULTI"}


def fetch_category(cat: str, from_period: str) -> list[list[str]]:
    params = {
        "get": "cell_value,data_type_code,category_code,geo_level_code",
        "time": f"from+{from_period}",
        "seasonally_adj": "yes",
        "category_code": cat,
        "time_slot_id": "0",
    }
    # time=from+YYYY-MM must not URL-encode the plus; build manually.
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"census_resconst {cat}: {e}")
        return []
    try:
        return json.loads(raw) or []
    except Exception:
        return []


def main() -> None:
    today = dt.date.today()
    # 26 months back gives 24 months for YoY on 24 months of data.
    start = today.replace(day=1)
    for _ in range(26):
        y = start.year if start.month > 1 else start.year - 1
        m = start.month - 1 if start.month > 1 else 12
        start = dt.date(y, m, 1)
    from_period = start.strftime("%Y-%m")

    # key: (cat, dtype, period) -> value (thousands)
    data: dict[tuple[str, str, str], float] = {}

    for cat in CATEGORIES:
        rows = fetch_category(cat, from_period)
        if len(rows) < 2:
            continue
        header = rows[0]
        try:
            i_val = header.index("cell_value")
            i_dtype = header.index("data_type_code")
            i_cat = header.index("category_code")
            i_geo = header.index("geo_level_code")
            i_time = header.index("time")
        except ValueError:
            continue
        for row in rows[1:]:
            try:
                geo = row[i_geo]
                dtype = row[i_dtype]
                if geo != "US" or dtype not in DATA_TYPES:
                    continue
                c = row[i_cat]
                per = row[i_time]
                v = float(row[i_val])
            except Exception:
                continue
            data[(c, dtype, per)] = v

    if not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"census_resconst: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Build rows with MoM and YoY for each (cat, dtype).
    out_rows: list[dict] = []
    # Group by (cat, dtype) → sorted periods
    groups: dict[tuple[str, str], list[str]] = {}
    for (cat, dtype, per) in data.keys():
        groups.setdefault((cat, dtype), []).append(per)
    for periods in groups.values():
        periods.sort()

    def _prior_month(p: str) -> str:
        y, m = map(int, p.split("-"))
        m -= 1
        if m < 1:
            m = 12
            y -= 1
        return f"{y:04d}-{m:02d}"

    def _prior_year(p: str) -> str:
        y, m = map(int, p.split("-"))
        return f"{y - 1:04d}-{m:02d}"

    for (cat, dtype), periods in groups.items():
        for per in periods:
            v = data[(cat, dtype, per)]
            pm = _prior_month(per)
            py = _prior_year(per)
            pv_m = data.get((cat, dtype, pm))
            pv_y = data.get((cat, dtype, py))
            mom = ((v - pv_m) / pv_m * 100
                   if pv_m and abs(pv_m) > 1e-9 else None)
            yoy = ((v - pv_y) / pv_y * 100
                   if pv_y and abs(pv_y) > 1e-9 else None)
            out_rows.append({
                "category_code": cat,
                "data_type_code": dtype,
                "period": per,
                "value_thousand": f"{v:.0f}",
                "mom_pct": f"{mom:.2f}" if mom is not None else "",
                "yoy_pct": f"{yoy:.2f}" if yoy is not None else "",
            })

    if not out_rows:
        return

    out_rows.sort(key=lambda r: (r["category_code"],
                                 r["data_type_code"],
                                 r["period"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in out_rows:
        r["captured_at"] = now

    fieldnames = ["category_code", "data_type_code", "period",
                  "value_thousand", "mom_pct", "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # Summary: latest TOTAL permits + starts.
    latest_permits = [r for r in out_rows
                      if r["category_code"] == "APERMITS"
                      and r["data_type_code"] == "TOTAL"]
    latest_starts = [r for r in out_rows
                     if r["category_code"] == "ASTARTS"
                     and r["data_type_code"] == "TOTAL"]
    pm = latest_permits[-1] if latest_permits else None
    st = latest_starts[-1] if latest_starts else None
    p_s = (f"permits {pm['period']}={pm['value_thousand']}k "
           f"({pm['mom_pct']}% MoM)" if pm else "")
    s_s = (f"starts {st['period']}={st['value_thousand']}k "
           f"({st['mom_pct']}% MoM)" if st else "")
    print(f"census_resconst: {len(out_rows)} rows | {p_s} | {s_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
