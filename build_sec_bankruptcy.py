#!/usr/bin/env python3
"""build_sec_bankruptcy.py — SEC Form 8-K Item 1.03 bankruptcy filings.

When a public company files Chapter 7/11/15, it MUST file an 8-K with
Item 1.03 "Bankruptcy or Receivership" disclosure. Direct catalyst — stock
typically gets "Q" suffix and drops 50-90%.

Uses EDGAR full-text search (efts.sec.gov). 90-day lookback.

Output: sec_bankruptcy.csv
Columns: filed_at, ticker, company, cik, url, captured_at
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
OUT_CSV = ROOT / "sec_bankruptcy.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
LOOKBACK_DAYS = 90
HITS_PER_PAGE = 100
MAX_PAGES = 3

TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,\s*[A-Z0-9.\-]+)*\)\s*\(CIK")
CIK_RE = re.compile(r"CIK\s*(\d+)")


def efts_search(start: str, end: str, page_from: int = 0) -> dict:
    params = {
        "q": '"Item 1.03" "bankruptcy"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "forms": "8-K",
        "hits": str(HITS_PER_PAGE),
        "from": str(page_from),
    }
    url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def extract(display_names: list[str]) -> tuple[str, str, str]:
    if not display_names:
        return "", "", ""
    first = display_names[0]
    ticker = ""
    tm = TICKER_RE.search(first)
    if tm:
        ticker = tm.group(1).upper()
    cik = ""
    cm = CIK_RE.search(first)
    if cm:
        cik = cm.group(1)
    company = first.split("  (")[0].strip()
    return ticker, cik, company


def build_url(adsh: str, cik: str) -> str:
    if not cik or not adsh:
        return ""
    adsh_clean = adsh.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh_clean}/{adsh}-index.htm"


def main() -> int:
    end = dt.date.today()
    start = end - dt.timedelta(days=LOOKBACK_DAYS)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    rows: list[dict] = []
    seen_adsh: set[str] = set()
    page_from = 0
    for _ in range(MAX_PAGES):
        try:
            data = efts_search(start.isoformat(), end.isoformat(), page_from)
        except Exception as e:
            print(f"sec_bankruptcy: {e}")
            break
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h.get("_source", {})
            adsh = src.get("adsh", "")
            if not adsh or adsh in seen_adsh:
                continue
            seen_adsh.add(adsh)
            ticker, cik, company = extract(src.get("display_names", []))
            rows.append({
                "filed_at": src.get("file_date", ""),
                "ticker": ticker,
                "company": company[:120],
                "cik": cik,
                "url": build_url(adsh, cik),
                "captured_at": now,
            })
        page_from += HITS_PER_PAGE
        if len(hits) < HITS_PER_PAGE:
            break

    rows.sort(key=lambda r: r.get("filed_at", ""), reverse=True)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["filed_at", "ticker", "company", "cik", "url", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    with_ticker = sum(1 for r in rows if r["ticker"])
    print(f"sec_bankruptcy: {len(rows)} filings | with_ticker={with_ticker}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
