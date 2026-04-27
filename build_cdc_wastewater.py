#!/usr/bin/env python3
"""build_cdc_wastewater.py — Wastewater viral surveillance (COVID, flu, RSV).

Wastewater levels lead clinical cases by 2 weeks. Rising COVID/flu →
retail pharmacy traffic (CVS, WBA), at-home tests (LH, DGX, BDX, QDEL),
Paxlovid/Tamiflu sales (PFE, GILD), drug stores. Declining → travel/event
stocks (LYV, MAR, RCL) positive setup.

Source: data.cdc.gov Socrata JSON (free, no key required).
Output: cdc_wastewater.csv
Columns: week_end, metric, jurisdiction, level, trend_2wk, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cdc_wastewater.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# National wastewater surveillance (NWSS) API
ENDPOINT = "https://data.cdc.gov/resource/2ew6-ywp6.json?$limit=500&$order=date_end%20DESC"


def fetch(url: str) -> list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"cdc_ww: {e}")
        return None


def main() -> None:
    data = fetch(ENDPOINT) or []
    rows: list[dict] = []
    if isinstance(data, list):
        for rec in data[:400]:
            rows.append({
                "week_end": rec.get("date_end") or "",
                "metric": "SARS-CoV-2",
                "jurisdiction": rec.get("reporting_jurisdiction") or rec.get("county_names") or "",
                "level": rec.get("percentile") or "",
                "trend_2wk": rec.get("ptc_15d") or "",
            })
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week_end", "metric", "jurisdiction", "level",
                "trend_2wk", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"cdc_wastewater: {len(rows)} obs | latest {latest.get('week_end','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
