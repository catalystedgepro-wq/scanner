#!/usr/bin/env python3
"""build_fda_enforcement.py — FDA drug/device/food recall enforcement actions.

Recalls are material catalysts for pharma (CRL class I = equity at risk),
medical devices (Boston Scientific BSX, Medtronic MDT), and food
(Conagra CAG, Kellogg K). Class I recall = "reasonable probability of
serious adverse health consequences or death."

Trade uses:
- Class I drug recall attributed to a public co: initial -5% to -15%
  move if sole-source, fade after 5 days if generic/secondary supply.
- Mass recall clusters (same firm across multiple products): supply
  chain contamination — short to cover.
- Device Class I recall > 50k units: catalyst for competitor share
  gain (ISRG vs INTU, ABT vs DXCM).
- Food recall in leafy greens/beef: grocer revenue hit (KR/SFM), lift
  protein peers (TSN if listeria, PPC if salmonella).

Source: api.fda.gov/{drug,device,food}/enforcement.json. Public, no key
required (1k req/day unauthenticated). OpenFDA is updated weekly.

Output: fda_enforcement.csv
Columns: report_date, category, classification, product_type, firm,
         state, reason, voluntary, product_description, status,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_enforcement.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.fda.gov/{category}/enforcement.json"

CATEGORIES = ("drug", "device", "food")
LIMIT = 200  # Max OpenFDA allows without API key.


def fda_fetch(category: str, since: str) -> list[dict]:
    """Returns recent enforcement records for the category since YYYYMMDD."""
    today = dt.date.today().strftime("%Y%m%d")
    params = {
        "search": f"report_date:[{since}+TO+{today}]",
        "limit": str(LIMIT),
        "sort": "report_date:desc",
    }
    # OpenFDA uses + as literal, don't url-encode search.
    qs = "&".join([
        f"search={params['search']}",
        f"limit={params['limit']}",
        f"sort={params['sort']}",
    ])
    url = BASE.format(category=category) + "?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fda_enforcement {category}: {e}")
        return []
    return payload.get("results", []) or []


def main() -> None:
    # Last 90 days.
    since = (dt.date.today() - dt.timedelta(days=90)).strftime("%Y%m%d")
    rows: list[dict] = []
    for cat in CATEGORIES:
        for rec in fda_fetch(cat, since):
            rows.append({
                "report_date": rec.get("report_date", ""),
                "category": cat,
                "classification": rec.get("classification", ""),
                "product_type": rec.get("product_type", ""),
                "firm": rec.get("recalling_firm", "")[:120],
                "state": rec.get("state", ""),
                "reason": rec.get("reason_for_recall", "")[:240],
                "voluntary": rec.get("voluntary_mandated", ""),
                "product_description": rec.get("product_description", "")[:240],
                "status": rec.get("status", ""),
            })
    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"fda_enforcement: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    rows.sort(key=lambda r: (r["report_date"], r["category"]), reverse=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["report_date", "category", "classification",
                        "product_type", "firm", "state", "reason",
                        "voluntary", "product_description", "status",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    # Class I severity tally.
    class_i = [r for r in rows if r["classification"] == "Class I"]
    latest = rows[0] if rows else {}
    print(f"fda_enforcement: {len(rows)} recalls 90d "
          f"({len({r['category'] for r in rows})} categories, "
          f"{len(class_i)} Class I) | latest {latest.get('report_date','?')} "
          f"{latest.get('category','')} {latest.get('firm','')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
