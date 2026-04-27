#!/usr/bin/env python3
"""build_uk_ons_inflation.py — UK ONS inflation dashboard.

UK is the 5th largest equity market and a G7 policy bellwether.
UK CPI/CPIH/RPI prints move:
- GBP pairs (EUR/GBP, USD/GBP) immediately on release day
- FTSE 100 (multinat EPS via GBP translation): FTSE100 is ~75% USD
  revenue so strong GBP = FTSE headwind, weak GBP = FTSE tailwind
- BoE path via Sonia futures → gilt yields → US 10Y via correlated term
  premia drift
- UK-listed banks (HSBC, BCS, LYG) and homebuilders (TW.L, PSN.L)
  whose EPS tied to base-rate trajectory

Fetches 5 ONS timeseries from MM23 dataset:
- D7G7  CPI annual rate
- L55O  CPIH annual rate
- CZBH  RPI annual rate
- CHMK  RPIX index level
- CZEQ  RPI quarter-on-quarter (pct change over 3 months)

Output: uk_ons_inflation.csv
Columns: code, title, period, value, source_dataset, update_date,
captured_at

Source: ons.gov.uk/economy/inflationandpriceindices/timeseries/
{code}/mm23/data (no key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "uk_ons_inflation.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www.ons.gov.uk/economy/inflationandpriceindices"
       "/timeseries/{code}/mm23/data")

SERIES = [
    ("d7g7", "CPI_annual_rate_%"),
    ("l55o", "CPIH_annual_rate_%"),
    ("czbh", "RPI_annual_rate_%"),
    ("chmk", "RPIX_index_2015_100"),
    ("czeq", "RPI_3m_pct_change"),
    ("a2fc", "RPI_1m_pct_change"),
]


def _fetch(code: str) -> dict | None:
    url = URL.format(code=code)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"uk_ons_inflation {code}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for code, lbl in SERIES:
        d = _fetch(code)
        if not d:
            continue
        title = (d.get("description") or {}).get("title", "")[:80]
        months = d.get("months") or []
        # Take last 12 months as rolling window.
        for m in months[-12:]:
            val = str(m.get("value") or "").strip()
            if not val:
                continue
            rows.append({
                "code": code.upper(),
                "label": lbl,
                "title": title,
                "period": m.get("date") or "",
                "value": val,
                "update_date": (m.get("updateDate") or "")[:10],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"uk_ons_inflation: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort by code, then period (recent last).
    rows.sort(key=lambda r: (r["code"], r["period"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["code", "label", "title", "period", "value",
                  "update_date", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Latest snapshot per code.
    latest: dict[str, dict] = {}
    for r in rows:
        latest[r["code"]] = r
    cpi = latest.get("D7G7", {})
    cpih = latest.get("L55O", {})
    rpi = latest.get("CZBH", {})
    print(f"uk_ons_inflation: {len(rows)} rows | CPI={cpi.get('value','?')}% "
          f"CPIH={cpih.get('value','?')}% RPI={rpi.get('value','?')}% "
          f"({cpi.get('period','?')}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
