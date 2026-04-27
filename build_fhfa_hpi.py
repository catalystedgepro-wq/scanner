#!/usr/bin/env python3
"""build_fhfa_hpi.py — FHFA House Price Index monthly bundle.

Monthly FHFA HPI (purchase-only, traditional) for 9 Census
Divisions + USA. Housing momentum is the dominant lead indicator
for:
- Homebuilder equity (LEN, DHI, NVR, PHM, TOL, TMHC, MTH, KBH)
- Building products (HD, LOW, FND, BLDR, EXP, IBP)
- Mortgage finance (RKT, UWMC, COOP, PFSI, RDN, MTG)
- REITs (AMH, INVH, SUI, ELS — single-family rental)
- Insurance (ALL, PGR, TRV, AIG — property lines)

Signal: 12-month HPI delta vs trailing 3-year average separates
durable expansion from spike-and-fade patterns.

Source: www.fhfa.gov/hpi/download/monthly/hpi_master.csv.

Output: fhfa_hpi.csv
Columns: place_name, place_id, yr, period, index_nsa, index_sa,
         yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fhfa_hpi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv"

WANTED_FLAVOR = "purchase-only"
WANTED_TYPE = "traditional"
WANTED_LEVELS = {"USA or Census Division", "USA"}


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"fhfa_hpi: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fhfa_hpi: keeping existing {OUT_CSV.name}")
        return

    reader = csv.DictReader(io.StringIO(body))
    latest_by_place: dict[str, list[dict]] = {}
    for row in reader:
        if (row.get("hpi_flavor") != WANTED_FLAVOR or
                row.get("hpi_type") != WANTED_TYPE or
                row.get("frequency") != "monthly"):
            continue
        if row.get("level") not in WANTED_LEVELS:
            continue
        place = row.get("place_id", "") or row.get("place_name", "")
        latest_by_place.setdefault(place, []).append(row)

    if not latest_by_place:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fhfa_hpi: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    out_rows: list[dict] = []
    for place, recs in latest_by_place.items():
        recs.sort(key=lambda r: (int(r.get("yr") or 0),
                                 int(r.get("period") or 0)))
        if not recs:
            continue
        last = recs[-1]
        try:
            idx_now = float(last.get("index_sa") or 0)
        except (TypeError, ValueError):
            continue
        yoy_pct = ""
        if len(recs) >= 13:
            try:
                idx_yoy = float(recs[-13].get("index_sa") or 0)
                if idx_yoy:
                    yoy_pct = f"{(idx_now / idx_yoy - 1) * 100:+.2f}"
            except (TypeError, ValueError):
                yoy_pct = ""
        out_rows.append({
            "place_name": str(last.get("place_name") or "")[:48],
            "place_id": str(last.get("place_id") or "")[:12],
            "yr": str(last.get("yr") or "")[:4],
            "period": str(last.get("period") or "")[:2],
            "index_nsa": str(last.get("index_nsa") or "")[:8],
            "index_sa": str(last.get("index_sa") or "")[:8],
            "yoy_pct": yoy_pct,
            "captured_at": now,
        })

    out_rows.sort(key=lambda r: (r["place_id"] or "zz"))

    fieldnames = ["place_name", "place_id", "yr", "period", "index_nsa",
                  "index_sa", "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    usa_row = next((r for r in out_rows if r["place_name"].startswith("United")),
                   out_rows[0] if out_rows else {})
    print(f"fhfa_hpi: {len(out_rows)} places | USA HPI="
          f"{usa_row.get('index_sa', '?')} YoY "
          f"{usa_row.get('yoy_pct', '?')}% @ {usa_row.get('yr', '?')}-"
          f"{usa_row.get('period', '?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
