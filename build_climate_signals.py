#!/usr/bin/env python3
"""build_climate_signals.py — global CO2 + surface temperature anomaly.

Two headline climate indicators on one sheet:
- NOAA Mauna Loa CO2 monthly (ppm), deseasonalised + trend
- NASA GISTEMP land+ocean temperature anomaly vs 1951-1980 (°C)

Both released monthly with ~1-month lag. YoY change surfaces the
acceleration or plateauing of each signal.

Signal: CO2 YoY > 2.5ppm + GISTEMP YoY positive = climate-urgency
cycle pricing in. Drives IRA beneficiary re-rating (solar/wind/EV/heat
pump) and insurance loss-cost forecasts (climate-exposed property).

Drives:
- Solar + renewable (ENPH, SEDG, FSLR, RUN, NOVA, ARRY)
- Wind (GE, VWSYF, TPIC)
- EV + storage (TSLA, CHPT, EVGO, BLNK, STEM)
- Insurance climate risk (ALL, TRV, PGR, CB)
- Natural disaster reinsurers (RNR, EG, AJG)
- Weatherizing / HVAC (CARR, TT, WMS, AOS)

Source: gml.noaa.gov + data.giss.nasa.gov (free, no key).
Output: climate_signals.csv
Columns: series, period, value, unit, yoy_delta, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "climate_signals.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
CO2_URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.txt"
GIS_URL = ("https://data.giss.nasa.gov/gistemp/tabledata_v4/"
           "GLB.Ts+dSST.csv")


def _fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"climate_signals: {url}: {e}")
        return None


def _parse_co2(text: str) -> list[dict]:
    """Parse Mauna Loa monthly CO2 file.
    Cols: year, month, decimal_date, average, deseasonalized, #days, ...
    """
    rows: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 5:
            continue
        try:
            year = int(parts[0])
            month = int(parts[1])
            avg = float(parts[3])
            deseason = float(parts[4])
        except (TypeError, ValueError):
            continue
        if avg < 0 or deseason < 0:  # flag values
            continue
        period = f"{year:04d}-{month:02d}"
        rows.append({
            "period": period,
            "average": avg,
            "trend": deseason,
        })
    return rows


def _parse_gistemp(text: str) -> list[dict]:
    """Parse NASA GISTEMP monthly anomaly CSV.
    Row format: year, J, F, M, A, M, J, J, A, S, O, N, D, J-D, D-N, DJF, ...
    Anomalies are in 0.01 °C (divide by 100).
    """
    rows: list[dict] = []
    reader = csv.reader(text.splitlines())
    header_seen = False
    for parts in reader:
        if not parts:
            continue
        # Header row starts with "Year" (or looks like it)
        first = parts[0].strip().lower()
        if first.startswith("year"):
            header_seen = True
            continue
        if not header_seen:
            continue
        try:
            year = int(parts[0])
        except (TypeError, ValueError):
            continue
        months = parts[1:13] if len(parts) >= 13 else []
        for i, raw in enumerate(months, start=1):
            raw = raw.strip()
            if not raw or raw in ("***", "---", "NaN"):
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            period = f"{year:04d}-{i:02d}"
            rows.append({"period": period, "anomaly_c": val})
    return rows


def _with_yoy(rows: list[dict], key: str) -> list[dict]:
    """Attach same-month-prior-year delta to each row."""
    idx = {r["period"]: r for r in rows}
    out: list[dict] = []
    for r in rows:
        period = r["period"]
        prev_year = int(period[:4]) - 1
        prev_period = f"{prev_year:04d}-{period[5:7]}"
        delta = ""
        if prev_period in idx:
            try:
                delta = f"{r[key] - idx[prev_period][key]:+.3f}"
            except (TypeError, KeyError):
                delta = ""
        out.append({"period": period, "value": r[key], "yoy_delta": delta})
    return out


def main() -> None:
    co2_text = _fetch(CO2_URL)
    gis_text = _fetch(GIS_URL)

    co2_rows: list[dict] = []
    gis_rows: list[dict] = []

    if co2_text:
        raw = _parse_co2(co2_text)
        avg_yoy = _with_yoy(raw, "average")
        trend_yoy = _with_yoy(raw, "trend")
        # Keep most recent 60 months of trend (deseasonalised) for storage.
        for r in trend_yoy[-60:]:
            co2_rows.append({
                "series": "co2_mlo_trend",
                "period": r["period"],
                "value": f"{r['value']:.2f}",
                "unit": "ppm",
                "yoy_delta": r["yoy_delta"],
            })
        for r in avg_yoy[-24:]:
            co2_rows.append({
                "series": "co2_mlo_raw",
                "period": r["period"],
                "value": f"{r['value']:.2f}",
                "unit": "ppm",
                "yoy_delta": r["yoy_delta"],
            })

    if gis_text:
        raw = _parse_gistemp(gis_text)
        with_yoy = _with_yoy(raw, "anomaly_c")
        for r in with_yoy[-60:]:
            gis_rows.append({
                "series": "gistemp_land_ocean",
                "period": r["period"],
                "value": f"{r['value']:.3f}",
                "unit": "degC",
                "yoy_delta": r["yoy_delta"],
            })

    rows = co2_rows + gis_rows

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"climate_signals: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["series", "period", "value", "unit", "yoy_delta",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_co2 = next((r for r in reversed(co2_rows)
                       if r["series"] == "co2_mlo_trend"), None)
    latest_gis = gis_rows[-1] if gis_rows else None
    bits = []
    if latest_co2:
        bits.append(f"CO2 trend {latest_co2['period']}={latest_co2['value']}"
                    f"ppm ({latest_co2['yoy_delta'] or 'NA'}yoy)")
    if latest_gis:
        bits.append(f"GISTEMP {latest_gis['period']}={latest_gis['value']}"
                    f"°C ({latest_gis['yoy_delta'] or 'NA'}yoy)")
    print(f"climate_signals: {len(rows)} points | {' | '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
