#!/usr/bin/env python3
"""build_ofac_sanctions.py — OFAC SDN sanctions list updates.

Sanctions additions = massive catalyst. Russia/China/Iran entity
sanctions → flag ticker exposure. Chinese tech firm entity list →
AAPL/NVDA export-restriction risk. Crypto address sanctions → COIN
compliance cost, TORN/TOR project dead. Oil company sanctions →
XOM/CVX supply chain rerouting, shipping stocks benefit (SBLK, GOGL).

Source: sanctionslist.ofac.treas.gov/Home/ConsolidatedList (XML).
Output: ofac_sanctions.csv
Columns: sdn_id, entity_name, entity_type, program, nationality,
         list_date, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ofac_sanctions.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# OFAC recent actions HTML scrape (public, no auth).
URL = "https://ofac.treasury.gov/recent-actions"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"ofac: {e}")
        return []
    # Parse /recent-actions/YYYYMMDD-XX blocks.
    items: list[dict] = []
    import re as _re
    pat = _re.compile(
        r'<a[^>]+href="(/recent-actions/(\d{8})[^"]*)"[^>]*>([^<]{4,200})</a>',
        _re.IGNORECASE,
    )
    seen = set()
    for m in pat.finditer(html):
        href, date8, title = m.group(1), m.group(2), m.group(3).strip()
        key = href
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": date8,
            "title": title,
            "type": "action",
            "program": "",
            "nationality": "",
            "releaseDate": f"{date8[:4]}-{date8[4:6]}-{date8[6:8]}",
            "url": f"https://ofac.treasury.gov{href}",
        })
    return items


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items[:200]:
        rows.append({
            "sdn_id": it.get("id", "") or it.get("publicationId", ""),
            "entity_name": (it.get("name") or it.get("title", ""))[:140],
            "entity_type": it.get("type", ""),
            "program": it.get("program", "") or it.get("sanctionsType", ""),
            "nationality": it.get("nationality", "") or it.get("country", ""),
            "list_date": (
                it.get("releaseDate") or it.get("publicationDate", "")
            )[:10],
            "url": it.get("url", "") or it.get("link", ""),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r.get("list_date") or "", reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "sdn_id", "entity_name", "entity_type",
                "program", "nationality", "list_date",
                "url", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"ofac: {len(rows)} entries | latest "
          f"{latest.get('list_date','?')} {latest.get('entity_name','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
