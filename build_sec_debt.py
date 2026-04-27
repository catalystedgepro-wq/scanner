#!/usr/bin/env python3
"""build_sec_debt.py — EDGAR debt-market 8-K tape.

Bond issuance, refinancing, amendment, and credit-facility 8-Ks
are filed under Item 2.03 (Creation of a Direct Financial
Obligation) or Item 1.01 (Entry into a Material Definitive
Agreement). Key signals:

- supplemental indenture: new bond tranche off existing shelf
- credit agreement: new or amended revolver/term loan
- senior notes offering: high-yield or investment-grade issuance
- note purchase agreement: private placement of debt
- covenant waiver: distress signal, often precedes amend-extend
- debt refinancing: maturity extension, rate reset

Economic readthrough:
- Spike in indenture/senior notes = debt market open, credit risk-on
- Covenant waivers cluster = credit stress in a sector
- Rate-lock / make-whole redemption = refi opportunistic
- Investment-grade issuance -> M&A + buyback funding

Source: SEC EDGAR full-text search 30d.
Output: sec_debt.csv
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
OUT_CSV = ROOT / "sec_debt.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES = [
    ("supplemental indenture", "indenture_supplement"),
    ("senior notes offering", "senior_notes_issuance"),
    ("credit agreement", "credit_agreement"),
    ("note purchase agreement", "note_purchase"),
    ("covenant waiver", "covenant_waiver"),
    ("debt refinancing", "debt_refi"),
]


def _fetch(q: str, d_from: str, d_to: str) -> dict:
    qs = urllib.parse.urlencode({
        "q": f'"{q}"',
        "dateRange": "custom",
        "startdt": d_from,
        "enddt": d_to,
        "forms": "8-K",
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sec_debt: fetch {q[:20]} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=30)).isoformat()
    d_to = today.isoformat()

    rows: list[dict] = []
    for q, kind in QUERIES:
        j = _fetch(q, d_from, d_to)
        hits = j.get("hits", {}).get("hits", [])
        for h in hits[:80]:
            src = h.get("_source", {})
            ciks = src.get("ciks") or []
            names = src.get("display_names") or []
            filed = src.get("file_date", "")
            adsh = src.get("adsh", "")
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
                "kind": kind,
                "ticker": ticker,
                "issuer": issuer,
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_debt: no rows, keeping {OUT_CSV.name}")
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
    fieldnames = ["filed", "kind", "ticker", "issuer",
                  "ciks", "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v
                   in sorted(by_kind.items(), key=lambda kv: -kv[1]))
    with_t = sum(1 for r in rows if r["ticker"])
    stress_rows = [r for r in rows
                    if r["kind"] == "covenant_waiver" and r["ticker"]]
    sb = " | ".join(f"{r['ticker']}" for r in stress_rows[:5])
    print(f"sec_debt: {len(rows)} 30d ({with_t} tagged) | {kb} | "
          f"stress: [{sb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
