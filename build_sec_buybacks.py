#!/usr/bin/env python3
"""build_sec_buybacks.py — Share-repurchase authorizations via 8-K full text.

Reads efts.sec.gov full-text search for 8-K filings containing either:
- "share repurchase program"
- "stock repurchase program"
- "authorized to repurchase"

Then dedupes by (ticker, file_date).

Buybacks = shareholder-yield floor.  Large programs (>$1B, or >5% of
market cap) can front-run price by 2-5% over 30 days post-announcement
(Ikenberry, Lakonishok, Vermaelen 1995 buyback anomaly still holds).

Signal tiers:
- Mega program (name recognition) = bullish-credit-quality bid
- First-time program (no prior) = structural shift, activist pressure
- Small / penny = low-signal (screens out)

Source: efts.sec.gov/LATEST/search-index
Output: sec_buybacks.csv
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
OUT_CSV = ROOT / "sec_buybacks.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://efts.sec.gov/LATEST/search-index"
LOOKBACK_DAYS = 30

QUERIES = [
    '"share repurchase program"',
    '"stock repurchase program"',
    '"authorized to repurchase"',
]

NAME_RE = re.compile(
    r"^(?P<name>.+?)\s+\((?P<tickers>[A-Z0-9,\s\.\-]+?)\)\s+"
    r"\(CIK\s+(?P<cik>\d+)\)"
)


def _fetch(query: str, startdt: str, enddt: str) -> list[dict]:
    params = {
        "q": query,
        "forms": "8-K",
        "dateRange": "custom",
        "startdt": startdt,
        "enddt": enddt,
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"sec_buybacks: {query[:20]}: {e}")
        return []
    hits = d.get("hits", {}).get("hits", [])
    return hits if isinstance(hits, list) else []


def _parse_name(raw: str) -> tuple[str, str, str]:
    m = NAME_RE.match(raw.strip())
    if not m:
        return raw.strip(), "", ""
    tickers = [t.strip() for t in m.group("tickers").split(",")
               if t.strip()]
    return (m.group("name").strip(),
            tickers[0] if tickers else "",
            m.group("cik"))


def main() -> None:
    today = dt.date.today()
    startdt = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    enddt = today.isoformat()

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for query in QUERIES:
        for h in _fetch(query, startdt, enddt):
            src = h.get("_source", {}) if isinstance(h, dict) else {}
            if not isinstance(src, dict):
                continue
            display = src.get("display_names") or []
            if not display:
                continue
            name, ticker, cik = _parse_name(
                display[0] if isinstance(display, list) else "")
            file_date = src.get("file_date", "")
            key = (ticker or cik, file_date)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "ticker": ticker,
                "cik": cik,
                "company": name[:50],
                "file_date": file_date,
                "accession_id": (h.get("_id", "") or "").split(":")[0],
                "captured_at": now_iso,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_buybacks: no fetch, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["file_date"], r["ticker"]), reverse=True)

    fieldnames = ["ticker", "cik", "company", "file_date",
                  "accession_id", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    recent = [r for r in rows if r["file_date"]
              >= (today - dt.timedelta(days=7)).isoformat()]
    rtick = " ".join(r["ticker"] for r in recent if r["ticker"])[:120]
    print(f"sec_buybacks: {len(rows)} authorizations | last7d="
          f"{len(recent)} [{rtick}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
