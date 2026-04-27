#!/usr/bin/env python3
"""build_sec_13d.py — Real-time 13D/13G activist + >5% stake filings.

Schedule 13D = activist position (intent to influence management).
Schedule 13G = passive >5% position (index fund, pension).
13D filings move small/mid-caps violently (Icahn, Elliott, Starboard
precedents). Must be captured within a narrow window of EDGAR publication.

Source: EDGAR full-text search (efts.sec.gov) — the getcurrent RSS feed
is unreliable for 13D/G forms (often returns empty), so we use the
keyword-search endpoint which actually indexes all filings.

Output: sec_13d_filings.csv
Columns: filed_at, form, filer, target_cik, target_name, ticker, url, captured_at
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
OUT_CSV = ROOT / "sec_13d_filings.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
LOOKBACK_DAYS = 7
HITS_PER_PAGE = 100
MAX_PAGES = 5

FORMS_QUERY = [
    ("SCHEDULE 13D", "SC 13D"),
    ("SCHEDULE 13D/A", "SC 13D/A"),
    ("SCHEDULE 13G", "SC 13G"),
    ("SCHEDULE 13G/A", "SC 13G/A"),
]

TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,\s*[A-Z0-9.\-]+)*\)\s*\(CIK")
CIK_RE = re.compile(r"CIK\s*(\d+)")


def efts_search(q_phrase: str, start: str, end: str, page_from: int = 0) -> dict:
    params = {
        "q": f'"{q_phrase}"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "forms": q_phrase,
        "hits": str(HITS_PER_PAGE),
        "from": str(page_from),
    }
    url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def extract_ticker_cik(display_names: list[str]) -> tuple[str, str, str]:
    """Return (ticker, cik, target_name) from a display_names entry."""
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
    # target name is the leading chunk before "  ("
    target = first.split("  (")[0].strip()
    return ticker, cik, target


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

    for efts_form, short_form in FORMS_QUERY:
        page_from = 0
        for _ in range(MAX_PAGES):
            try:
                data = efts_search(efts_form, start.isoformat(), end.isoformat(), page_from)
            except Exception as e:
                print(f"sec_13d {efts_form}: {e}")
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
                display_names = src.get("display_names", [])
                ticker, cik, target = extract_ticker_cik(display_names)
                # Filer = second display_names entry if present (filer separate from subject)
                filer = ""
                if len(display_names) > 1:
                    filer = display_names[1].split("  (")[0].strip()[:120]
                if not filer:
                    filer = target[:120]
                rows.append({
                    "filed_at": src.get("file_date", "") or src.get("accession_no", ""),
                    "form": short_form,
                    "filer": filer,
                    "target_cik": cik,
                    "target_name": target[:120],
                    "ticker": ticker,
                    "url": build_url(adsh, cik),
                    "captured_at": now,
                })
            page_from += HITS_PER_PAGE
            if len(hits) < HITS_PER_PAGE:
                break

    rows.sort(key=lambda r: r.get("filed_at", ""), reverse=True)
    rows = rows[:500]

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["filed_at", "form", "filer", "target_cik", "target_name",
                        "ticker", "url", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    by_form: dict[str, int] = {}
    with_ticker = 0
    for r in rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
        if r["ticker"]:
            with_ticker += 1
    dist = ", ".join(f"{k}={v}" for k, v in sorted(by_form.items()))
    print(f"sec_13d: {len(rows)} filings | with_ticker={with_ticker} | {dist}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
