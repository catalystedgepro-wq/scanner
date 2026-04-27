#!/usr/bin/env python3
"""build_uspto_feed.py — USPTO patent + trademark weekly feed.

USPTO publishes everything for free. This script pulls:
  - Patent applications published last 7 days (PatentsView API)
  - Trademark filings last 7 days (USPTO TSDR/Trademark API)

Maps assignee to ticker via public-company name hints.

Output: uspto_feed.csv
Columns: filing_date, type, assignee, ticker_guess, title, doc_id, url
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
OUT_CSV = ROOT / "uspto_feed.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# PatentsView now requires an API key (header: X-Api-Key). Without one we skip.
PATENT_API = "https://search.patentsview.org/api/v1/patent/"
PATENT_API_KEY = os.environ.get("PATENTSVIEW_API_KEY", "")

# USPTO trademark case-file RSS (via uspto.gov/dashboards) is not public. We
# use the USPTO's open-data bulk search endpoint for trademarks.
TRADEMARK_API = "https://tsdrapi.uspto.gov/ts/cd/casestatus"

ASSIGNEE_HINTS = {
    "APPLE INC": "AAPL", "MICROSOFT": "MSFT", "ALPHABET": "GOOGL",
    "GOOGLE": "GOOGL", "META PLATFORMS": "META", "AMAZON": "AMZN",
    "NVIDIA": "NVDA", "TESLA": "TSLA", "INTEL": "INTC", "IBM": "IBM",
    "ADVANCED MICRO DEVICES": "AMD", "QUALCOMM": "QCOM",
    "ORACLE": "ORCL", "SALESFORCE": "CRM", "ADOBE": "ADBE",
    "PFIZER": "PFE", "MODERNA": "MRNA", "JOHNSON & JOHNSON": "JNJ",
    "MERCK": "MRK", "ABBVIE": "ABBV", "ELI LILLY": "LLY",
    "BOEING": "BA", "LOCKHEED": "LMT", "RAYTHEON": "RTX",
    "GENERAL ELECTRIC": "GE", "CATERPILLAR": "CAT",
    "FORD MOTOR": "F", "GENERAL MOTORS": "GM",
    "EXXON": "XOM", "CHEVRON": "CVX",
    "WALMART": "WMT", "COSTCO": "COST", "TARGET": "TGT",
    "DISNEY": "DIS", "NETFLIX": "NFLX", "COMCAST": "CMCSA",
    "JPMORGAN": "JPM", "BANK OF AMERICA": "BAC", "CITIGROUP": "C",
    "GOLDMAN SACHS": "GS", "MORGAN STANLEY": "MS",
    "VISA": "V", "MASTERCARD": "MA", "PAYPAL": "PYPL",
    "PROCTER & GAMBLE": "PG", "COCA-COLA": "KO",
    "PALANTIR": "PLTR", "C3.AI": "AI", "C3 AI": "AI",
    "SNOWFLAKE": "SNOW", "DATABRICKS": "",
    "MICRON": "MU", "TSMC": "TSM", "APPLIED MATERIALS": "AMAT",
}


def fetch(url: str, body: dict | None = None, timeout: int = 25) -> dict | None:
    data = None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if PATENT_API_KEY:
        headers["X-Api-Key"] = PATENT_API_KEY
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"uspto: {url[-40:]} -> {e}")
        return None


def guess_ticker(name: str) -> str:
    up = (name or "").upper()
    for k, v in ASSIGNEE_HINTS.items():
        if k in up:
            return v
    return ""


def pull_patents() -> list[dict]:
    out: list[dict] = []
    if not PATENT_API_KEY:
        print("uspto: PATENTSVIEW_API_KEY not set — skipping patents.")
        return out
    today = dt.date.today()
    since = (today - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    query = {
        "q": {"_gte": {"patent_date": since}},
        "f": ["patent_id", "patent_title", "patent_date", "assignees"],
        "s": [{"patent_date": "desc"}],
        "o": {"size": 100},
    }
    data = fetch(PATENT_API, body=query)
    if not data or "patents" not in data:
        return out
    for p in data["patents"]:
        assignees = p.get("assignees") or []
        first = ""
        if assignees:
            first = assignees[0].get("assignee_organization") or assignees[0].get("raw_assignee_organization") or ""
        out.append({
            "filing_date": p.get("patent_date", ""),
            "type": "PATENT",
            "assignee": (first or "")[:120],
            "ticker_guess": guess_ticker(first),
            "title": (p.get("patent_title") or "")[:240],
            "doc_id": p.get("patent_id", ""),
            "url": f"https://patents.google.com/patent/US{p.get('patent_id','')}" if p.get("patent_id") else "",
        })
    return out


def main():
    rows: list[dict] = []
    rows.extend(pull_patents())
    # Trademark API requires OAuth for bulk pulls. We skip it in stdlib mode
    # unless/until a key is available via USPTO_API_KEY.
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["filing_date", "type", "assignee", "ticker_guess", "title", "doc_id", "url"],
        )
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"uspto_feed: {len(rows)} filings ({with_tic} ticker-mapped) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
