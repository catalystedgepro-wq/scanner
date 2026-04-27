#!/usr/bin/env python3
"""build_bls_macro.py — BLS headline macro series bundle.

Bureau of Labor Statistics public API v2 (free, no key, 25 queries/day).
Headline series drive macro regime for equity rotation:
- CES0000000001 — Total nonfarm payrolls (monthly, first Friday).
- LNS14000000 — Unemployment rate (U-3, monthly).
- LNS13327709 — U-6 underemployment rate (monthly, broader labor slack).
- CUUR0000SA0 — CPI-U, All items (monthly, ~mid-month).
- CUUR0000SA0L1E — CPI-U Core (ex-food/energy, monthly).
- WPUFD4 — Producer Price Index final demand (monthly).
- CES0500000003 — Avg hourly earnings, private (monthly).
- PRS85006092 — Productivity nonfarm business (quarterly).

Trade uses:
- Payrolls > +50k vs consensus: risk-on rotation, long SPY, short TLT.
- Unemployment +0.2 MoM: recession signal, rotate to utilities/staples.
- Core CPI > +0.3 MoM: Fed hike repricing, short TLT, long DXY proxy
  (UUP).
- Wage growth accelerating (CES0500000003 > 4% YoY): margin compression
  narrative for small-cap cohorts.
- U-6 rising while U-3 flat: early cycle weakness, under-the-hood sign.

Source: api.bls.gov/publicAPI/v2/timeseries/data (free tier = 25
series/query, 25 queries/day, 10-yr lookback). POST with JSON payload.

Output: bls_macro.csv
Columns: series_id, series_name, period, period_name, year, value,
         yoy_pct, mom_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bls_macro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

SERIES = {
    "CES0000000001": "Nonfarm Payrolls (thousands)",
    "LNS14000000": "Unemployment Rate U-3 (%)",
    "LNS13327709": "Underemployment U-6 (%)",
    "CUUR0000SA0": "CPI-U All Items (index)",
    "CUUR0000SA0L1E": "CPI-U Core (index)",
    "WPUFD4": "PPI Final Demand (index)",
    "CES0500000003": "Avg Hourly Earnings Private ($)",
    "CIU1010000000000A": "Employment Cost Index Civilian (index)",
}


def fetch() -> dict | None:
    end_year = dt.date.today().year
    start_year = end_year - 2
    payload = {
        "seriesid": list(SERIES.keys()),
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"bls_macro: {e}")
        return None


def _parse_float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main() -> None:
    data = fetch() or {}
    if data.get("status") != "REQUEST_SUCCEEDED":
        msg = data.get("message") or "unknown"
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bls_macro: status={data.get('status','?')} msg={msg}; "
                  f"keeping existing {OUT_CSV.name}")
            return
    series = (data.get("Results") or {}).get("series") or []
    rows: list[dict] = []
    for s in series:
        sid = s.get("seriesID", "")
        name = SERIES.get(sid, sid)
        points = s.get("data") or []
        # Points come newest → oldest; sort to guarantee
        points = [p for p in points if p.get("value", "-") != "-"]
        points.sort(key=lambda p: (p.get("year", ""), p.get("period", "")))
        for i, p in enumerate(points):
            val = _parse_float(p.get("value", ""))
            if val is None:
                continue
            # MoM: previous index in same-frequency series
            mom = None
            if i > 0:
                prev = _parse_float(points[i - 1].get("value", ""))
                if prev not in (None, 0.0):
                    mom = (val - prev) / prev * 100.0
            # YoY: ~12 entries back for monthly
            yoy = None
            if i >= 12:
                prior = _parse_float(points[i - 12].get("value", ""))
                if prior not in (None, 0.0):
                    yoy = (val - prior) / prior * 100.0
            rows.append({
                "series_id": sid,
                "series_name": name,
                "period": p.get("period", ""),
                "period_name": p.get("periodName", ""),
                "year": p.get("year", ""),
                "value": f"{val}",
                "yoy_pct": f"{yoy:+.2f}" if yoy is not None else "",
                "mom_pct": f"{mom:+.2f}" if mom is not None else "",
            })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"bls_macro: empty parse, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["series_id", "series_name", "period",
                        "period_name", "year", "value", "yoy_pct",
                        "mom_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    latest_by_series: dict[str, dict] = {}
    for r in rows:
        k = r["series_id"]
        cur = latest_by_series.get(k)
        if not cur or (r["year"], r["period"]) > (cur["year"], cur["period"]):
            latest_by_series[k] = r
    bullet = " | ".join(
        f"{k}={v['value']}({v['yoy_pct']}% YoY)"
        for k, v in list(latest_by_series.items())[:3]
    )
    print(f"bls_macro: {len(rows)} rows / {len(series)} series | "
          f"{bullet} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
