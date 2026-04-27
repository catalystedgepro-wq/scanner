#!/usr/bin/env python3
"""build_sec_divest.py — SEC sell-side / strategic-alternatives tape.

6 divestiture / sell-side 8-K kinds:

- divestiture — outright business/segment sale (buy-side M&A flip).
- asset_sale — operational asset disposition.
- carve_out — minority IPO / pre-spin structure.
- strategic_alternatives — "exploring strategic alternatives"
  signal. Equity Research playbook: +3-5% day-one, but deals fail
  ~50% of the time. Mosaic of sec_despac::lett + sec_whistleblower.
- strategic_review — formal board review. Higher commitment
  vs strategic_alternatives (formal mandate).
- superior_proposal — topping bid. Strong signal of competitive
  auction; average +8-12% from original deal value.

Economic readthrough:
- Strategic_alternatives + strategic_review cluster -> put on
  conviction-watch list (often resolves in 3-9 months).
- Superior_proposal cluster -> arb basket (long target, short
  acquirer) plays.
- Carve_out + IPO cluster -> pre-spin optionality window (SCGLY/
  KVUE-style parent-vs-child divergence).

Source: efts.sec.gov/LATEST/search-index
Output: sec_divest.csv

Lookback: 60 days.
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
OUT_CSV = ROOT / "sec_divest.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "divestiture": '"divestiture"',
    "asset_sale": '"asset sale"',
    "carve_out": '"carve-out"',
    "strategic_alternatives": '"strategic alternatives"',
    "strategic_review": '"strategic review"',
    "superior_proposal": '"superior proposal"',
}

LIMITS = {
    "divestiture": 200,
    "asset_sale": 200,
    "carve_out": 80,
    "strategic_alternatives": 130,
    "strategic_review": 70,
    "superior_proposal": 90,
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
        print(f"sec_divest: {kind} fetch failed: {e}")
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
            print(f"sec_divest: no fetch, keeping {OUT_CSV.name}")
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
    print(f"sec_divest: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
