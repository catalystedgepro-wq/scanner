#!/usr/bin/env python3
"""build_zillow_rent.py — Zillow observed rent index (ZORI), weekly.

Rent CPI = 42% of core PCE shelter component. Rising rents = sticky
CPI, hawkish Fed, growth stock compression. Falling rents = dovish,
multifamily REITs squeezed (MAA, CPT, EQR, AVB, ESS). Zillow public
ZORI CSV released monthly, 1-2 months ahead of BLS CPI shelter.

Source: files.zillowstatic.com/research/public_csvs/zori/*.csv
Output: zillow_rent.csv
Columns: month, zori_usd, zori_mom, zori_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "zillow_rent.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

ZORI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "Metro_zori_uc_sfrcondomfr_sm_month.csv"
)


def fetch() -> list[tuple[str, float]]:
    req = urllib.request.Request(ZORI_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"zillow: {e}")
        return []
    lines = txt.splitlines()
    if not lines:
        return []
    header = lines[0].split(",")
    # Find United States row and extract time series columns (dates)
    us_row = None
    for ln in lines[1:]:
        if ',"United States",' in ln or ln.split(",")[2:3] == ['"United States"']:
            us_row = ln
            break
        parts = ln.split(",")
        if len(parts) > 2 and parts[2].strip('"') == "United States":
            us_row = ln
            break
    if not us_row:
        return []
    parts = us_row.split(",")
    if len(parts) != len(header):
        # simple comma split may fail on quoted fields; try naive
        pass
    out = []
    for i, col in enumerate(header):
        c = col.strip().strip('"')
        if len(c) >= 7 and c[4] == "-":
            try:
                v = float(parts[i].strip().strip('"'))
                out.append((c[:7] + "-01", v))
            except Exception:
                continue
    return out[-48:]


def main() -> None:
    data = dict(fetch())
    sorted_dates = sorted(data.keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(data.keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data.get(d, 0)
        i = idx.get(d, -1)
        prev = data.get(sorted_dates[i - 1], 0) if i >= 1 else 0
        yoy = data.get(sorted_dates[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "zori_usd": f"{cur:.2f}",
            "zori_mom": f"{((cur / prev - 1) * 100):.2f}" if prev else "",
            "zori_yoy_pct": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "zori_usd", "zori_mom", "zori_yoy_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"zillow: {len(rows)} months | latest {latest.get('month','?')} "
          f"rent=${latest.get('zori_usd','?')} yoy={latest.get('zori_yoy_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
