#!/usr/bin/env python3
"""build_worldbank_cpi.py — World Bank global CPI inflation.

Annual CPI inflation rate (FP.CPI.TOTL.ZG) across 200+ economies.
Complements US CPI (FRED/BLS) with cross-country inflation backdrop
for:
- EM equity exposure (EEM, VWO, EMXC, BABA, BHP, VALE, PBR, ITUB)
- Hyperinflation watch list (Argentina/Venezuela/Turkey/Lebanon)
- Commodity producer countries (Russia/Saudi/Chile/Australia)
- DM central bank divergence (BoE/ECB/BoJ vs Fed policy paths)
- Currency crisis triggers (EM sov-debt spreads)

Signal: countries >20% CPI = macro crisis zones; >10% = tight cycle;
sub-2% = deflationary risk. Year-over-year delta captures direction.

Source: api.worldbank.org/v2 (free, no key).
Output: worldbank_cpi.csv
Columns: iso3, country, year, cpi_pct, yoy_delta, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "worldbank_cpi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.worldbank.org/v2/country/all/indicator/"
       "FP.CPI.TOTL.ZG?format=json&date=2022:2024&per_page=2000")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"worldbank_cpi: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_cpi: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(payload, list) or len(payload) < 2:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_cpi: empty, keeping existing {OUT_CSV.name}")
        return

    data = payload[1] or []
    by_country: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}

    for item in data:
        if not isinstance(item, dict):
            continue
        iso3 = (item.get("countryiso3code") or "").strip()
        if not iso3 or len(iso3) != 3:
            continue
        year = str(item.get("date") or "")[:4]
        val = item.get("value")
        if val is None:
            continue
        try:
            fv = float(val)
        except (TypeError, ValueError):
            continue
        names[iso3] = ((item.get("country") or {}).get("value")
                       or iso3)[:40]
        by_country.setdefault(iso3, {})[year] = fv

    if not by_country:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_cpi: parsed 0, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for iso3, years in by_country.items():
        latest_year = max(years.keys())
        latest = years[latest_year]
        prev = str(int(latest_year) - 1)
        delta = ""
        if prev in years:
            delta = f"{latest - years[prev]:+.2f}"
        rows.append({
            "iso3": iso3,
            "country": names.get(iso3, iso3),
            "year": latest_year,
            "cpi_pct": f"{latest:.2f}",
            "yoy_delta": delta,
        })

    rows.sort(key=lambda r: r["country"])

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["iso3", "country", "year", "cpi_pct", "yoy_delta",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    vals = [(r["country"], float(r["cpi_pct"])) for r in rows]
    hyperinfl = sum(1 for _, v in vals if v > 20)
    high = sum(1 for _, v in vals if v > 10)
    deflation = sum(1 for _, v in vals if v < 0)
    hi = max(vals, key=lambda kv: kv[1], default=("?", 0))
    print(f"worldbank_cpi: {len(rows)} countries | hyperinfl>20%="
          f"{hyperinfl} high>10%={high} deflation<0%={deflation} | "
          f"hi {hi[0]}={hi[1]:.1f}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
