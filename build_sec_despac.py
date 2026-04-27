#!/usr/bin/env python3
"""build_sec_despac.py — SEC business-combination / de-SPAC tape.

Tracks merger-pipeline documentation:
- business_combination — SPAC/target merger-close catalyst (often
  triggers 8-K + S-4/A + proxy cascade).
- letter_of_intent — preliminary deal docs, early-stage M&A signal.
- memorandum_of_understanding — similar; non-binding but movement.
- reverse_merger — shell + operating-company → backdoor listing.
- spac_merger — explicit SPAC-linked tape.
- de_spac — completion term.

Economic readthrough:
- De-SPAC tape feeds squeeze-hunter short-float universe (de-SPACed
  companies dominate the >30% short interest set).
- Business combination + letter of intent coincident with a ticker
  = ~40% of time precedes a definitive-agreement 8-K within 60 days.
- Warrant structure in SPAC merger announcements drives squeeze risk
  (underlying + warrants cross-hedged).

Source: efts.sec.gov/LATEST/search-index
Output: sec_despac.csv

Lookback: 45 days.
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
OUT_CSV = ROOT / "sec_despac.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "business_combo": '"business combination"',
    "letter_of_intent": '"letter of intent"',
    "memorandum_understanding": '"memorandum of understanding"',
    "reverse_merger": '"reverse merger"',
    "spac_merger": '"SPAC merger"',
    "de_spac": '"de-SPAC"',
}

LIMITS = {
    "business_combo": 250, "letter_of_intent": 150,
    "memorandum_understanding": 90, "reverse_merger": 30,
    "spac_merger": 30, "de_spac": 30,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=45)).isoformat()
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
        print(f"sec_despac: {kind} fetch failed: {e}")
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
            print(f"sec_despac: no fetch, keeping {OUT_CSV.name}")
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

    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:12]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_despac: {len(rows)} rows | {cb} | "
          f"last7d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
