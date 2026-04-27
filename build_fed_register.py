#!/usr/bin/env python3
"""build_fed_register.py — U.S. Federal Register rulemaking feed.

Every market-moving federal rule, proposed rule, and agency notice
is published daily to the Federal Register. Signal: regulatory action
precedes sector-ETF rotation by days to weeks.

Economic readthrough:
- FDA rule -> biotech sector (XBI, IBB) binary events.
- FCC rule -> spectrum auction / carrier (T, VZ, TMUS) flow.
- FAA scheduling -> airline (AAL, UAL, LUV) capacity shock.
- BLM oil/gas lease -> E&P (XOM, CVX, OXY) reserves.
- Treasury/IRS -> tax arbitrage (PE, financials).
- DoE / FERC -> utility (NEE, DUK, SO) rate cases.
- EPA rule -> refiners (VLO, MPC, PSX) and coal (BTU, ARCH).
- USDA -> ag supply / crop insurance (ADM, BG, MOS).

Source: https://www.federalregister.gov/api/v1/documents.json

Output: fed_register.csv — last 14 days, market-relevant agencies.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fed_register.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

AGENCY_KINDS: dict[str, str] = {
    "food and drug administration": "fda",
    "health and human services": "hhs",
    "centers for medicare": "cms",
    "federal communications commission": "fcc",
    "federal aviation administration": "faa",
    "federal trade commission": "ftc",
    "securities and exchange commission": "sec",
    "commodity futures trading commission": "cftc",
    "environmental protection agency": "epa",
    "energy regulatory commission": "ferc",
    "department of energy": "doe",
    "department of the treasury": "treasury",
    "internal revenue service": "irs",
    "department of agriculture": "usda",
    "department of labor": "dol",
    "department of transportation": "dot",
    "national highway traffic safety": "nhtsa",
    "bureau of land management": "blm",
    "occupational safety and health": "osha",
    "defense contract management": "defense",
    "department of defense": "defense",
    "federal reserve": "fed",
    "federal deposit insurance": "fdic",
    "office of the comptroller": "occ",
    "consumer financial protection": "cfpb",
    "federal housing finance agency": "fhfa",
    "national labor relations": "nlrb",
    "pension benefit guaranty": "pbgc",
}


def _agency_kind(agencies: list[dict]) -> str:
    for a in agencies:
        name = (a.get("raw_name") or a.get("name") or "").lower()
        for kw, k in AGENCY_KINDS.items():
            if kw in name:
                return k
    return "other"


def _fetch(page: int = 1, per_page: int = 1000) -> list[dict]:
    d_from = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    d_to = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    qs = urllib.parse.urlencode({
        "order": "newest",
        "per_page": per_page,
        "page": page,
        "conditions[publication_date][gte]": d_from,
        "conditions[publication_date][lte]": d_to,
    }, safe="[]")
    url = f"https://www.federalregister.gov/api/v1/documents.json?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read()).get("results", [])
    except Exception as e:
        print(f"fed_register: fetch failed: {e}")
        return []


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    results = _fetch(page=1, per_page=1000)

    rows: list[dict] = []
    for r in results:
        agencies = r.get("agencies") or []
        kind = _agency_kind(agencies)
        if kind == "other":
            continue
        ag_name = (agencies[0].get("raw_name") or agencies[0].get("name") or
                   "")[:50] if agencies else ""
        rows.append({
            "date": r.get("publication_date", ""),
            "agency_kind": kind,
            "agency": ag_name,
            "doc_type": (r.get("type") or "")[:30],
            "title": (r.get("title") or "")[:180],
            "abstract": (r.get("abstract") or "")[:200],
            "doc_num": r.get("document_number", ""),
            "url": r.get("html_url") or r.get("pdf_url") or "",
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fed_register: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["date"], r["agency_kind"]), reverse=True)
    fieldnames = ["date", "agency_kind", "agency", "doc_type",
                  "title", "abstract", "doc_num", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["agency_kind"]] = kinds.get(r["agency_kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(),
                                                 key=lambda x: -x[1])[:8])
    rules = [r for r in rows if "Rule" in r["doc_type"]]
    print(f"fed_register: {len(rows)} rows ({len(rules)} rules) | "
          f"{kb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
