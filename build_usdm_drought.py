#!/usr/bin/env python3
"""build_usdm_drought.py — US Drought Monitor weekly CONUS + states.

Weekly drought-severity coverage percentages from the USDM
(University of Nebraska-Lincoln). Updated every Thursday.

Categories (area-percent):
- None  no drought
- D0    abnormally dry
- D1    moderate drought
- D2    severe drought
- D3    extreme drought
- D4    exceptional drought

Signal for trading:
- CONUS D2+ area >30% sustained 4+ weeks = grain/livestock stress
  → long fertilizer (CF, MOS, NTR, CTVA), long irrigation (LNN, VMI),
  watch DE for short-term demand softness.
- Midwest (IL, IA, IN, OH, MO, MN, WI) D3+ coverage rising = corn/
  soybean yield-loss tail → bid CORN, SOYB, WEAT ETFs; ADM/BG
  margins compress (grain handlers lose volume).
- California D3+ coverage rising = TSN/HRL feed costs + almond
  almond/tree nut supply stress → fade TSN/HRL; LAMR/OUT (billboards
  near farm freight corridors) softens.
- Plains wheat-belt (KS, NE, OK) D2+ up = WEAT bid; global wheat
  export-pricing for ADM.

Source: usdmdataservices.unl.edu/api (no key).
  GetDroughtSeverityStatisticsByAreaPercent (CSV response).

Output: usdm_drought.csv
Columns: area, map_date, none_pct, d0_pct, d1_pct, d2_pct, d3_pct,
         d4_pct, d2plus_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usdm_drought.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://usdmdataservices.unl.edu/api"

# AOIs that matter for equities. conus = national; states are for
# ag/water-stress drill-down.
AOIS_NATIONAL = ["conus"]
# State endpoint wants 2-digit FIPS code, not abbreviation.
STATE_FIPS = {
    "IA": "19", "IL": "17", "IN": "18", "OH": "39", "MO": "29",
    "MN": "27", "WI": "55",                          # corn belt
    "KS": "20", "NE": "31", "OK": "40", "TX": "48",  # wheat belt
    "CA": "06",                                      # California
    "AZ": "04", "NV": "32", "UT": "49", "CO": "08", "NM": "35",
    "FL": "12", "GA": "13", "AL": "01",              # southeast
}


def _fetch(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"usdm fetch: {e}")
        return []
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    return [ln.split(",") for ln in lines]


def fetch_aoi(aoi: str, start: dt.date, end: dt.date,
              statistics_type: int) -> list[dict]:
    sd = start.strftime("%-m/%-d/%Y")
    ed = end.strftime("%-m/%-d/%Y")
    # National endpoint is USStatistics, state endpoint StateStatistics.
    if aoi.lower() == "conus":
        ep = "USStatistics"
        aoi_p = "conus"
        area_col = "AreaOfInterest"
    else:
        ep = "StateStatistics"
        # State endpoint takes FIPS code, not abbreviation.
        aoi_p = STATE_FIPS.get(aoi.upper(), aoi.upper())
        area_col = "StateAbbreviation"
    url = (f"{BASE}/{ep}/GetDroughtSeverityStatisticsByAreaPercent"
           f"?aoi={aoi_p}&startdate={sd}&enddate={ed}"
           f"&statisticsType={statistics_type}")
    rows = _fetch(url)
    if len(rows) < 2:
        return []
    hdr = rows[0]
    try:
        idx = {k: hdr.index(k) for k in
               ("MapDate", area_col, "None", "D0", "D1",
                "D2", "D3", "D4")}
    except ValueError:
        return []
    out: list[dict] = []
    for r in rows[1:]:
        if len(r) <= max(idx.values()):
            continue
        try:
            md_raw = r[idx["MapDate"]]
            md = f"{md_raw[0:4]}-{md_raw[4:6]}-{md_raw[6:8]}"
            area = r[idx[area_col]]
            d0 = float(r[idx["D0"]])
            d1 = float(r[idx["D1"]])
            d2 = float(r[idx["D2"]])
            d3 = float(r[idx["D3"]])
            d4 = float(r[idx["D4"]])
            none_pct = float(r[idx["None"]])
        except Exception:
            continue
        out.append({
            "area": area,
            "map_date": md,
            "none_pct": f"{none_pct:.2f}",
            "d0_pct": f"{d0:.2f}",
            "d1_pct": f"{d1:.2f}",
            "d2_pct": f"{d2:.2f}",
            "d3_pct": f"{d3:.2f}",
            "d4_pct": f"{d4:.2f}",
            "d2plus_pct": f"{d2:.2f}",  # overwritten below
        })
    # D2+ is D2 already (cumulative in this API: D2 column is D2 OR
    # worse). USDM "area in D2 or worse" is reported directly.
    return out


def main() -> None:
    today = dt.date.today()
    # 10 weeks back gives 2mo of history + latest.
    start = today - dt.timedelta(weeks=10)

    rows: list[dict] = []
    for aoi in AOIS_NATIONAL:
        rows.extend(fetch_aoi(aoi, start, today, statistics_type=1))
    for aoi in STATE_FIPS.keys():
        rows.extend(fetch_aoi(aoi, start, today, statistics_type=1))

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"usdm_drought: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Sort: most recent first, then largest D2+ coverage.
    rows.sort(key=lambda r: (r["map_date"],
                             -float(r["d2plus_pct"])),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["area", "map_date", "none_pct", "d0_pct", "d1_pct",
                  "d2_pct", "d3_pct", "d4_pct", "d2plus_pct",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest CONUS row + top-3 states by D2+.
    conus = [r for r in rows if r["area"] == "CONUS"]
    conus_latest = conus[0] if conus else None
    latest_date = conus_latest["map_date"] if conus_latest else ""
    top_states = sorted(
        [r for r in rows if r["map_date"] == latest_date
         and r["area"] != "CONUS"],
        key=lambda r: -float(r["d2plus_pct"]),
    )[:3]
    c_s = (f"CONUS {latest_date} D2+={conus_latest['d2plus_pct']}%"
           if conus_latest else "")
    ts_s = " ".join(f"{s['area']}={s['d2plus_pct']}%"
                    for s in top_states)
    print(f"usdm_drought: {len(rows)} rows | {c_s} | top {ts_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
