#!/usr/bin/env python3
"""build_worldbank_gdp.py — World Bank annual GDP growth by country.

Macro backdrop for global-exposure equities. Real GDP growth (constant
local currency, annualized %) by major economies — decouples US S&P
narrative from ex-US performance for names with large non-US revenue:
AAPL, GOOGL, MSFT, META, KO, PG, JNJ, NKE, TSLA.

Trade context:
- China slowdown → $CAT, $FCX, $DE iron/copper ETF bid
- EU stagnation → $LVMH, $NSRGY ADR premium compression
- India 6%+ growth → $INDA, $IBN, $HDB momentum
- Brazil volatility → $EWZ, $VALE, $PBR swings

Source: api.worldbank.org/v2 (free, no key).
Indicator: NY.GDP.MKTP.KD.ZG — GDP growth (annual %, constant LCU).

Output: worldbank_gdp.csv
Columns: country_code, country_name, year, gdp_growth_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "worldbank_gdp.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.worldbank.org/v2/country"
INDICATOR = "NY.GDP.MKTP.KD.ZG"

# 22 major economies covering ~85% of global equity-relevant GDP.
COUNTRIES = [
    ("US", "United States"), ("CN", "China"), ("JP", "Japan"),
    ("DE", "Germany"), ("IN", "India"), ("GB", "United Kingdom"),
    ("FR", "France"), ("IT", "Italy"), ("BR", "Brazil"),
    ("CA", "Canada"), ("RU", "Russia"), ("KR", "Korea"),
    ("AU", "Australia"), ("ES", "Spain"), ("MX", "Mexico"),
    ("ID", "Indonesia"), ("NL", "Netherlands"), ("SA", "Saudi Arabia"),
    ("TR", "Turkey"), ("TW", "Taiwan"), ("CH", "Switzerland"),
    ("SE", "Sweden"),
]


def _fetch(iso2: str) -> list:
    url = (f"{BASE}/{iso2}/indicator/{INDICATOR}"
           f"?format=json&per_page=3&date=2022:2024")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        if isinstance(d, list) and len(d) >= 2 and isinstance(d[1], list):
            return d[1]
        return []
    except Exception as e:
        print(f"worldbank_gdp {iso2}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    for code, name in COUNTRIES:
        obs = _fetch(code)
        for row in obs:
            if not isinstance(row, dict):
                continue
            val = row.get("value")
            if val is None:
                continue
            rows.append({
                "country_code": code,
                "country_name": name,
                "year": (row.get("date") or "")[:4],
                "gdp_growth_pct": f"{float(val):.3f}",
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_gdp: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["country_code"], r["year"]), reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["country_code", "country_name",
                                          "year", "gdp_growth_pct",
                                          "captured_at"])
        w.writeheader()
        w.writerows(rows)

    latest_year = max((r["year"] for r in rows), default="?")
    latest = [r for r in rows if r["year"] == latest_year]
    latest.sort(key=lambda r: float(r["gdp_growth_pct"]), reverse=True)
    top = latest[0] if latest else {}
    bot = latest[-1] if latest else {}
    print(f"worldbank_gdp: {len(rows)} obs | {latest_year} top: "
          f"{top.get('country_code','?')}={top.get('gdp_growth_pct','?')}%"
          f" | bot: {bot.get('country_code','?')}="
          f"{bot.get('gdp_growth_pct','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
