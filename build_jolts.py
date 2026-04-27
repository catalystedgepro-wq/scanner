#!/usr/bin/env python3
"""build_jolts.py — BLS JOLTS job openings + hires/quits/layoffs (monthly).

JOLTS openings/quits ratio is Fed's favorite labor-slack gauge. High
quits = wage-pressure (inflation, margin risk). Falling openings = slack
(disinflation, Fed pivot closer). Layoffs spike = cyclical top.

Trade uses:
- Quits rate drop 3 months in a row -> bond rally setup (TLT), tech
  growth lift (QQQ beats XLF on duration sensitivity).
- Openings fall > -300k m/m -> recession odds jump, gold + staples bid.
- Openings-to-unemployed ratio > 1.5 = tight (wage inflation persists),
  < 1.0 = slack (Fed pivot window).
- Layoffs & discharges spike -> KRE/XLF stress, staffing (MAN/RHI) fade.

Source: api.bls.gov/publicAPI/v2/timeseries/data/ (public, no key needed
for low-volume single-series fetches). Previously used FRED fredgraph.csv
which is intermittently unreachable; BLS API is primary now.

Output: jolts.csv
Columns: month, job_openings_k, hires_k, quits_k, layoffs_k,
         total_separations_k, openings_per_unemployed, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "jolts.csv"
API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# JOLTS: total nonfarm, seasonally adjusted, level (thousands).
SERIES_LEVELS = {
    "job_openings_k":      "JTS000000000000000JOL",
    "hires_k":             "JTS000000000000000HIL",
    "quits_k":             "JTS000000000000000QUL",
    "layoffs_k":           "JTS000000000000000LDL",
    "total_separations_k": "JTS000000000000000TSL",
}
# Unemployment level (thousands), seasonally adjusted — from CPS.
UNEMP_SERIES = "LNS13000000"

MONTH_NUM = {f"M{n:02d}": n for n in range(1, 13)}


def bls_fetch(series_ids: list[str], start: int, end: int) -> dict:
    body = json.dumps({
        "seriesid": series_ids,
        "startyear": str(start),
        "endyear": str(end),
    }).encode("utf-8")
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"jolts: {e}")
        return {}


def normalize(payload: dict) -> dict[str, dict[str, float]]:
    """sid -> {YYYY-MM: value}."""
    out: dict[str, dict[str, float]] = {}
    for s in (payload.get("Results") or {}).get("series", []) or []:
        sid = s.get("seriesID", "")
        obs: dict[str, float] = {}
        for o in s.get("data", []):
            year = o.get("year", "")
            period = o.get("period", "")
            if period not in MONTH_NUM:
                continue
            key = f"{year}-{MONTH_NUM[period]:02d}"
            try:
                obs[key] = float(o.get("value", "") or "nan")
            except ValueError:
                continue
        out[sid] = obs
    return out


def main() -> None:
    this_year = dt.date.today().year
    payload = bls_fetch(
        list(SERIES_LEVELS.values()) + [UNEMP_SERIES],
        start=this_year - 2,
        end=this_year,
    )
    by_series = normalize(payload)
    if not any(by_series.values()):
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 120:
            print(f"jolts: fetch empty, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
            return
    openings_map = by_series.get(SERIES_LEVELS["job_openings_k"], {})
    months = sorted(openings_map.keys())[-24:]  # last 2 years
    unemp = by_series.get(UNEMP_SERIES, {})
    rows: list[dict] = []
    for ym in months:
        row: dict = {"month": ym}
        for label, sid in SERIES_LEVELS.items():
            val = by_series.get(sid, {}).get(ym)
            row[label] = f"{val:.0f}" if val is not None else ""
        op = openings_map.get(ym)
        un = unemp.get(ym)
        row["openings_per_unemployed"] = (
            f"{op / un:.2f}" if op and un and un > 0 else ""
        )
        rows.append(row)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "job_openings_k", "hires_k", "quits_k",
                        "layoffs_k", "total_separations_k",
                        "openings_per_unemployed", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"jolts: {len(rows)} months | latest {latest.get('month','?')} "
          f"openings={latest.get('job_openings_k','?')}k "
          f"quits={latest.get('quits_k','?')}k "
          f"ratio={latest.get('openings_per_unemployed','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
