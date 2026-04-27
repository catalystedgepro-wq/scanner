#!/usr/bin/env python3
"""build_enso_state.py — NOAA ENSO / Nino 3.4 ONI state.

El Nino-Southern Oscillation is the single largest multi-month climate
signal for commodity and equity markets. ONI (Oceanic Nino Index) is the
3-month running mean of SST anomalies in the Nino 3.4 region.

Thresholds:
- El Nino: ≥ +0.5°C for 5 consecutive overlapping 3-mo periods
- La Nina: ≤ -0.5°C for same
- Neutral: between -0.5 and +0.5

Equity impact:
- **El Nino years**: CA/Peru wet winter → hydro utility recovery (AVA,
  NWE). Argentine drought pressure on soy (ADM, BG beneficiaries). Weak
  Indian monsoon → Indian-equity ETF INDA drawdown. Strong Peruvian
  anchovy decline → livestock feed cost rise (TSN, HRL).
- **La Nina years**: Drought in southern US (TX corn/cotton belt), wet
  PNW, active Atlantic hurricane season (pairs with hurricane_radar
  spoke for insurance complex). Gulf Coast natural-gas producer tailwind
  (CTRA, EQT) on cold winter setup.
- **Neutral**: less thematic; look for regional signals only.

Trade uses:
- ENSO shift El Nino → Neutral (or vice versa): multi-month commodity
  rotation; long DBA (ag ETF) 60 days post-flip.
- Strong El Nino (ONI > +1.5): long ADM/BG 3-6 months, short CORN/SOYB
  ETFs during planting season.
- Strong La Nina (ONI < -1.5): long CTRA/EQT winter, long INDA India
  (wet monsoon), short airlines ahead of active hurricane season.

Source: cpc.ncep.noaa.gov/data/indices/oni.ascii.txt (free, no key,
updated monthly, back to 1950).

Output: enso_state.csv
Columns: season, year, sst_total, anomaly, regime, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "enso_state.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"enso_state: {e}")
        return ""


def _regime(anom: float) -> str:
    if anom >= 1.5: return "Strong El Nino"
    if anom >= 1.0: return "Moderate El Nino"
    if anom >= 0.5: return "Weak El Nino"
    if anom <= -1.5: return "Strong La Nina"
    if anom <= -1.0: return "Moderate La Nina"
    if anom <= -0.5: return "Weak La Nina"
    return "Neutral"


def main() -> None:
    text = fetch()
    if not text and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"enso_state: fetch failed, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        seas, yr, total, anom = parts
        if seas in ("SEAS", "Season"):
            continue
        try:
            year = int(yr)
            total_f = float(total)
            anom_f = float(anom)
        except ValueError:
            continue
        rows.append({
            "season": seas,
            "year": str(year),
            "sst_total": f"{total_f:.2f}",
            "anomaly": f"{anom_f:+.2f}",
            "regime": _regime(anom_f),
        })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"enso_state: parsed empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["season", "year", "sst_total", "anomaly",
                        "regime", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    latest = rows[-1] if rows else {}
    # Prior-year same season for YoY regime comparison
    prev = next((r for r in reversed(rows[:-1])
                 if r.get("season") == latest.get("season")), {})
    prev_s = f"| {prev.get('year','')} {prev.get('season','')} anom={prev.get('anomaly','')} ({prev.get('regime','')})" if prev else ""
    print(f"enso_state: {len(rows)} months | latest "
          f"{latest.get('year','?')} {latest.get('season','?')} "
          f"anom={latest.get('anomaly','?')} "
          f"({latest.get('regime','?')}) {prev_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
