#!/usr/bin/env python3
"""build_uk_grid_transport.py — UK electricity grid + London transport.

Two complementary UK real-time public datasets:

1. National Grid carbon intensity + generation mix (carbonintensity.org.uk)
   - Signals UK utility revenue composition (gas, wind, solar, nuclear)
   - Wind share spikes → SSE, RWE, orsted favourable narrative
   - Gas share spikes → high spot prices → CNA, gas-heavy generators
   - Carbon intensity crossing thresholds → CCUS + nuclear attention

2. Transport for London tube line status (api.tfl.gov.uk)
   - Infrastructure stress / strike indicator
   - Feeds UK transport equity narrative (NATS, FirstGroup, Go-Ahead)

Output: uk_grid_transport.csv
Columns: domain, region_or_line, metric_name, value, unit, status,
captured_at

Sources: both endpoints no-key, live.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "uk_grid_transport.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
GRID_NATIONAL = "https://api.carbonintensity.org.uk/intensity"
GRID_MIX = "https://api.carbonintensity.org.uk/generation"
GRID_REGIONAL = "https://api.carbonintensity.org.uk/regional"
TFL_TUBE = "https://api.tfl.gov.uk/Line/Mode/tube/Status"


def _fetch(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"uk_grid_transport {url[-40:]}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []

    nat = _fetch(GRID_NATIONAL)
    if isinstance(nat, dict):
        items = nat.get("data") or []
        if items and isinstance(items, list):
            it = items[0]
            intensity = it.get("intensity") or {}
            rows.append({
                "domain": "grid_national",
                "region_or_line": "UK",
                "metric_name": "carbon_intensity_actual",
                "value": str(intensity.get("actual", "")),
                "unit": "gCO2_per_kWh",
                "status": intensity.get("index", ""),
            })
            rows.append({
                "domain": "grid_national",
                "region_or_line": "UK",
                "metric_name": "carbon_intensity_forecast",
                "value": str(intensity.get("forecast", "")),
                "unit": "gCO2_per_kWh",
                "status": intensity.get("index", ""),
            })

    mix = _fetch(GRID_MIX)
    if isinstance(mix, dict):
        data = mix.get("data") or {}
        for f in data.get("generationmix") or []:
            fuel = f.get("fuel", "")
            pct = f.get("perc", "")
            if not fuel:
                continue
            rows.append({
                "domain": "grid_mix_national",
                "region_or_line": "UK",
                "metric_name": f"pct_{fuel}",
                "value": str(pct),
                "unit": "percent",
                "status": "",
            })

    reg = _fetch(GRID_REGIONAL)
    if isinstance(reg, dict):
        items = reg.get("data") or []
        if items and isinstance(items, list):
            for region in items[0].get("regions") or []:
                short = (region.get("shortname") or "")[:24]
                intensity = region.get("intensity") or {}
                rows.append({
                    "domain": "grid_regional",
                    "region_or_line": short,
                    "metric_name": "carbon_intensity_forecast",
                    "value": str(intensity.get("forecast", "")),
                    "unit": "gCO2_per_kWh",
                    "status": intensity.get("index", ""),
                })
                for f in region.get("generationmix") or []:
                    fuel = f.get("fuel", "")
                    pct = f.get("perc", "")
                    if fuel in ("wind", "solar", "gas", "nuclear"):
                        rows.append({
                            "domain": "grid_regional_mix",
                            "region_or_line": short,
                            "metric_name": f"pct_{fuel}",
                            "value": str(pct),
                            "unit": "percent",
                            "status": "",
                        })

    tube = _fetch(TFL_TUBE)
    if isinstance(tube, list):
        for line in tube:
            name = line.get("name", "")
            statuses = line.get("lineStatuses") or []
            if not statuses:
                continue
            st = statuses[0]
            sev = st.get("statusSeverityDescription", "")
            sev_n = st.get("statusSeverity", "")
            rows.append({
                "domain": "tfl_tube",
                "region_or_line": name,
                "metric_name": "line_status",
                "value": str(sev_n),
                "unit": "severity_0_20",
                "status": sev,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"uk_grid_transport: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["domain", "region_or_line", "metric_name", "value",
                  "unit", "status", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    ci = next((r for r in rows
               if r["metric_name"] == "carbon_intensity_actual"), {})
    wind = next((r for r in rows if r["domain"] == "grid_mix_national"
                 and r["metric_name"] == "pct_wind"), {})
    gas = next((r for r in rows if r["domain"] == "grid_mix_national"
                and r["metric_name"] == "pct_gas"), {})
    disrupted = [r for r in rows if r["domain"] == "tfl_tube"
                 and r["status"] not in ("Good Service", "")]
    print(f"uk_grid_transport: {len(rows)} rows | "
          f"UK CI={ci.get('value','?')}gCO2/kWh ({ci.get('status','?')}) "
          f"wind={wind.get('value','?')}% gas={gas.get('value','?')}% | "
          f"tube disrupted={len(disrupted)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
