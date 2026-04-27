#!/usr/bin/env python3
"""build_nyiso_grid.py — New York ISO fuel-mix snapshot.

NYISO covers all NY state, including NYC/LI load pockets — the densest
AI-datacenter and finance-sector electricity draw in the Northeast.

Signal:
- NG MW share = LDC (NJR, SJI, NRG) + eastern NG E&P demand
- Nuclear MW = CEG (Ginna, Nine Mile Point, FitzPatrick)
- Dual Fuel on = oil-price sensitive switching
- Wind/Solar/Hydro = renewables dev (NEE, AVGR, GEV)
- Hour-on-hour ramp = battery/peaker utilization

Source: mis.nyiso.com/public/csv/rtfuelmix/{YYYYMMDD}rtfuelmix.csv
Output: nyiso_grid.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nyiso_grid.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def _get(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"nyiso_grid: {url}: {e}")
        return None


def main() -> None:
    # NYISO publishes per-day CSV; try today, fall back to yesterday.
    now_utc = dt.datetime.now(dt.timezone.utc)
    et_now = now_utc - dt.timedelta(hours=4)  # rough EDT
    for delta in (0, 1):
        d = et_now - dt.timedelta(days=delta)
        stamp = d.strftime("%Y%m%d")
        url = (f"http://mis.nyiso.com/public/csv/rtfuelmix/"
               f"{stamp}rtfuelmix.csv")
        txt = _get(url)
        if txt and txt.count("\n") > 10:
            break
    else:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nyiso_grid: no fetch, keeping {OUT_CSV.name}")
        return

    lines = txt.strip().splitlines()
    if not lines or len(lines) < 2:
        return

    reader = csv.DictReader(lines)
    all_rows = list(reader)
    if not all_rows:
        return

    # Latest snapshot = max Time Stamp.
    latest_ts = max(r["Time Stamp"] for r in all_rows if r.get("Time Stamp"))
    snap = [r for r in all_rows if r.get("Time Stamp") == latest_ts]

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now_iso = now_iso.replace("+00:00", "Z")

    rows: list[dict] = []
    total = 0.0
    renew = 0.0
    RENEW = {"Wind", "Solar", "Hydro", "Other Renewables"}
    for r in snap:
        fuel = r.get("Fuel Category", "").strip()
        try:
            mw = float(r.get("Gen MW", "0") or "0")
        except Exception:
            mw = 0.0
        if fuel:
            total += mw
            if fuel in RENEW:
                renew += mw
            rows.append({
                "metric": "fuel_mw",
                "name": fuel,
                "value": f"{mw:.1f}",
                "unit": "MW",
                "snapshot_time": latest_ts,
                "captured_at": now_iso,
            })

    if total > 0:
        rows.append({
            "metric": "renewable_share",
            "name": "renewable_pct",
            "value": f"{100.0 * renew / total:.2f}",
            "unit": "pct",
            "snapshot_time": latest_ts,
            "captured_at": now_iso,
        })
        rows.append({
            "metric": "total_gen",
            "name": "total_mw",
            "value": f"{total:.1f}",
            "unit": "MW",
            "snapshot_time": latest_ts,
            "captured_at": now_iso,
        })

    if not rows:
        return

    rows.sort(key=lambda r: (r["metric"], r["name"]))
    fieldnames = ["metric", "name", "value", "unit",
                  "snapshot_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_fuel = {r["name"]: float(r["value"]) for r in rows
               if r["metric"] == "fuel_mw"}
    total_gw = total / 1000
    ng = by_fuel.get("Natural Gas", 0) / 1000
    nuc = by_fuel.get("Nuclear", 0) / 1000
    hyd = by_fuel.get("Hydro", 0) / 1000
    wind = by_fuel.get("Wind", 0) / 1000
    print(f"nyiso_grid: {len(rows)} rows | {latest_ts} total={total_gw:.1f}GW "
          f"renew={100.0*renew/total:.1f}% | "
          f"NG={ng:.1f} Nuc={nuc:.1f} Hydro={hyd:.1f} Wind={wind:.2f} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
