#!/usr/bin/env python3
"""build_ecb_monetary.py — ECB M3 money supply + euro yield curve.

Euro liquidity regime + EUR rate expectations from the ECB Statistical
Data Warehouse.

Series captured:
- BSI: M1, M2, M3 money aggregates (monthly stocks)
- YC : euro-area sovereign (AAA-only) zero-coupon yields
       3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y (daily)

Signal:
- M3 growth collapsing → EU recession leading indicator (banks DB CS
  UBS SAN BBVA compress), euro strengthens vs EM
- Euro 2s10s inversion → EU banks ROE pain, preferred to short
  European banks, long US banks
- 10Y yield spike → European sovereign stress → core periphery
  spread widens (Italy, Greece stress → BTP ETFs)

Drives:
- European bank ADRs (DB, SAN, BCS, BBVA, CS equivalents)
- Euro-FX pairs (FXE, USDEUR)
- EU industrial exporters (SAP, ASML, BUD, UL)
- US multinationals with EU exposure (AAPL, MCD, PG, CAT)
- Eurobond ETFs (BWX, IGOV)

Source: data-api.ecb.europa.eu/service/data (free, no key).
Output: ecb_monetary.csv
Columns: series, series_key, period, value, unit, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from io import StringIO
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ecb_monetary.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://data-api.ecb.europa.eu/service/data"

# BSI: eurozone monetary aggregates (stocks, EUR millions).
BSI_SERIES = [
    ("M1", "BSI/M.U2.N.V.M10.X.1.U2.2300.Z01.E"),
    ("M2", "BSI/M.U2.N.V.M20.X.1.U2.2300.Z01.E"),
    ("M3", "BSI/M.U2.N.V.M30.X.1.U2.2300.Z01.E"),
]

# YC: euro-area (AAA) zero-coupon yields (daily, percent).
YC_SERIES = [
    ("yield_3m",  "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_3M"),
    ("yield_6m",  "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_6M"),
    ("yield_1y",  "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_1Y"),
    ("yield_2y",  "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"),
    ("yield_5y",  "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y"),
    ("yield_10y", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"),
    ("yield_30y", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y"),
]


def _fetch(path: str, n: int) -> list[dict] | None:
    url = (f"{BASE}/{path}?lastNObservations={n}"
           f"&format=csvdata")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/csv",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"ecb_monetary: {path}: {e}")
        return None
    reader = csv.DictReader(StringIO(text))
    return list(reader)


def main() -> None:
    import time
    rows: list[dict] = []

    for label, key in BSI_SERIES:
        data = _fetch(key, n=24)  # 24 months
        if not data:
            time.sleep(2)
            continue
        for rec in data:
            period = rec.get("TIME_PERIOD", "").strip()
            raw = rec.get("OBS_VALUE", "").strip()
            if not period or not raw:
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            rows.append({
                "series": label,
                "series_key": key.split("/", 1)[-1],
                "period": period,
                "value": f"{val:.2f}",
                "unit": "eur_millions",
            })
        time.sleep(1)

    for label, key in YC_SERIES:
        data = _fetch(key, n=60)  # 60 business days
        if not data:
            time.sleep(2)
            continue
        for rec in data:
            period = rec.get("TIME_PERIOD", "").strip()
            raw = rec.get("OBS_VALUE", "").strip()
            if not period or not raw:
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            rows.append({
                "series": label,
                "series_key": key.split("/", 1)[-1],
                "period": period,
                "value": f"{val:.4f}",
                "unit": "percent",
            })
        time.sleep(1)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ecb_monetary: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["series", "series_key", "period", "value", "unit",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest M3, 2Y, 10Y, 2s10s spread.
    def _latest(series: str) -> dict | None:
        cand = [r for r in rows if r["series"] == series]
        cand.sort(key=lambda r: r["period"], reverse=True)
        return cand[0] if cand else None

    m3 = _latest("M3")
    y2 = _latest("yield_2y")
    y10 = _latest("yield_10y")
    y30 = _latest("yield_30y")
    bits = []
    if m3:
        bits.append(f"M3={float(m3['value'])/1e6:.2f}T ({m3['period']})")
    if y2:
        bits.append(f"2Y={y2['value']}%")
    if y10:
        bits.append(f"10Y={y10['value']}%")
    if y2 and y10:
        spread_bp = (float(y10["value"]) - float(y2["value"])) * 100
        bits.append(f"2s10s={spread_bp:+.0f}bp")
    if y30:
        bits.append(f"30Y={y30['value']}%")

    print(f"ecb_monetary: {len(rows)} rows | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
