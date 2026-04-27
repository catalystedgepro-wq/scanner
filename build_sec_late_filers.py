#!/usr/bin/env python3
"""build_sec_late_filers.py — SEC NT 10-K/NT 10-Q late-filer notifications.

Form 12b-25 ("NT") = company notifies SEC it cannot file 10-K/10-Q on
time. Initial NT causes typical -5% to -15% reaction. Reasons stated:
- Restatement pending → -20% to -40% historical drawdown window
- Auditor resignation → material risk, often -30%
- Cyber/system disruption → usually transitory, bounces 2-4 weeks
- Acquisition timing → usually benign, no persistent weakness

Secondary warnings: multiple NTs from same filer within 6 months = red
flag (SEC can delist if >45d late for 10-K, >5d for 10-Q with NT).

Source: efts.sec.gov/LATEST/search-index?forms=NT+10-K,NT+10-Q with
30-day window. display_names carries parenthesized tickers for listed
filers.

Output: sec_late_filers.csv
Columns: filing_date, form, ticker, company, cik, sic, state,
         period_ending, accession, captured_at
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
OUT_CSV = ROOT / "sec_late_filers.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://efts.sec.gov/LATEST/search-index"

# Pull tickers from display_names like "Foo Corp  (ABC)  (CIK ...)"
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9\.]{0,5})\)")


def fetch(form: str, start: str, end: str,
          page_size: int = 100) -> list[dict]:
    params = {
        "q": "",
        "forms": form,
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
    }
    out: list[dict] = []
    # EFTS search-index paginates with from/size.
    for offset in range(0, 600, page_size):
        p = dict(params, **{"from": offset})
        url = f"{API}?{urllib.parse.urlencode(p)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                body = json.loads(
                    r.read().decode("utf-8", errors="ignore"))
        except Exception as e:
            print(f"sec_late_filers {form}: offset={offset} -> {e}")
            break
        hits = body.get("hits", {}).get("hits", []) or []
        if not hits:
            break
        out.extend(hits)
        if len(hits) < page_size:
            break
    return out


def main() -> None:
    today = dt.date.today()
    start = (today - dt.timedelta(days=30)).isoformat()
    end = today.isoformat()

    filings: list[dict] = []
    for form in ("NT 10-K", "NT 10-Q"):
        hits = fetch(form, start, end)
        filings.extend(hits)

    if not filings and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"sec_late_filers: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for h in filings:
        src = h.get("_source", {}) or {}
        display = " ".join(src.get("display_names") or [])
        m = TICKER_RE.search(display)
        ticker = m.group(1) if m else ""
        # Strip any "CIK ..." capture from display
        company = re.sub(r"\s*\(CIK[^)]+\)\s*", "", display).strip()
        company = re.sub(r"\s*\([A-Z][A-Z0-9\.,\s]+\)\s*$", "",
                         company).strip()
        ciks = src.get("ciks") or [""]
        sics = src.get("sics") or [""]
        states = src.get("biz_states") or [""]
        rows.append({
            "filing_date": src.get("file_date", ""),
            "form": src.get("form", ""),
            "ticker": ticker,
            "company": company[:80],
            "cik": ciks[0] if ciks else "",
            "sic": sics[0] if sics else "",
            "state": states[0] if states else "",
            "period_ending": src.get("period_ending", ""),
            "accession": src.get("adsh", ""),
        })

    # Dedupe on accession
    seen: set[str] = set()
    dedup: list[dict] = []
    for r in rows:
        key = r["accession"]
        if not key or key in seen:
            if not key:
                dedup.append(r)
            continue
        seen.add(key)
        dedup.append(r)
    rows = dedup

    rows.sort(key=lambda r: r["filing_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["filing_date", "form", "ticker", "company", "cik",
                  "sic", "state", "period_ending", "accession",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    tickered = [r for r in rows if r["ticker"]]
    top_t = ", ".join(f"{r['ticker']}({r['form'].split()[-1]})"
                      for r in tickered[:5])
    print(f"sec_late_filers: {len(rows)} NT filings (30d) | "
          f"{len(tickered)} tickered | latest: {top_t} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
