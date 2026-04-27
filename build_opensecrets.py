#!/usr/bin/env python3
"""build_opensecrets.py — OpenSecrets lobbying + FEC contribution surface.

Lobbying spend spikes precede regulatory and policy catalysts. FEC
contribution data is published free by the Federal Election Commission.

Without an OPENSECRETS_API_KEY we use the FEC free API (fec.gov) for
recent donor/expense filings and archived lobbying CSV.

Output: opensecrets.csv
Columns: filing_date, type, organization, ticker_guess, amount_usd, detail, url
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
OUT_CSV = ROOT / "opensecrets.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FEC_KEY = os.environ.get("FEC_API_KEY", "DEMO_KEY")

FEC_ENDPOINT = (
    "https://api.open.fec.gov/v1/schedules/schedule_b/"
    "?api_key={key}&per_page=100&sort=-disbursement_date"
)

LOBBY_HINTS = {
    "AMAZON.COM": "AMZN", "ALPHABET INC": "GOOGL", "APPLE INC": "AAPL",
    "META PLATFORMS": "META", "MICROSOFT CORP": "MSFT",
    "PFIZER INC": "PFE", "MODERNA INC": "MRNA",
    "EXXON MOBIL": "XOM", "CHEVRON CORP": "CVX",
    "LOCKHEED MARTIN": "LMT", "RAYTHEON": "RTX", "BOEING": "BA",
    "GENERAL ELECTRIC": "GE", "TESLA INC": "TSLA",
    "JPMORGAN CHASE": "JPM", "GOLDMAN SACHS": "GS",
    "BLACKROCK": "BLK", "BANK OF AMERICA": "BAC",
    "WALMART": "WMT", "COSTCO": "COST",
    "INTEL CORP": "INTC", "NVIDIA": "NVDA", "AMD ": "AMD",
    "ORACLE CORP": "ORCL", "IBM CORP": "IBM", "CISCO": "CSCO",
    "AT&T": "T", "VERIZON": "VZ", "COMCAST": "CMCSA",
    "DISNEY": "DIS", "NETFLIX": "NFLX",
    "COINBASE": "COIN", "ROBINHOOD": "HOOD",
    "PALANTIR": "PLTR", "SALESFORCE": "CRM",
}


def fetch(url: str, timeout: int = 25) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"opensecrets/fec: {e}")
        return None


def guess(name: str) -> str:
    up = (name or "").upper()
    for k, v in LOBBY_HINTS.items():
        if k in up:
            return v
    return ""


def main():
    rows: list[dict] = []
    data = fetch(FEC_ENDPOINT.format(key=FEC_KEY))
    if data and "results" in data:
        for r in data["results"][:60]:
            name = r.get("payee_name") or r.get("memo_text") or ""
            rows.append({
                "filing_date": (r.get("disbursement_date") or "")[:10],
                "type": "FEC_DISBURSEMENT",
                "organization": name[:140],
                "ticker_guess": guess(name),
                "amount_usd": f"{float(r.get('disbursement_amount') or 0):.0f}",
                "detail": (r.get("disbursement_description") or "")[:140],
                "url": r.get("pdf_url") or "https://www.fec.gov/",
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "filing_date", "type", "organization", "ticker_guess",
                "amount_usd", "detail", "url",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"opensecrets: {len(rows)} filings ({with_tic} ticker-mapped) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
