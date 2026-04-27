#!/usr/bin/env python3
"""build_ercot_fuelmix.py — ERCOT Texas grid real-time fuel mix.

ERCOT publishes the Texas grid's real-time generation by fuel source
every 5 minutes. Texas is now the canonical US AI-datacenter + crypto-
mining power draw proxy (Oracle OCI, MSFT, GOOG, META all building
giga-campuses; MARA/RIOT/CIFR/HUT mining fleet). Grid strain here
leads headlines 6-24 hours before broader power-rationing events.

Signal:
- Solar gen > 30,000 MW = midday oversupply (negative power pricing,
  free for flexible-load miners)
- Wind < 2,000 MW + Solar declining into evening + grid >75GW = peak
  shortage risk (CEG, VST nuclear premium, NG peakers ETR, EXC)
- Natural gas share > 45% = gas-merchant earnings tailwind (RRC,
  EQT, AR, CTRA)
- Coal/lignite declining 3mo ann. = structural retirement (Jim's XCE,
  CNX, HNRG short signals)
- Renewable share > 55% at midday = battery storage arbitrage window
  (TSLA, FLNC, STEM, BE)
- Power storage gen > 8 GW on demand-side = utility-scale arb
  realized (PLUG, FLNC inflow)

Drives:
- Natural gas E&P (RRC, EQT, AR, CTRA, EOG, FANG) via gas share
- Nuclear (CEG, VST, NEE, SO, DUK) via baseload premium
- Utility-scale solar (FSLR, ENPH, NXT, SEDG, RUN) via solar penetration
- Wind (NEE, AVGR, GEV, TPIC) via wind share
- Grid storage (TSLA energy, FLNC, STEM, BE) via storage dispatch
- Crypto miners (MARA, RIOT, CIFR, HUT, CLSK) via free-power windows

Source: ercot.com/api/1/services/read/dashboards/fuel-mix.json (public
JSON, 5-minute refresh, no key).
Output: ercot_fuelmix.csv
Columns: snapshot_ts, fuel, generation_mw, capacity_mw, share_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ercot_fuelmix.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.ercot.com/api/1/services/read/dashboards/fuel-mix.json"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"ercot_fuelmix: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ercot_fuelmix: keeping existing {OUT_CSV.name}")
        return

    cap = payload.get("monthlyCapacity") or {}
    data = payload.get("data") or {}
    if not data:
        return

    last_day = sorted(data.keys())[-1]
    day = data[last_day]
    last_ts = sorted(day.keys())[-1]
    snap = day[last_ts] or {}

    fuels: list[tuple[str, float]] = []
    for fuel, rec in snap.items():
        gen = rec.get("gen") if isinstance(rec, dict) else None
        if gen is None:
            continue
        try:
            fuels.append((fuel, float(gen)))
        except (TypeError, ValueError):
            continue

    if not fuels:
        return

    total = sum(g for _, g in fuels)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    rows: list[dict] = []
    for fuel, gen in sorted(fuels, key=lambda x: -x[1]):
        rows.append({
            "snapshot_ts": last_ts,
            "fuel": fuel[:30],
            "generation_mw": f"{gen:.1f}",
            "capacity_mw": f"{cap.get(fuel, 0):.0f}",
            "share_pct": (f"{100 * gen / total:.2f}"
                          if total > 0 else ""),
            "captured_at": now,
        })

    fieldnames = ["snapshot_ts", "fuel", "generation_mw", "capacity_mw",
                  "share_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top3 = rows[:3]
    bits = [f"{r['fuel']}={float(r['generation_mw'])/1000:.1f}GW"
            f"({r['share_pct']}%)" for r in top3]
    reneg = sum(float(r["generation_mw"]) for r in rows
                if r["fuel"] in ("Solar", "Wind", "Hydro"))
    reneg_pct = (100 * reneg / total) if total > 0 else 0
    print(f"ercot_fuelmix: {len(rows)} fuels @ {last_ts} | "
          f"total={total/1000:.1f}GW renewable={reneg_pct:.1f}% | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
