#!/usr/bin/env python3
"""build_world_bank_gdp.py — World Bank GDP & growth for major economies.

Economies' real-time nowcasts drive country ETFs (EWJ, EWU, EWG, FXI, EWZ,
INDA, EWY, EWT, RSX) and multinationals (AAPL ~55% non-US, NKE ~58%,
MCD ~60%, KO ~65%).

Source: api.worldbank.org (free, no key required).
  - NY.GDP.MKTP.CD: nominal GDP USD
  - NY.GDP.MKTP.KD.ZG: real GDP growth pct

Output: world_bank_gdp.csv
Columns: country, year, gdp_usd_trillion, real_growth_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "world_bank_gdp.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

COUNTRIES = [
    "USA", "CHN", "JPN", "DEU", "IND", "GBR", "FRA", "ITA", "BRA",
    "CAN", "KOR", "RUS", "MEX", "ESP", "AUS", "TUR", "SAU", "NLD",
    "CHE", "SWE",
]


def fetch(indicator: str, country: str) -> list:
    url = (
        f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
        "?format=json&per_page=5"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data[1] if isinstance(data, list) and len(data) > 1 else []
    except Exception as e:
        print(f"wb {country} {indicator}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for c in COUNTRIES:
        gdp = fetch("NY.GDP.MKTP.CD", c)
        growth = fetch("NY.GDP.MKTP.KD.ZG", c)
        g_map = {x.get("date"): x.get("value") for x in growth if x}
        for rec in gdp:
            if not rec or not rec.get("value"):
                continue
            year = rec.get("date")
            rows.append({
                "country": c,
                "year": year,
                "gdp_usd_trillion": f"{(rec['value'] or 0) / 1e12:.3f}",
                "real_growth_pct": f"{g_map.get(year) or 0:.2f}",
                "captured_at": now,
            })
    rows.sort(key=lambda r: (r["country"], r.get("year", "")), reverse=False)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "country", "year", "gdp_usd_trillion",
                "real_growth_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"world_bank_gdp: {len(rows)} obs / {len(COUNTRIES)} countries -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
