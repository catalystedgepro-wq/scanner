#!/usr/bin/env python3
"""build_bls_jolts.py — BLS Job Openings and Labor Turnover Survey.

Monthly US labor market flows — openings, hires, quits, layoffs —
across total nonfarm and key supersectors. JOLTS is a 45-day
lagging release but it's a direct read on hiring appetite + worker
confidence, which leads wage-growth + corporate-guidance cycles.

Signal for trading:
- Openings drop + quits drop = labor softening, Fed dovish tilt
  → rates down, duration bid (TLT, long-bond sovereigns).
- Quits rate elevated (>2.8%) = worker confidence high, wage
  pressure intact → staffing firms (RHI, MAN), wage-exposed
  retail (WMT, COST) margin risk.
- Hires dropping while openings steady = inability to fill
  roles → structural skills gap signal, tech/healthcare benefit.
- Layoffs surge (>1.5%) = recession tell (2008 hit 1.8%, 2020
  hit 7%).
- Sector divergence: manufacturing layoffs + retail hires =
  economy rotating away from goods to services.
- Quits-to-layoffs ratio >2.5 = tight labor; <1.5 = weakening.

Source: api.bls.gov/publicAPI/v2/timeseries (no key needed for
single-series, 25 queries/day).

Series IDs captured:
  JTS000000000000000JOL  — Total nonfarm job openings
  JTS000000000000000HIL  — Total nonfarm hires
  JTS000000000000000QUL  — Total nonfarm quits
  JTS000000000000000LDL  — Total nonfarm layoffs+discharges
  JTS000000000000000TSL  — Total nonfarm total separations

Output: bls_jolts.csv
Columns: month, metric, value_k, mom_delta_k, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bls_jolts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

SERIES = {
    "openings": "JTS000000000000000JOL",
    "hires": "JTS000000000000000HIL",
    "quits": "JTS000000000000000QUL",
    "layoffs": "JTS000000000000000LDL",
    "separations": "JTS000000000000000TSL",
}


def fetch(series_id: str) -> list[tuple[str, float]]:
    """Return list of (YYYY-MM, value) sorted desc by time."""
    url = f"{API}{series_id}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"jolts {series_id}: {e}")
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    results = data.get("Results", {}).get("series", [])
    if not results:
        return []
    items = results[0].get("data", []) or []
    out: list[tuple[str, float]] = []
    for it in items:
        try:
            y = int(it["year"])
            p = it["period"]
            if not p.startswith("M"):
                continue
            m = int(p[1:])
            if m < 1 or m > 12:
                continue
            v = float(it["value"])
        except Exception:
            continue
        out.append((f"{y:04d}-{m:02d}", v))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    latest: dict[str, tuple[str, float]] = {}
    for metric, sid in SERIES.items():
        series = fetch(sid)
        if not series:
            continue
        by_month = {m: v for m, v in series}
        for m, v in series:
            # MoM = value - prior month
            prev_y, prev_mo = map(int, m.split("-"))
            d = dt.date(prev_y, prev_mo, 15)
            d = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=15)
            prev_key = f"{d.year:04d}-{d.month:02d}"
            prev_v = by_month.get(prev_key)
            # YoY
            yoy_key = f"{prev_y - 1:04d}-{prev_mo:02d}"
            yoy_v = by_month.get(yoy_key)
            mom = (v - prev_v) if prev_v is not None else None
            yoy = (((v - yoy_v) / yoy_v * 100)
                   if yoy_v and yoy_v > 0 else None)
            rows.append({
                "month": m,
                "metric": metric,
                "value_k": f"{v:.0f}",
                "mom_delta_k": (f"{mom:+.0f}"
                                if mom is not None else ""),
                "yoy_pct": (f"{yoy:.2f}"
                            if yoy is not None else ""),
            })
        if series:
            latest[metric] = series[0]

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bls_jolts: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["month"], r["metric"]), reverse=True)
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["month", "metric", "value_k", "mom_delta_k",
                  "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest month + quits-to-layoffs ratio.
    q = latest.get("quits")
    l = latest.get("layoffs")
    o = latest.get("openings")
    ratio = None
    if q and l and l[1] > 0:
        ratio = q[1] / l[1]
    parts = []
    if o:
        parts.append(f"openings={o[1]:.0f}K")
    if q:
        parts.append(f"quits={q[1]:.0f}K")
    if l:
        parts.append(f"layoffs={l[1]:.0f}K")
    if ratio is not None:
        parts.append(f"Q/L={ratio:.2f}")
    latest_month = (o or q or l or ("", 0))[0]
    print(f"bls_jolts: {len(rows)} pts | {latest_month} | "
          f"{' '.join(parts)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
