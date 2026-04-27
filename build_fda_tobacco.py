#!/usr/bin/env python3
"""build_fda_tobacco.py — openFDA tobacco problem reports.

Consumer-reported tobacco product problems. Rising reports of
health issues linked to e-cigarettes / vapes / cigars signal:
- FDA enforcement risk (MO, BTI, PM, IMBBY)
- PMTA denial risk for smaller vape makers
- Regulatory/legal tailwinds for nicotine-replacement (HLNAF, HALO)
- ESG/health litigation pipeline (Juul-style cases)

Source: openFDA /tobacco/problem.json (free, no key).

Output: fda_tobacco.csv
Columns: report_id, date_submitted, nonuser_affected, health_problems,
         product_problems, product_types, num_products,
         num_health_problems, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_tobacco.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.fda.gov/tobacco/problem.json"


def main() -> None:
    today = dt.date.today()
    start = today - dt.timedelta(days=730)
    qs = urllib.parse.urlencode({
        "search": f"date_submitted:[{start.strftime('%Y%m%d')} TO "
                  f"{today.strftime('%Y%m%d')}]",
        "limit": 200,
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fda_tobacco: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_tobacco: keeping existing {OUT_CSV.name}")
        return

    results = d.get("results") or []
    if not results:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_tobacco: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        health = "|".join((item.get("reported_health_problems") or []))[:120]
        prob = "|".join((item.get("reported_product_problems") or []))[:120]
        types = "|".join((item.get("tobacco_products") or []))[:80]
        rows.append({
            "report_id": str(item.get("report_id") or "")[:12],
            "date_submitted": str(item.get("date_submitted") or "")[:10],
            "nonuser_affected": str(item.get("nonuser_affected") or "")[:6],
            "health_problems": health,
            "product_problems": prob,
            "product_types": types,
            "num_products": str(item.get("number_tobacco_products") or 0),
            "num_health_problems": str(item.get("number_health_problems") or 0),
            "captured_at": now,
        })

    rows.sort(key=lambda r: r["date_submitted"], reverse=True)

    fieldnames = ["report_id", "date_submitted", "nonuser_affected",
                  "health_problems", "product_problems", "product_types",
                  "num_products", "num_health_problems", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    deaths = sum(1 for r in rows if "Death" in r["health_problems"])
    nonuser = sum(1 for r in rows if r["nonuser_affected"] == "Yes")
    print(f"fda_tobacco: {len(rows)} reports (2-y) | deaths={deaths} "
          f"nonuser_affected={nonuser} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
