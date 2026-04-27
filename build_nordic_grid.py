#!/usr/bin/env python3
"""build_nordic_grid.py — Nord Pool electricity + Danish grid CO2.

Nordic wholesale power data relevant to European energy equities
(ORSTED.CO, VWS.CO, EQNR, FORTUM.HE) and US wind/nuclear (NEE, CEG).

Three Danish Energy Data Service endpoints (no-key, live):
1. Elspotprices — day-ahead EUR price for DK1/DK2/DE/NO2/SE3/SE4/…
2. CO2Emis — 5-min carbon intensity for DK1/DK2
3. DeclarationProduction — fuel-mix production declaration by type

Catalyst reads:
- Elspot EUR spike in DE (German zone) → UK/IE power price follow
- DK1 negative prices → wind oversupply → curtailment narrative for
  Orsted; bullish for battery storage (FLNC, ALB lithium feedback)
- CO2Emis divergence DK1 vs DK2 → interconnector flow signal
- BioGas share falling = cold-snap gas demand (CTRA, EQNR)

Output: nordic_grid.csv
Columns: dataset, price_area, metric_name, value, unit, ts, captured_at

Source: api.energidataservice.dk (live, no key).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nordic_grid.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.energidataservice.dk/dataset"


def _fetch(dataset: str, params: dict) -> list:
    url = f"{BASE}/{dataset}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
        return data.get("records") or []
    except Exception as e:
        print(f"nordic_grid {dataset}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []

    # 1. Elspot prices — most recent 24h across price areas.
    elspot = _fetch("Elspotprices", {"limit": 500, "sort": "HourUTC DESC"})
    if elspot:
        # Take latest hour's rows across all PriceAreas.
        latest_ts = elspot[0].get("HourUTC", "")
        for rec in elspot:
            ts = rec.get("HourUTC", "")
            if ts != latest_ts:
                break
            area = rec.get("PriceArea", "")
            eur = rec.get("SpotPriceEUR")
            if area and eur is not None:
                rows.append({
                    "dataset": "elspot",
                    "price_area": area,
                    "metric_name": "spot_price_eur_mwh",
                    "value": f"{float(eur):.2f}",
                    "unit": "EUR_per_MWh",
                    "ts": ts,
                })

    # 2. CO2 emissions — most recent 5-min obs for DK1/DK2.
    co2 = _fetch("CO2Emis", {"limit": 10, "sort": "Minutes5UTC DESC"})
    if co2:
        seen = set()
        for rec in co2:
            area = rec.get("PriceArea", "")
            if area in seen:
                continue
            seen.add(area)
            val = rec.get("CO2Emission")
            ts = rec.get("Minutes5UTC", "")
            if val is not None:
                rows.append({
                    "dataset": "co2_emis",
                    "price_area": area,
                    "metric_name": "grid_co2_intensity",
                    "value": f"{float(val):.1f}",
                    "unit": "gCO2_per_kWh",
                    "ts": ts,
                })

    # 3. Production declaration — latest hour per fuel type.
    prod = _fetch("DeclarationProduction",
                  {"limit": 200, "sort": "HourUTC DESC"})
    if prod:
        latest_ts = prod[0].get("HourUTC", "")
        # Aggregate share by ProductionType for DK1 grid deliveries.
        agg: dict[str, float] = {}
        for rec in prod:
            if rec.get("HourUTC") != latest_ts:
                break
            if rec.get("PriceArea") != "DK1":
                continue
            if rec.get("DeliveryType") != "Grid":
                continue
            ptype = rec.get("ProductionType", "")
            share = rec.get("ShareGrid")
            if ptype and share is not None:
                agg[ptype] = agg.get(ptype, 0.0) + float(share)
        for ptype, share in sorted(agg.items(),
                                   key=lambda kv: -kv[1])[:12]:
            rows.append({
                "dataset": "prod_mix_dk1",
                "price_area": "DK1",
                "metric_name": f"share_{ptype[:20]}",
                "value": f"{share:.2f}",
                "unit": "percent_grid",
                "ts": latest_ts,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nordic_grid: no data, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["dataset", "price_area", "metric_name", "value",
                  "unit", "ts", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    dk1 = next((r for r in rows if r["dataset"] == "elspot"
                and r["price_area"] == "DK1"), {})
    de = next((r for r in rows if r["dataset"] == "elspot"
               and r["price_area"] == "DE"), {})
    co2_dk1 = next((r for r in rows if r["dataset"] == "co2_emis"
                    and r["price_area"] == "DK1"), {})
    prod_n = sum(1 for r in rows if r["dataset"] == "prod_mix_dk1")
    print(f"nordic_grid: {len(rows)} rows | DK1 elspot="
          f"€{dk1.get('value','?')}/MWh DE elspot=€{de.get('value','?')} | "
          f"DK1 CO2={co2_dk1.get('value','?')}g/kWh | "
          f"{prod_n} fuel types -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
