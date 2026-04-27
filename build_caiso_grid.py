#!/usr/bin/env python3
"""build_caiso_grid.py — California ISO grid fuel-mix + demand snapshot.

CAISO covers ~80% of California + a chunk of Nevada — the second-biggest
US grid footprint after PJM. Gives the west-coast solar-heavy duck-curve
read and AI/EV-driven Silicon Valley load that ERCOT doesn't see.

Signal:
- Solar peak MW → FSLR, ENPH, NXT, RUN, SEDG demand curve
- Battery output → TSLA, FLNC, STEM megapack pull
- Import share → adjacent-state power exporters
- Net-demand spike vs current → CA retail utility (PCG, EIX, SRE) margin
- Natural-gas share when solar drops → western NG E&P (EQT, AR, CTRA)

Source: caiso.com/outlook/current/{fuelsource,demand,netdemand}.csv
Output: caiso_grid.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "caiso_grid.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://www.caiso.com/outlook/current"


def _get(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"caiso_grid: {url}: {e}")
        return None


def _parse_csv(txt: str) -> list[dict]:
    rows: list[dict] = []
    reader = csv.DictReader(txt.splitlines())
    for row in reader:
        rows.append(row)
    return rows


def _latest_nonempty(rows: list[dict]) -> dict | None:
    # Walk from bottom to find last row with any numeric col.
    for row in reversed(rows):
        for k, v in row.items():
            if k == "Time":
                continue
            if v and v.strip() not in ("", "-"):
                return row
    return None


def main() -> None:
    fuel_txt = _get(f"{BASE}/fuelsource.csv")
    dem_txt = _get(f"{BASE}/demand.csv")
    net_txt = _get(f"{BASE}/netdemand.csv")

    if not fuel_txt and not dem_txt and not net_txt:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"caiso_grid: no fetch, keeping {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []

    if fuel_txt:
        fuel_rows = _parse_csv(fuel_txt)
        lat = _latest_nonempty(fuel_rows)
        if lat:
            t = lat.get("Time", "")
            total = 0.0
            renew = 0.0
            RENEW = {"Solar", "Wind", "Geothermal", "Biomass",
                     "Biogas", "Small hydro", "Large Hydro", "Batteries"}
            for k, v in lat.items():
                if k == "Time":
                    continue
                try:
                    mw = float(v) if v.strip() not in ("", "-") else 0.0
                except Exception:
                    mw = 0.0
                total += abs(mw) if k == "Batteries" else max(mw, 0.0)
                if k in RENEW and mw > 0:
                    renew += mw
                rows.append({
                    "metric": "fuel_mw",
                    "name": k,
                    "value": f"{mw:.0f}",
                    "unit": "MW",
                    "snapshot_time": t,
                    "captured_at": now,
                })
            if total > 0:
                rows.append({
                    "metric": "renewable_share",
                    "name": "renewable_pct",
                    "value": f"{100.0 * renew / total:.2f}",
                    "unit": "pct",
                    "snapshot_time": t,
                    "captured_at": now,
                })
                rows.append({
                    "metric": "total_supply",
                    "name": "total_mw",
                    "value": f"{total:.0f}",
                    "unit": "MW",
                    "snapshot_time": t,
                    "captured_at": now,
                })

    if dem_txt:
        dem_rows = _parse_csv(dem_txt)
        lat = _latest_nonempty(dem_rows)
        if lat:
            t = lat.get("Time", "")
            for k, v in lat.items():
                if k == "Time":
                    continue
                try:
                    mw = float(v) if v.strip() not in ("", "-") else None
                except Exception:
                    mw = None
                if mw is None:
                    continue
                rows.append({
                    "metric": "demand_mw",
                    "name": k,
                    "value": f"{mw:.0f}",
                    "unit": "MW",
                    "snapshot_time": t,
                    "captured_at": now,
                })

    if net_txt:
        net_rows = _parse_csv(net_txt)
        lat = _latest_nonempty(net_rows)
        if lat:
            t = lat.get("Time", "")
            for k, v in lat.items():
                if k == "Time":
                    continue
                try:
                    mw = float(v) if v.strip() not in ("", "-") else None
                except Exception:
                    mw = None
                if mw is None:
                    continue
                rows.append({
                    "metric": "netdemand_mw",
                    "name": k,
                    "value": f"{mw:.0f}",
                    "unit": "MW",
                    "snapshot_time": t,
                    "captured_at": now,
                })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"caiso_grid: empty rows, keeping {OUT_CSV.name}")
        return

    fieldnames = ["metric", "name", "value", "unit",
                  "snapshot_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    solar = next((r for r in rows
                  if r["metric"] == "fuel_mw" and r["name"] == "Solar"), None)
    ng = next((r for r in rows
               if r["metric"] == "fuel_mw" and r["name"] == "Natural Gas"),
              None)
    renew = next((r for r in rows if r["metric"] == "renewable_share"), None)
    total = next((r for r in rows if r["metric"] == "total_supply"), None)
    cur = next((r for r in rows
                if r["metric"] == "demand_mw"
                and r["name"] == "Current demand"), None)
    bits: list[str] = []
    if total:
        bits.append(f"total={float(total['value'])/1000:.1f}GW")
    if renew:
        bits.append(f"renew={renew['value']}%")
    if solar:
        bits.append(f"Solar={float(solar['value'])/1000:.1f}GW")
    if ng:
        bits.append(f"NG={float(ng['value'])/1000:.1f}GW")
    if cur:
        bits.append(f"demand={float(cur['value'])/1000:.1f}GW")
    print(f"caiso_grid: {len(rows)} rows | {' '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
