#!/usr/bin/env python3
"""build_census_vacancies.py — Census Housing Vacancy Survey (HVS).

Quarterly homeowner + rental vacancy rates from the Census Bureau
Housing Vacancy Survey. Direct pricing-power signal for residential
REITs and homebuilders.

Series tracked (US national):
- RVR    rental vacancy rate (%)           — rent pricing power
- HVR    homeowner vacancy rate (%)        — spec-home supply risk
- SAHOR  homeownership rate sa (%)         — first-time buyer demand
- HOR    homeownership rate nsa (%)        — first-time buyer demand

Signal for trading:
- RVR falling = landlord pricing power strengthens → bid residential
  REITs (AMH/INVH/MAA/AVB/CPT/EQR/ESS/UDR/IRT/CSR).
- RVR rising = rent softness → fade the same complex, downside on
  NOI reset narratives.
- HVR rising sharply = spec-home supply overhang → fade KBH, MTH,
  MDC, TOL (the spec-heavy builders).
- SAHOR rising = first-time buyer cohort strengthening → bid DHI
  (entry-level leader), LEN (first-time-focused brands), Rocket RKT,
  UWM UWMC on purchase-volume read.

Source: api.census.gov/data/timeseries/eits/hv (no key).

Output: census_vacancies.csv
Columns: data_type_code, period, value_pct, delta_qoq, delta_yoy,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_vacancies.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.census.gov/data/timeseries/eits/hv"

# data_type_code → human label.
SERIES_SA = {"SAHOR", "SARVR", "SAHVR"}
SERIES_NSA = {"HOR", "RVR", "HVR"}


def fetch(seasonally_adj: str, from_period: str) -> list[list[str]]:
    params = (
        f"get=cell_value,data_type_code,category_code,geo_level_code"
        f"&time=from+{from_period}"
        f"&seasonally_adj={seasonally_adj}"
        f"&time_slot_id=0"
    )
    url = f"{BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"census_vacancies {seasonally_adj}: {e}")
        return []
    try:
        return json.loads(raw) or []
    except Exception:
        return []


def _q_prev(p: str) -> str:
    # p = "YYYY-Qn"
    y, q = p.split("-Q")
    y = int(y)
    q = int(q)
    q -= 1
    if q < 1:
        q = 4
        y -= 1
    return f"{y}-Q{q}"


def _q_yr(p: str) -> str:
    y, q = p.split("-Q")
    return f"{int(y) - 1}-Q{q}"


def main() -> None:
    today = dt.date.today()
    # 12 quarters back ≈ 3 yr history gives 2 yr of YoY comparisons.
    start_y = today.year - 3
    from_period = f"{start_y}-Q1"

    # data[(dtype, period)] = value
    data: dict[tuple[str, str], float] = {}

    for sa_flag in ("yes", "no"):
        rows = fetch(sa_flag, from_period)
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
        want = SERIES_SA if sa_flag == "yes" else SERIES_NSA
        for row in rows[1:]:
            try:
                if row[i_geo] != "US":
                    continue
                dtype = row[i_dtype]
                cat = row[i_cat]
                if dtype not in want:
                    continue
                if cat != "RATE":
                    continue
                per = row[i_time]
                v = float(row[i_val])
            except Exception:
                continue
            data[(dtype, per)] = v

    if not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"census_vacancies: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    groups: dict[str, list[str]] = {}
    for (dtype, per) in data.keys():
        groups.setdefault(dtype, []).append(per)
    for lst in groups.values():
        lst.sort()

    out_rows: list[dict] = []
    for dtype, periods in groups.items():
        for per in periods:
            v = data[(dtype, per)]
            pv_q = data.get((dtype, _q_prev(per)))
            pv_y = data.get((dtype, _q_yr(per)))
            dq = (v - pv_q) if pv_q is not None else None
            dy = (v - pv_y) if pv_y is not None else None
            out_rows.append({
                "data_type_code": dtype,
                "period": per,
                "value_pct": f"{v:.2f}",
                "delta_qoq": f"{dq:+.2f}" if dq is not None else "",
                "delta_yoy": f"{dy:+.2f}" if dy is not None else "",
            })

    out_rows.sort(key=lambda r: (r["data_type_code"], r["period"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in out_rows:
        r["captured_at"] = now

    fieldnames = ["data_type_code", "period", "value_pct",
                  "delta_qoq", "delta_yoy", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # Summary: latest RVR, HVR, SAHOR.
    def _latest(code: str) -> str:
        xs = [r for r in out_rows if r["data_type_code"] == code]
        if not xs:
            return ""
        last = xs[-1]
        return (f"{code} {last['period']}={last['value_pct']}% "
                f"({last['delta_yoy']}pt YoY)")

    rvr_s = _latest("RVR")
    hvr_s = _latest("HVR")
    hor_s = _latest("SAHOR") or _latest("HOR")
    print(f"census_vacancies: {len(out_rows)} rows | {rvr_s} | "
          f"{hvr_s} | {hor_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
