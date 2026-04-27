#!/usr/bin/env python3
"""build_sec_arrangements.py — Canadian plan-of-arrangement M&A tape.

Canadian public companies use "plan of arrangement" as the primary
statutory merger mechanism (CBCA/BCBCA Sec 192). Canadian issuers
listed on US exchanges must file the arrangement circular or
announcement as a Form 6-K with the SEC. This is distinct from the
US M&A tape (S-4, PREM14A, etc.) and complements sec_merger_proxy
for cross-border deal flow.

Economic readthrough:
- 6-K with "plan of arrangement" keyword -> target issuer has
  agreed to a Canadian court-supervised M&A transaction.
- Typical arb spread: 3-8% at announcement, tightens to <1% at
  court approval, closes at record date.
- Dual-listed Canadian issuers (TSX + NYSE/Nasdaq) -> most visible
  to US investors; pure-TSX names still file 6-K if SEC-registered.
- Reverse arrangements -> going-private transactions, SPAC-merge
  equivalent for Canadian shell structures.

Source: SEC EDGAR full-text search
https://efts.sec.gov/LATEST/search-index
Query: q="plan of arrangement", forms=6-K, 45d window.

Output: sec_arrangements.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_arrangements.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

# Canadian M&A keyword phrases (boolean OR via EDGAR FTS)
QUERIES = [
    ("plan of arrangement", "plan_of_arrangement"),
    ("arrangement agreement", "arrangement_agreement"),
    ("court approval arrangement", "court_approval"),
]
FORMS = ["6-K", "6-K/A", "40-F", "40-F/A"]


def _fetch(q: str, form: str, d_from: str, d_to: str) -> dict:
    qs = urllib.parse.urlencode({
        "q": f'"{q}"',
        "dateRange": "custom",
        "startdt": d_from,
        "enddt": d_to,
        "forms": form,
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sec_arrangements: fetch {form}/{q[:20]} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=45)).isoformat()
    d_to = today.isoformat()

    rows: list[dict] = []
    for q, kind in QUERIES:
        for form in FORMS:
            j = _fetch(q, form, d_from, d_to)
            hits = j.get("hits", {}).get("hits", [])
            for h in hits[:80]:
                src = h.get("_source", {})
                ciks = src.get("ciks") or []
                names = src.get("display_names") or []
                filed = src.get("file_date", "")
                actual_form = src.get("form", form)
                adsh = src.get("adsh", "")
                biz = src.get("biz_locations") or []
                ticker = ""
                issuer = ""
                for n in names:
                    m = re.search(r"\(([A-Z\.\-]{1,6})\)", n)
                    if m and not ticker:
                        ticker = m.group(1)
                    if not issuer:
                        issuer = n.split("  (")[0][:60]
                rows.append({
                    "filed": filed,
                    "form": actual_form,
                    "kind": kind,
                    "ticker": ticker,
                    "issuer": issuer,
                    "location": (biz[0] if biz else "")[:40],
                    "ciks": "|".join(ciks[:2])[:50],
                    "accession": adsh[:25],
                })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_arrangements: no rows, keeping {OUT_CSV.name}")
        return

    seen = set()
    dedup = []
    for r in rows:
        k = r["accession"]
        if k and k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    rows = dedup

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "form", "kind", "ticker", "issuer",
                  "location", "ciks", "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind: dict[str, int] = {}
    by_form: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v
                   in sorted(by_kind.items(), key=lambda kv: -kv[1]))
    fb = " ".join(f"{k}={v}" for k, v
                   in sorted(by_form.items(), key=lambda kv: -kv[1]))
    with_t = sum(1 for r in rows if r["ticker"])
    top = [r for r in rows if r["ticker"]][:5]
    tb = " | ".join(f"{r['ticker']}:{r['kind']}" for r in top)
    print(f"sec_arrangements: {len(rows)} 45d ({with_t} tagged) | "
          f"{kb} | {fb} | active: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
