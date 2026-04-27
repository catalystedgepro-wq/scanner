#!/usr/bin/env python3
"""build_fda_drug_ae.py — openFDA drug adverse event aggregate.

Top drugs by FAERS adverse event count in the last 2 years.
High-volume spikes are an early warning for:
- Black box label additions / REMS risk (LLY, PFE, MRK, ABBV)
- Class-action lawsuits (GSK, BMY)
- M&A target repricing when an acquired franchise has AE trend
- Regulatory intervention / marketing withdrawals

Signal: compare monthly AE counts vs trailing 12-mo baseline.

Source: openFDA /drug/event.json (free, no key, rate-limited).

Output: fda_drug_ae.csv
Columns: generic_name, ae_count_2y, rank, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_drug_ae.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.fda.gov/drug/event.json"


def main() -> None:
    today = dt.date.today()
    start = today - dt.timedelta(days=730)
    qs = urllib.parse.urlencode({
        "search": f"receivedate:[{start.strftime('%Y%m%d')} TO "
                  f"{today.strftime('%Y%m%d')}]",
        "count": "patient.drug.openfda.generic_name.exact",
        "limit": 100,
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fda_drug_ae: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_drug_ae: keeping existing {OUT_CSV.name}")
        return

    results = d.get("results") or []
    if not results:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_drug_ae: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    for i, item in enumerate(results, 1):
        if not isinstance(item, dict):
            continue
        rows.append({
            "generic_name": str(item.get("term") or "")[:60],
            "ae_count_2y": str(int(item.get("count") or 0)),
            "rank": str(i),
            "captured_at": now,
        })

    fieldnames = ["generic_name", "ae_count_2y", "rank", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top = rows[0] if rows else {}
    print(f"fda_drug_ae: {len(rows)} drugs (2-y FAERS) | top: "
          f"{top.get('generic_name', '?')}={top.get('ae_count_2y', '?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
