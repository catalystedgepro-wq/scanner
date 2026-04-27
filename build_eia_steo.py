#!/usr/bin/env python3
"""build_eia_steo.py — EIA Short-Term Energy Outlook monthly.

EIA's official 2-year forecast for oil production, demand, price,
natural gas, coal, electricity. Published monthly ~2nd Tuesday.
Key series tracked here are the consensus-beating leading
indicators that move energy equities on release.

Series tracked:
- WTIPUUS  WTI crude spot price ($/bbl)
- BREPUUS  Brent crude spot price ($/bbl)
- NGHHMCF  Henry Hub spot price ($/MMBtu)
- PAPR_WORLD  world petroleum production (mbd)
- PATC_WORLD  world petroleum consumption (mbd)
- PAPR_NONOPEC  non-OPEC production (mbd)
- COPRPUS   US crude production (mbd)
- PATC_US   US petroleum consumption (mbd)
- STEO.PASC_OECD_T3  OECD commercial stocks (mm bbl)
- RGCRUSTUS refinery crude inputs (mbd)
- ELCKWHUS  total electricity generation (GWh)

Signal for trading:
- OECD stock build >20mm bbl m/m beat consensus = oil bearish,
  short XOM/CVX/EOG/DVN next session.
- Non-OPEC supply revision higher = OPEC intervention pressure
  (short XLE, long UAL/DAL as jet fuel relief).
- Refinery utilization forecast rising = crack-spread expansion
  (long VLO/MPC/PSX).
- Henry Hub forecast revision higher = LNG exporter tailwind
  (long LNG/CQP/TELL).

Source: api.eia.gov/v2/steo/data (DEMO_KEY works or set EIA_API_KEY).

Output: eia_steo.csv
Columns: series_id, description, period, value, unit,
         pct_vs_12mo_prior, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eia_steo.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API_KEY = os.environ.get("EIA_API_KEY", "DEMO_KEY")

# 24-month rolling window (past 12 + future 12 forecast).
SERIES = [
    "WTIPUUS",  # WTI
    "BREPUUS",  # Brent
    "NGHHMCF",  # Henry Hub gas
    "PAPR_WORLD",
    "PATC_WORLD",
    "PAPR_NONOPEC",
    "COPRPUS",
    "PATC_US",
    "RGCRUSTUS",
]


def fetch_series(sid: str) -> list[dict]:
    params = {
        "api_key": API_KEY,
        "frequency": "monthly",
        "data[0]": "value",
        "facets[seriesId][]": sid,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "30",
    }
    qs = urllib.parse.urlencode(params)
    url = f"https://api.eia.gov/v2/steo/data/?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"eia_steo {sid}: {e}")
        return []
    try:
        d = json.loads(raw)
    except Exception:
        return []
    return d.get("response", {}).get("data", []) or []


def _to_float(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


def main() -> None:
    rows: list[dict] = []
    today = dt.date.today()
    cutoff = today + dt.timedelta(days=120)  # keep ~4mo forward
    earliest = (today - dt.timedelta(days=400)).isoformat()[:7]

    for sid in SERIES:
        series_pts = fetch_series(sid)
        if not series_pts:
            continue
        # Build period → value map for YoY.
        by_period: dict[str, float] = {}
        for p in series_pts:
            v = _to_float(p.get("value"))
            per = p.get("period") or ""
            if v is not None and per:
                by_period[per] = v

        for p in series_pts:
            per = p.get("period") or ""
            if not per or per < earliest:
                continue
            # Drop forecast tail > 4 months out.
            try:
                y, m = map(int, per.split("-"))
                if dt.date(y, m, 15) > cutoff:
                    continue
            except Exception:
                pass
            v = _to_float(p.get("value"))
            if v is None:
                continue
            # YoY comparison.
            try:
                y, m = map(int, per.split("-"))
                prior_k = f"{y - 1:04d}-{m:02d}"
            except Exception:
                prior_k = ""
            pv = by_period.get(prior_k)
            yoy = None
            if pv and abs(pv) > 1e-9:
                yoy = (v - pv) / abs(pv) * 100
            rows.append({
                "series_id": sid,
                "description": (p.get("seriesDescription") or "")[:80],
                "period": per,
                "value": f"{v:.4f}",
                "unit": (p.get("unit") or "")[:40],
                "pct_vs_12mo_prior": (f"{yoy:.2f}"
                                      if yoy is not None else ""),
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"eia_steo: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["series_id"], r["period"]),
              reverse=False)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["series_id", "description", "period", "value",
                  "unit", "pct_vs_12mo_prior", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Latest WTI line for summary.
    wti = [r for r in rows if r["series_id"] == "WTIPUUS"]
    latest_per = wti[-1]["period"] if wti else ""
    latest_val = wti[-1]["value"] if wti else "?"
    print(f"eia_steo: {len(rows)} pts | WTI {latest_per}=${latest_val}/bbl "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
