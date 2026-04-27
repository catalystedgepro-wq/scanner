#!/usr/bin/env python3
"""build_fda_recalls.py — FDA enforcement recalls (openFDA API).

Recalls drop the sponsor in 24h (sometimes 30%+ on a Class I). Food
recalls hit CAG, HAIN, KHC, K, GIS. Device recalls hit BSX, MDT, SYK,
ABT, BDX, PHG. Drug recalls hit the sponsor + supplier (TEVA, VTRS,
PFE, CTLT, WBA).

Source: api.fda.gov/food/enforcement.json, /drug, /device.
Output: fda_recalls.csv
Columns: recall_id, classification, recall_type, firm, product, reason,
         recall_initiation_date, status, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_recalls.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

ENDPOINTS = [
    ("drug", "https://api.fda.gov/drug/enforcement.json"),
    ("food", "https://api.fda.gov/food/enforcement.json"),
    ("device", "https://api.fda.gov/device/enforcement.json"),
]


def fetch(kind: str, base: str) -> list[tuple[str, dict]]:
    end = dt.date.today()
    start = end - dt.timedelta(days=120)
    url = (
        f"{base}?search=recall_initiation_date:"
        f"[{start.strftime('%Y%m%d')}+TO+{end.strftime('%Y%m%d')}]"
        f"&limit=100"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"fda_recalls {kind}: {e}")
        return []
    return [(kind, it) for it in data.get("results", [])]


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for kind, base in ENDPOINTS:
        for _, it in fetch(kind, base):
            d = it.get("recall_initiation_date", "")
            date_iso = (
                f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
            )
            rows.append({
                "recall_id": it.get("recall_number") or it.get("event_id", ""),
                "classification": it.get("classification", ""),
                "recall_type": kind,
                "firm": (it.get("recalling_firm") or "")[:80],
                "product": (it.get("product_description") or "")[:140],
                "reason": (it.get("reason_for_recall") or "")[:140],
                "recall_initiation_date": date_iso,
                "status": it.get("status", ""),
                "captured_at": now,
            })
    rows.sort(key=lambda r: r["recall_initiation_date"], reverse=True)
    rows = rows[:300]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "recall_id", "classification", "recall_type",
                "firm", "product", "reason",
                "recall_initiation_date", "status", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fda_recalls: {len(rows)} recalls | latest "
          f"{latest.get('recall_initiation_date','?')} "
          f"{latest.get('firm','?')[:30]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
