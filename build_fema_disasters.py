#!/usr/bin/env python3
"""build_fema_disasters.py — FEMA federal disaster declarations.

Declared disasters → rebuild trades. Hurricane → HD/LOW surge, POOL,
FBHS. Wildfire → EIX/PCG volatility, SCGLY reinsurers. Floods → farm
commodities, crop insurance. Multi-state fed emergencies → immediate
sector plays as states request aid.

Source: fema.gov/api/open/v2/DisasterDeclarationsSummaries (REST).
Output: fema_disasters.csv
Columns: declaration_date, state, county, incident_type,
         declaration_title, disaster_number, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fema_disasters.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = (
    "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
    "?$orderby=declarationDate%20desc&$top=400"
)


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fema: {e}")
        return []
    return data.get("DisasterDeclarationsSummaries") or []


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    seen = set()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items:
        key = (it.get("disasterNumber"), it.get("state"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "declaration_date": (it.get("declarationDate") or "")[:10],
            "state": it.get("state", "")[:2],
            "county": (it.get("designatedArea") or "")[:60],
            "incident_type": it.get("incidentType", "")[:40],
            "declaration_title": (it.get("declarationTitle") or "")[:120],
            "disaster_number": it.get("disasterNumber", ""),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r["declaration_date"], reverse=True)
    rows = rows[:200]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["declaration_date", "state", "county",
                        "incident_type", "declaration_title",
                        "disaster_number", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fema: {len(rows)} declarations | latest "
          f"{latest.get('declaration_date','?')} "
          f"{latest.get('state','?')} {latest.get('incident_type','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
