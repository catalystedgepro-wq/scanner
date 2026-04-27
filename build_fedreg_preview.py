#!/usr/bin/env python3
"""build_fedreg_preview.py — Federal Register public-inspection queue.

Pre-publication regulatory documents on public inspection TODAY — the
leading edge of federal_register.py which covers already-published
docs. Catches tomorrow's rules before they formally hit, buying 12–24h
of lead time on:
- FDA guidance (biotech)
- FAA ADs (airlines, BA, LMT, NOC)
- CFPB fine/rule (banks)
- EPA rules (XLE, XLB, chemicals)
- NHTSA recalls (autos)
- EO filed-but-not-effective (presidential actions)

Source: federalregister.gov/api/v1/public-inspection-documents (free).
Output: fedreg_preview.csv
Columns: doc_number, title, type, agency, filing_date, filed_at,
         url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fedreg_preview.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www.federalregister.gov/api/v1/"
       "public-inspection-documents/current.json")


def _agency_names(raw) -> str:
    if not isinstance(raw, list):
        return ""
    names = []
    for a in raw:
        if isinstance(a, dict):
            name = a.get("name") or a.get("raw_name") or ""
            if name:
                names.append(str(name)[:40])
    return "|".join(names)[:80]


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fedreg_preview: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fedreg_preview: keeping existing {OUT_CSV.name}")
        return

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fedreg_preview: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in results[:400]:
        if not isinstance(item, dict):
            continue
        rows.append({
            "doc_number": str(item.get("document_number") or "")[:20],
            "title": str(item.get("title") or "")[:200],
            "type": str(item.get("type") or "")[:24],
            "agency": _agency_names(item.get("agencies")),
            "filing_date": str(item.get("filing_date") or "")[:10],
            "filed_at": str(item.get("filed_at") or "")[:19],
            "url": str(item.get("pdf_url")
                       or item.get("html_url") or "")[:220],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fedreg_preview: 0 rows, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed_at"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["doc_number", "title", "type", "agency", "filing_date",
                  "filed_at", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    types: dict[str, int] = {}
    ag_hist: dict[str, int] = {}
    for r in rows:
        t = r["type"] or "Unknown"
        types[t] = types.get(t, 0) + 1
        for a in (r["agency"] or "").split("|"):
            if a:
                ag_hist[a] = ag_hist.get(a, 0) + 1
    t_str = " ".join(f"{k}={v}" for k, v in
                     sorted(types.items(), key=lambda kv: -kv[1])[:4])
    top_ag = sorted(ag_hist.items(), key=lambda kv: -kv[1])[:3]
    a_str = " ".join(f"{k}={v}" for k, v in top_ag)
    print(f"fedreg_preview: {len(rows)} docs on public inspection | "
          f"{t_str} | top agencies: {a_str} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
