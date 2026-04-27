#!/usr/bin/env python3
"""build_courtlistener_recap.py — CourtListener RECAP bankruptcy filings.

CourtListener (Free Law Project) provides a public API to every PACER
bankruptcy docket. Chapter 11 filings move tickers immediately (JCPEW,
WEWKQ, SBNY, SIVB, etc.).

Output: courtlistener_recap.csv
Columns: case_name, date_filed, chapter, court, ticker_guess, url
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "courtlistener_recap.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")

# Search docket endpoint — no auth required for basic use.
API = "https://www.courtlistener.com/api/rest/v4/search/?type=r&q={q}&filed_after={fa}&order_by=dateFiled+desc"

HINTS = {
    "WEWORK": "WE", "REVLON": "REV", "BED BATH": "BBBY",
    "HERTZ": "HTZ", "AMC ENTERTAINMENT": "AMC",
    "PURDUE": "", "FTX": "", "CELSIUS NETWORK": "",
    "SILICON VALLEY BANK": "SIVBQ", "SIGNATURE BANK": "SBNY",
    "SILVERGATE": "SICP", "GENESIS": "",
    "PARTY CITY": "PRTY", "LORDSTOWN": "RIDE",
    "VICE MEDIA": "", "ENVISION HEALTHCARE": "",
    "RITE AID": "RAD", "BED BATH & BEYOND": "BBBY",
    "DIAMOND SPORTS": "",
}


def fetch(url: str, timeout: int = 25) -> dict | None:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Token {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"courtlistener: {e}")
        return None


def guess(name: str) -> str:
    up = (name or "").upper()
    for k, v in HINTS.items():
        if k in up:
            return v
    return ""


def main():
    today = dt.date.today()
    since = (today - dt.timedelta(days=30)).strftime("%Y-%m-%d")
    q = urllib.parse.quote("chapter 11")
    url = API.format(q=q, fa=since)
    data = fetch(url) or {}
    rows: list[dict] = []
    for r in data.get("results", [])[:80]:
        name = r.get("caseName") or r.get("case_name") or ""
        rows.append({
            "case_name": name[:180],
            "date_filed": r.get("dateFiled") or r.get("date_filed") or "",
            "chapter": "11",
            "court": r.get("court") or r.get("court_id") or "",
            "ticker_guess": guess(name),
            "url": "https://www.courtlistener.com" + (r.get("docket_absolute_url") or r.get("absolute_url") or ""),
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["case_name", "date_filed", "chapter", "court", "ticker_guess", "url"],
        )
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"courtlistener_recap: {len(rows)} filings ({with_tic} ticker-mapped) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
