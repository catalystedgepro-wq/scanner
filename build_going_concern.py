#!/usr/bin/env python3
"""build_going_concern.py — SEC 10-K/10-Q "going concern" warnings.

A going-concern opinion in an auditor's report means the auditor has
substantial doubt about the company's ability to continue operating for
12 months. It's a direct equity catalyst — historically precedes
-20-40% drawdowns and delisting/bankruptcy within 18 months ~40% of
the time.

Trade uses:
- New going-concern disclosure in 10-K: immediate -15% to -25% on
  announcement, with 3-5 day continuation lower.
- Going-concern in 10-Q (quarterly): even more severe market reaction
  since it signals deterioration mid-year.
- Repeat going-concern for 2+ years: equity approaching zero, options
  market may price bankruptcy premium — look for Chapter 11 setup.
- Going-concern removed (recovery): mean-reversion long candidate, +30%
  to +100% moves common over 6 months.

Source: efts.sec.gov/LATEST/search-index?q="going concern"&forms=10-K,10-Q
EDGAR Full-Text Search index. Public, 10 req/sec etiquette.

Output: going_concern.csv
Columns: filing_date, ticker, cik, form, period_ending, filer_name,
         accession, captured_at
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
OUT_CSV = ROOT / "going_concern.csv"

UA = "CatalystEdge/1.0 opensource@example.com"
BASE = "https://efts.sec.gov/LATEST/search-index"
FORMS = "10-K,10-Q,10-K/A,10-Q/A,8-K"
TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def efts_fetch(days_back: int = 30, hits: int = 200) -> dict:
    end = dt.date.today()
    start = end - dt.timedelta(days=days_back)
    params = {
        "q": "\"going concern\"",
        "forms": FORMS,
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
        "hits": str(hits),
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"going_concern: {e}")
        return {}


def extract_ticker(display_names: list[str]) -> str:
    """Display name format: 'THEGLOBE COM INC  (TGLO)  (CIK 0001066684)'."""
    for nm in display_names or []:
        m = TICKER_RE.findall(nm)
        for t in m:
            if "CIK" not in t:
                return t
    return ""


def main() -> None:
    payload = efts_fetch(days_back=30, hits=200)
    hits_data = (payload.get("hits") or {}).get("hits") or []
    if not hits_data and OUT_CSV.exists() and OUT_CSV.stat().st_size > 150:
        print(f"going_concern: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    rows: list[dict] = []
    for h in hits_data:
        src = h.get("_source") or {}
        accession_file = h.get("_id", "")
        accession = accession_file.split(":")[0] if ":" in accession_file else accession_file
        display_names = src.get("display_names") or []
        ticker = extract_ticker(display_names)
        ciks = src.get("ciks") or []
        cik = ciks[0] if ciks else ""
        forms = src.get("forms") or src.get("root_forms") or []
        form = forms[0] if isinstance(forms, list) and forms else ""
        rows.append({
            "filing_date": src.get("file_date", ""),
            "ticker": ticker,
            "cik": cik.lstrip("0") if cik else "",
            "form": form or src.get("form", ""),
            "period_ending": src.get("period_ending", ""),
            "filer_name": (display_names[0] if display_names else "")[:120],
            "accession": accession,
        })
    rows.sort(key=lambda r: r["filing_date"], reverse=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["filing_date", "ticker", "cik", "form",
                        "period_ending", "filer_name", "accession",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    tickered = [r for r in rows if r["ticker"]]
    latest = rows[0] if rows else {}
    print(f"going_concern: {len(rows)} filings 30d "
          f"({len(tickered)} with ticker) | latest "
          f"{latest.get('filing_date','?')} "
          f"{latest.get('ticker','')} {latest.get('form','')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
