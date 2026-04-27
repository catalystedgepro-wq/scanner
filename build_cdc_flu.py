#!/usr/bin/env python3
"""build_cdc_flu.py — CDC FluView weekly surveillance (Socrata).

Flu severity → pharmacy demand (WBA, CVS, Rite Aid parent), antiviral
prescription (GILD Tamiflu, Xofluza → SHP), OTC symptom relief (P&G,
RB, J&J, CL). High flu season also drags airline yields (DAL, UAL,
AAL) from cancellations, boosts Clorox (CLX), Lysol (RB). Low flu =
weaker pharmacy/OTC, less ICU utilization.

Source: CDC FluView WHO/NREVSS clinical labs API (Socrata).
Output: cdc_flu.csv
Columns: year_week, region, total_specimens, percent_positive,
         total_a, total_b, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cdc_flu.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

BASE = "https://data.cdc.gov/resource/xxby-e4ae.json"


def fetch() -> list[dict]:
    params = {
        "$limit": "500",
        "$order": "year_week DESC",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"cdc_flu: {e}")
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items[:200]:
        rows.append({
            "year_week": it.get("year_week", ""),
            "region": it.get("region", "US"),
            "total_specimens": it.get("total_specimens", ""),
            "percent_positive": it.get("percent_positive", ""),
            "total_a": it.get("total_a", ""),
            "total_b": it.get("total_b", ""),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "year_week", "region", "total_specimens",
                "percent_positive", "total_a", "total_b", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"cdc_flu: {len(rows)} obs | latest {latest.get('year_week','?')} "
          f"pos%={latest.get('percent_positive','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
