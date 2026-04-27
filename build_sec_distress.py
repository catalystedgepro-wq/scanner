#!/usr/bin/env python3
"""build_sec_distress.py — Corporate distress tape via SEC EDGAR.

Categories:
- bankruptcy_petition → "bankruptcy petition" in 8-K.  Chapter 11/7
                        filing.  Equity typically goes to zero or
                        near-zero (common stock rarely recovers >10%
                        of pre-petition value).  Days 1-5 = last
                        retail-squeeze window (HTZ, WHC, SHLD tape).
- nasdaq_delisting    → "nasdaq delisting" in 8-K.  Final-stage
                        compliance failure.  Often coincides with
                        reverse-split attempt.
- going_concern       → "going concern" in 8-K / 10-K / 10-Q.
                        Auditor's substantial-doubt flag; shares
                        typically trade -20-40% over following 90d
                        (Lenard-Alam-Madray 2012).

Source: efts.sec.gov/LATEST/search-index
Output: sec_distress.csv

Complements existing build_going_concern.py (10-K focus) by pulling
full-text hits across all form types and combining with bankruptcy /
delisting tapes.  Lookback: 45 days.
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
OUT_CSV = ROOT / "sec_distress.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://efts.sec.gov/LATEST/search-index"
LOOKBACK_DAYS = 45

QUERIES = {
    "bankruptcy_petition": ('"bankruptcy petition"', "8-K"),
    "nasdaq_delisting": ('"nasdaq delisting"', "8-K,25-NSE"),
    "going_concern": ('"going concern"', "8-K,10-K,10-Q"),
}

NAME_RE = re.compile(
    r"^(?P<name>.+?)\s+\((?P<tickers>[A-Z0-9,\s\.\-]+?)\)\s+"
    r"\(CIK\s+(?P<cik>\d+)\)"
)


def _fetch(query: str, forms: str, startdt: str,
           enddt: str) -> list[dict]:
    q = urllib.parse.quote(query)
    f = urllib.parse.quote(forms)
    url = (f"{BASE}?q={q}&forms={f}&dateRange=custom"
           f"&startdt={startdt}&enddt={enddt}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"sec_distress: {query[:20]}: {e}")
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
    seen: set[tuple[str, str, str]] = set()

    for kind, (query, forms) in QUERIES.items():
        for h in _fetch(query, forms, startdt, enddt):
            src = h.get("_source", {}) if isinstance(h, dict) else {}
            if not isinstance(src, dict):
                continue
            display = src.get("display_names") or []
            if not display:
                continue
            name, ticker, cik = _parse_name(
                display[0] if isinstance(display, list) else "")
            file_date = src.get("file_date", "")
            form = src.get("form", "") or src.get("root_form", "")
            key = (kind, ticker or cik, file_date)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "kind": kind,
                "ticker": ticker,
                "cik": cik,
                "company": name[:50],
                "form": form,
                "file_date": file_date,
                "accession_id": (h.get("_id", "") or "").split(":")[0],
                "captured_at": now_iso,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_distress: no fetch, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["file_date"], r["kind"], r["ticker"]),
              reverse=True)

    fieldnames = ["kind", "ticker", "cik", "company", "form",
                  "file_date", "accession_id", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind = {k: 0 for k in QUERIES}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    recent = [r for r in rows if r["file_date"]
              >= (today - dt.timedelta(days=7)).isoformat()]
    rtick = " ".join(f"{r['kind'][:4]}:{r['ticker']}" for r in recent
                     if r["ticker"])[:140]
    summary = " ".join(f"{k[:4]}={v}" for k, v in by_kind.items())
    print(f"sec_distress: {len(rows)} distress tape | {summary} | "
          f"last7d={len(recent)} [{rtick}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
