#!/usr/bin/env python3
"""build_sec_audit.py — SEC audit-quality / financial-reliability tape.

7 audit-risk 8-K kinds — textbook short-interest & distress
signals that precede delisting or bankruptcy:

- going_concern — auditor expressed doubt about entity's ability
  to continue operations. Academic (Carcello-Neal 2000): 43%
  one-year bankruptcy rate after first going-concern opinion.
- restatement — prior financials restated. Dechow-Dichev 2002:
  -10% CAR at announcement; -30% cumulative 12mo.
- non_reliance — Item 4.02 of 8-K ("Non-Reliance on Previously
  Issued Financial Statements"). Among strongest short signals;
  avg -12% day-one.
- audit_opinion — any reference. Often routine but reveal filing
  discussions.
- substantial_doubt — statutory phrase auditors must use when
  raising going-concern. Sibling of going_concern kind.
- valuation_allowance — DTA writedown. Forward-earnings pressure
  signal (company no longer expects to use NOLs).
- adverse_opinion — strongest negative auditor conclusion; rare
  but fatal (NYSE/Nasdaq delisting trigger).

Economic readthrough:
- Non_reliance + restatement + going_concern cluster -> short
  conviction basket; often feeds sec_distress::bankruptcy.
- Valuation_allowance without earnings crisis -> broader
  reflection of subdued tax-guidance outlook.

Source: efts.sec.gov/LATEST/search-index
Output: sec_audit.csv

Lookback: 60 days (audit cycles are quarterly, extended to catch).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_audit.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "going_concern": '"going concern"',
    "restatement": '"restatement"',
    "non_reliance": '"non-reliance"',
    "audit_opinion": '"audit opinion"',
    "substantial_doubt": '"substantial doubt"',
    "valuation_allowance": '"valuation allowance"',
    "adverse_opinion": '"adverse opinion"',
}

LIMITS = {
    "going_concern": 150,
    "restatement": 130,
    "non_reliance": 100,
    "audit_opinion": 80,
    "substantial_doubt": 80,
    "valuation_allowance": 80,
    "adverse_opinion": 60,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=60)).isoformat()
    d_to = today.isoformat()
    qq = urllib.parse.quote(query)
    forms = urllib.parse.quote("8-K")
    url = (f"https://efts.sec.gov/LATEST/search-index?q={qq}"
           f"&dateRange=custom&startdt={d_from}&enddt={d_to}"
           f"&forms={forms}&from=0&size={min(limit, 100)}")
    out: list[dict] = []
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"sec_audit: {kind} fetch failed: {e}")
        return out
    for h in d.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        names_list = src.get("display_names") or []
        names_str = " ".join(names_list)
        m = TICKER_RE.search(names_str)
        out.append({
            "kind": kind,
            "ticker": m.group(1) if m else "",
            "name": (names_list[0] if names_list else "")[:80],
            "form": src.get("form", ""),
            "filed": src.get("file_date", ""),
            "accession": h.get("_id", ""),
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for kind, q in QUERIES.items():
        batch = _fetch(kind, q, LIMITS.get(kind, 100))
        counts[kind] = len(batch)
        rows.extend(batch)
        time.sleep(0.4)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_audit: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["filed"], r["kind"]), reverse=True)
    fieldnames = ["kind", "ticker", "name", "form", "filed",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:15]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_audit: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
