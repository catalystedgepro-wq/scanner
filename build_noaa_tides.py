#!/usr/bin/env python3
"""build_noaa_tides.py — NOAA CO-OPS port water levels.

Near-real-time water levels + tide predictions at 8 major US
shipping/energy ports. Operational proxy for port activity,
storm-surge flooding, and cruise/refinery accessibility.

Ports tracked:
- 9410660 Los Angeles (container port, largest US by TEU)
- 9414290 San Francisco (west-coast bulk)
- 8454000 Providence RI (cruise/distribution)
- 8518750 The Battery NY (harbor commerce, storm-surge benchmark)
- 8638610 Sewells Point VA (Navy Norfolk + Virginia Port Authority)
- 8665530 Charleston SC (mega-container East)
- 8723214 Virginia Key FL (Miami/Fort Lauderdale cruise)
- 8771013 Eagle Point TX (Houston Ship Channel — Gulf refiners)

Signal for trading:
- Storm surge >4 ft at Battery NY / Sewells Point → insurance
  complex (ALL/TRV/CB/HIG) drawdown, GNRC/HD/LOW bid.
- Sustained low tide + Mississippi barge-low-water → rail
  beneficiaries (UNP/NSC/CSX) pair trade.
- Houston Ship Channel shutdown signals (surge + wind) →
  refined-product crack spreads (VLO/MPC/PSX margin whipsaw).
- Charleston/Savannah surge → retailer Q3 inventory risk
  (TGT/WMT/BBY/LOW).

Source: api.tidesandcurrents.noaa.gov (CO-OPS; no key).
  product=water_level (observed), range=48h.

Output: noaa_tides.csv
Columns: station_id, station_name, timestamp, water_level_ft,
         anomaly_ft, captured_at

Anomaly = latest obs vs median of prior 24h (simple local zero).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path
from statistics import median

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "noaa_tides.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

STATIONS = {
    "9410660": "Los Angeles CA",
    "9414290": "San Francisco CA",
    "8454000": "Providence RI",
    "8518750": "Battery NY",
    "8638610": "Sewells Point VA",
    "8665530": "Charleston SC",
    "8723214": "Virginia Key FL",
    "8771013": "Eagle Point TX (Houston)",
}


def fetch_station(station: str) -> list[dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=2)
    params = {
        "product": "water_level",
        "application": "CatalystEdge",
        "begin_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "datum": "MLLW",
        "station": station,
        "time_zone": "gmt",
        "units": "english",
        "format": "json",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"noaa_tides {station}: {e}")
        return []
    try:
        d = json.loads(raw)
    except Exception:
        return []
    return d.get("data", []) or []


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    ok = 0
    for st, name in STATIONS.items():
        pts = fetch_station(st)
        if not pts:
            continue
        # Latest observation + 24h median for anomaly.
        vals: list[float] = []
        for p in pts:
            try:
                vals.append(float(p.get("v", "")))
            except Exception:
                continue
        if not vals:
            continue
        # Median of prior-24h window (last 240 obs at 6-min cadence).
        recent = vals[-240:] if len(vals) > 240 else vals
        prior = vals[-480:-240] if len(vals) >= 480 else vals[:-len(recent)] or vals
        latest = vals[-1]
        base = median(prior) if prior else median(recent)
        anomaly = latest - base
        latest_t = pts[-1].get("t", "")
        rows.append({
            "station_id": st,
            "station_name": name,
            "timestamp": latest_t,
            "water_level_ft": f"{latest:.3f}",
            "anomaly_ft": f"{anomaly:+.3f}",
            "captured_at": now,
        })
        ok += 1

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"noaa_tides: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Sort by anomaly magnitude (largest deviation first).
    rows.sort(key=lambda r: -abs(float(r["anomaly_ft"])))

    fieldnames = ["station_id", "station_name", "timestamp",
                  "water_level_ft", "anomaly_ft", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    worst = rows[0]
    print(f"noaa_tides: {ok}/{len(STATIONS)} ports | "
          f"max_anomaly={worst['station_name']} "
          f"{worst['anomaly_ft']}ft -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
