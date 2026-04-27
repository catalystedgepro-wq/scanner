#!/usr/bin/env python3
"""build_federal_register.py — Federal Register regulations (daily).

New rules = industry catalysts. FDA new regs hit biotech, FAA regs
hit BA/airlines, FCC regs hit TMUS/VZ/T, EPA regs hit XLE/XLB, NHTSA
regs hit autos, CFPB regs hit banks. Executive orders flagged by
agency — presidential proclamations move energy (coal, gas), trade
(tariffs), immigration (H1B-dependent tech).

Source: federalregister.gov/api/v1 (public, no key).
Output: federal_register.csv
Columns: doc_number, title, type, agency, pub_date, abstract, url,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "federal_register.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

BASE = "https://www.federalregister.gov/api/v1/documents.json"


def fetch() -> list[dict]:
    today = dt.date.today()
    start = (today - dt.timedelta(days=7)).isoformat()
    params = [
        ("per_page", "100"),
        ("order", "newest"),
        ("fields[]", "document_number"),
        ("fields[]", "title"),
        ("fields[]", "type"),
        ("fields[]", "agencies"),
        ("fields[]", "publication_date"),
        ("fields[]", "abstract"),
        ("fields[]", "html_url"),
        ("conditions[publication_date][gte]", start),
        ("conditions[publication_date][lte]", today.isoformat()),
    ]
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"federal_register: {e}")
        return []
    return data.get("results", []) or []


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items:
        ags = it.get("agencies") or []
        ag_names = ", ".join(a.get("raw_name") or a.get("name", "")
                             for a in ags if isinstance(a, dict))[:120]
        rows.append({
            "doc_number": it.get("document_number", ""),
            "title": (it.get("title") or "")[:180],
            "type": it.get("type", ""),
            "agency": ag_names,
            "pub_date": it.get("publication_date", ""),
            "abstract": (it.get("abstract") or "")[:200],
            "url": it.get("html_url", ""),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "doc_number", "title", "type", "agency",
                "pub_date", "abstract", "url", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"federal_register: {len(rows)} docs | latest "
          f"{latest.get('pub_date','?')} {latest.get('type','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
