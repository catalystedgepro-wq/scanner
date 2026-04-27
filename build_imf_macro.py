#!/usr/bin/env python3
"""build_imf_macro.py — IMF World Economic Outlook cross-country macro.

Cross-country macro indicators from IMF DataMapper (WEO dataset).
Captures inflation, GDP growth, and sovereign-debt-to-GDP for the
major economies. Rolling 10-year window per country.

Series tracked:
- PCPIPCH    CPI inflation, YoY %
- NGDP_RPCH  real GDP growth, YoY %
- GGXWDG_NGDP  general govt gross debt, % of GDP

Countries: USA, CHN, JPN, DEU, GBR, FRA, IND, ITA, BRA, CAN,
           KOR, MEX, RUS, ESP, AUS, IDN, TUR, SAU, ARG

Signal for trading:
- US inflation > target + 2pt for 2+ years => fade long-duration
  (TLT), bid commodities (DBA/DBC), fade rate-sensitive tech.
- Germany debt/GDP rising through 70% sustained = EU-bund spread
  widening; fade European banks (DB, SAN). EZU down tick.
- China debt/GDP >85% + negative growth gap = CNY depreciation
  pressure; fade EEM, bid DXY/UUP.
- Japan debt/GDP >250% sustained = yield-curve-control stress tell;
  bid JPY on BoJ pivot speculation.

Source: www.imf.org/external/datamapper/api/v1/{ind}/{iso3,...}
        Returns {"values": {ind: {iso3: {year: val, ...}, ...}}}.

Output: imf_macro.csv
Columns: country, iso3, indicator, year, value_pct, yoy_delta,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "imf_macro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://www.imf.org/external/datamapper/api/v1"

COUNTRIES = [
    ("USA", "United States"),
    ("CHN", "China"),
    ("JPN", "Japan"),
    ("DEU", "Germany"),
    ("GBR", "United Kingdom"),
    ("FRA", "France"),
    ("IND", "India"),
    ("ITA", "Italy"),
    ("BRA", "Brazil"),
    ("CAN", "Canada"),
    ("KOR", "South Korea"),
    ("MEX", "Mexico"),
    ("RUS", "Russia"),
    ("ESP", "Spain"),
    ("AUS", "Australia"),
    ("IDN", "Indonesia"),
    ("TUR", "Turkey"),
    ("SAU", "Saudi Arabia"),
    ("ARG", "Argentina"),
]

INDICATORS = [
    ("PCPIPCH", "cpi_infl_pct"),
    ("NGDP_RPCH", "real_gdp_growth_pct"),
    ("GGXWDG_NGDP", "debt_to_gdp_pct"),
]


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"imf_macro {url}: {e}")
        return {}


def main() -> None:
    iso_list = ",".join(c[0] for c in COUNTRIES)
    name_of = dict(COUNTRIES)
    this_year = dt.date.today().year
    min_year = this_year - 10

    rows: list[dict] = []
    for ind, ind_name in INDICATORS:
        url = f"{BASE}/{ind}/{iso_list}"
        d = _fetch(url)
        series = d.get("values", {}).get(ind, {}) or {}
        for iso3, years in series.items():
            if not isinstance(years, dict):
                continue
            ordered = sorted(
                (int(y), float(v)) for y, v in years.items()
                if v is not None and str(y).isdigit()
            )
            by_year = dict(ordered)
            for y, v in ordered:
                if y < min_year:
                    continue
                prev = by_year.get(y - 1)
                yoy = (v - prev) if prev is not None else None
                rows.append({
                    "country": name_of.get(iso3, iso3),
                    "iso3": iso3,
                    "indicator": ind_name,
                    "year": str(y),
                    "value_pct": f"{v:.3f}",
                    "yoy_delta": (f"{yoy:+.3f}"
                                  if yoy is not None else ""),
                })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"imf_macro: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["indicator"], r["iso3"], r["year"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["country", "iso3", "indicator", "year",
                  "value_pct", "yoy_delta", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest USA inflation + latest CHN growth + DEU debt.
    def _latest(iso3: str, ind_name: str) -> dict | None:
        xs = [r for r in rows
              if r["iso3"] == iso3 and r["indicator"] == ind_name]
        return xs[-1] if xs else None

    us = _latest("USA", "cpi_infl_pct")
    cn = _latest("CHN", "real_gdp_growth_pct")
    de = _latest("DEU", "debt_to_gdp_pct")
    us_s = (f"US CPI {us['year']}={us['value_pct']}%"
            if us else "")
    cn_s = (f"CN GDPg {cn['year']}={cn['value_pct']}%"
            if cn else "")
    de_s = (f"DE debt/GDP {de['year']}={de['value_pct']}%"
            if de else "")
    print(f"imf_macro: {len(rows)} rows | {us_s} | {cn_s} | {de_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
