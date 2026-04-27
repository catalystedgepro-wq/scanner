#!/usr/bin/env python3
"""build_cpsc_recalls.py — CPSC consumer product recalls.

Consumer product recalls = brand reputation hits. Sears/Target recalls
→ retailer margin impact. Toy recalls → MAT, HAS. Appliance recalls →
WHR, HELE. Stroller/car seat recalls → DORM, GRPN-owned. Furniture
recalls (IKEA-style tip-overs) → WSM, RH, W.

Source: saferproducts.gov / cpsc.gov recalls API.
Output: cpsc_recalls.csv
Columns: recall_id, recall_number, title, description, remedy, manufacturer,
         hazards, recall_date, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cpsc_recalls.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# CPSC Open Data API
URL = "https://www.saferproducts.gov/RestWebServices/Recall?format=json"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"cpsc: {e}")
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    items = fetch()
    # Keep last 180 days
    cutoff = (dt.date.today() - dt.timedelta(days=180)).isoformat()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items:
        rd = it.get("RecallDate", "") or ""
        if rd and rd[:10] < cutoff:
            continue
        mfrs = it.get("Manufacturers") or []
        mfr_names = "; ".join(
            m.get("Name", "") for m in mfrs if isinstance(m, dict)
        )[:120]
        hazards = it.get("Hazards") or []
        hazard_names = "; ".join(
            h.get("Name", "") for h in hazards if isinstance(h, dict)
        )[:120]
        rows.append({
            "recall_id": it.get("RecallID", ""),
            "recall_number": it.get("RecallNumber", ""),
            "title": (it.get("Title") or "")[:140],
            "description": (it.get("Description") or "")[:200],
            "remedy": (it.get("RemedyOptions") and
                       it.get("RemedyOptions")[0].get("Option", "") or "")[:60]
                      if it.get("RemedyOptions") else "",
            "manufacturer": mfr_names,
            "hazards": hazard_names,
            "recall_date": rd[:10],
            "url": it.get("URL", ""),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r.get("recall_date") or "", reverse=True)
    rows = rows[:500]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "recall_id", "recall_number", "title", "description",
                "remedy", "manufacturer", "hazards",
                "recall_date", "url", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"cpsc: {len(rows)} recalls | latest "
          f"{latest.get('recall_date','?')} {latest.get('title','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
