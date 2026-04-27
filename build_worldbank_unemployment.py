#!/usr/bin/env python3
"""build_worldbank_unemployment.py — World Bank global unemployment.

Cross-country unemployment (SL.UEM.TOTL.ZS, modeled ILO estimate).
Complements build_worldbank_gdp — unemployment is a coincident-to-
lagging indicator that frames global demand backdrop for:
- Global industrials (CAT, DE, ETN)
- Staffing (MAN, RHI, ASGN, KFY)
- Consumer finance (COF, DFS, SYF, ALLY — credit loss cycles)
- Multinational consumer (NKE, MCD, SBUX, KO, PEP)
- EM exposure (BABA, JD, MELI, VALE, ITUB)

Signal: countries with UE >12% or deteriorating >1pt YoY flag weak
demand zones; sub-4% flags tight labor / wage inflation risk.

Source: api.worldbank.org/v2 (free, no key).
Output: worldbank_unemployment.csv
Columns: iso3, country, year, unemployment_pct, yoy_delta,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "worldbank_unemployment.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.worldbank.org/v2/country/all/indicator/"
       "SL.UEM.TOTL.ZS?format=json&date=2022:2024&per_page=2000")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"worldbank_unemployment: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_unemployment: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(payload, list) or len(payload) < 2:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_unemployment: empty, keeping existing "
                  f"{OUT_CSV.name}")
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
            print(f"worldbank_unemployment: parsed 0, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for iso3, years in by_country.items():
        if not years:
            continue
        latest_year = max(years.keys())
        latest = years[latest_year]
        prev_year = str(int(latest_year) - 1)
        delta = ""
        if prev_year in years:
            delta = f"{latest - years[prev_year]:+.2f}"
        rows.append({
            "iso3": iso3,
            "country": names.get(iso3, iso3),
            "year": latest_year,
            "unemployment_pct": f"{latest:.2f}",
            "yoy_delta": delta,
        })

    rows.sort(key=lambda r: r["country"])

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["iso3", "country", "year", "unemployment_pct",
                  "yoy_delta", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    vals = [(r["country"], float(r["unemployment_pct"]))
            for r in rows if r["unemployment_pct"]]
    hi = max(vals, key=lambda kv: kv[1], default=("?", 0))
    lo = min(vals, key=lambda kv: kv[1], default=("?", 0))
    tight = sum(1 for _, v in vals if v < 4)
    slack = sum(1 for _, v in vals if v > 12)
    print(f"worldbank_unemployment: {len(rows)} countries | tight<4%={tight}"
          f" slack>12%={slack} | hi {hi[0]}={hi[1]:.1f}% lo "
          f"{lo[0]}={lo[1]:.1f}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
