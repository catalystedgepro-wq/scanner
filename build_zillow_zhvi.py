#!/usr/bin/env python3
"""build_zillow_zhvi.py — Zillow Home Value Index, monthly.

Typical home value for middle-tier (33rd–67th percentile)
single-family + condo inventory, smoothed and seasonally adjusted.
Updated monthly by Zillow Research. Complements ZORI (rent) — ZHVI
tracks buyer-side price, not renter-side.

Signal:
- ZHVI YoY > +5% = home-equity wealth effect supports consumer
  discretionary (HD, LOW, RH, WSM, TSCO)
- ZHVI YoY < -2% = negative equity pressure → HOV/TOL/DHI risk,
  mortgage-credit deterioration (RKT, UWMC, COOP)
- Regional divergence (Sunbelt vs NE/Midwest) surfaces migration
  catalysts for localized REITs (UDR, EQR, MAA)

Drives:
- Homebuilders (DHI, LEN, PHM, NVR, TOL, MTH, KBH)
- Home improvement (HD, LOW)
- Mortgage originators (RKT, UWMC, PFSI, COOP)
- Home furnishings (RH, WSM, W, ETH)
- REITs (AVB, EQR, MAA, ESS, AMH, INVH)
- Real-estate brokers (Z, COMP, RDFN, EXPI)

Source: files.zillowstatic.com/research/public_csvs/zhvi/
        Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv
Output: zillow_zhvi.csv
Columns: region, region_type, period, zhvi_usd, mom_pct, yoy_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from io import StringIO
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "zillow_zhvi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://files.zillowstatic.com/research/public_csvs/zhvi/"
       "Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv")

# Top-20 MSAs + national aggregate.
FOCUS = {
    "United States", "New York, NY", "Los Angeles, CA",
    "Chicago, IL", "Dallas, TX", "Houston, TX",
    "Washington, DC", "Philadelphia, PA", "Miami, FL",
    "Atlanta, GA", "Boston, MA", "Phoenix, AZ",
    "San Francisco, CA", "Riverside, CA", "Detroit, MI",
    "Seattle, WA", "Minneapolis, MN", "San Diego, CA",
    "Tampa, FL", "Denver, CO", "Austin, TX",
}

MONTHS_OUT = 24


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"zillow_zhvi: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"zillow_zhvi: keeping existing {OUT_CSV.name}")
        return

    reader = csv.reader(StringIO(text))
    header = next(reader, None)
    if not header:
        return
    # Column indices for metadata.
    try:
        name_idx = header.index("RegionName")
        type_idx = header.index("RegionType")
    except ValueError:
        return
    # Date columns start after StateName column.
    try:
        state_idx = header.index("StateName")
    except ValueError:
        state_idx = type_idx + 1

    date_cols = [(i, header[i]) for i in range(state_idx + 1, len(header))]
    recent_cols = date_cols[-MONTHS_OUT:]

    rows: list[dict] = []

    for row in reader:
        if len(row) < len(header):
            continue
        name = row[name_idx]
        rtype = row[type_idx]
        if name not in FOCUS:
            continue

        series: list[tuple[str, float]] = []
        for i, col_name in date_cols:
            raw = row[i].strip() if i < len(row) else ""
            if not raw:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            series.append((col_name[:7], v))  # YYYY-MM

        if not series:
            continue

        last_idx = {p: v for p, v in series}
        keep = series[-MONTHS_OUT:]
        for period, val in keep:
            # MoM: prior month in series
            pos = [i for i, (p, _) in enumerate(series) if p == period]
            if not pos:
                continue
            idx = pos[0]
            prev_v = series[idx - 1][1] if idx >= 1 else None
            yoy_v = series[idx - 12][1] if idx >= 12 else None
            mom_pct = ""
            yoy_pct = ""
            if prev_v and prev_v > 0:
                mom_pct = f"{((val / prev_v) - 1) * 100:+.2f}"
            if yoy_v and yoy_v > 0:
                yoy_pct = f"{((val / yoy_v) - 1) * 100:+.2f}"
            rows.append({
                "region": name[:40],
                "region_type": rtype,
                "period": period,
                "zhvi_usd": f"{val:.2f}",
                "mom_pct": mom_pct,
                "yoy_pct": yoy_pct,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"zillow_zhvi: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["region", "region_type", "period", "zhvi_usd",
                  "mom_pct", "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    usa = [r for r in rows if r["region"] == "United States"]
    usa.sort(key=lambda r: r["period"], reverse=True)
    latest_us = usa[0] if usa else None
    ny = [r for r in rows if r["region"].startswith("New York")]
    ny.sort(key=lambda r: r["period"], reverse=True)
    latest_ny = ny[0] if ny else None
    austin = [r for r in rows if r["region"].startswith("Austin")]
    austin.sort(key=lambda r: r["period"], reverse=True)
    latest_austin = austin[0] if austin else None
    bits = []
    if latest_us:
        bits.append(f"US {latest_us['period']}=${float(latest_us['zhvi_usd'])/1000:.0f}k "
                    f"({latest_us['yoy_pct']}%YoY)")
    if latest_ny:
        bits.append(f"NY={latest_ny['yoy_pct']}%YoY")
    if latest_austin:
        bits.append(f"Austin={latest_austin['yoy_pct']}%YoY")
    print(f"zillow_zhvi: {len(rows)} rows | {len(FOCUS)} metros | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
