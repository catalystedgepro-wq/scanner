#!/usr/bin/env python3
"""build_edgar_fulltext.py — EDGAR full-text keyword scanner.

SEC provides a full-text search at efts.sec.gov. Surfaces filings that
mention legally weighty phrases (going concern, material weakness,
restatement, strategic alternatives, etc.) — these are leading indicators
of blowups or activist-style moves.

Output: edgar_fulltext_hits.csv
Columns: ticker, cik, company, filed_date, form, phrase, filing_url
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "edgar_fulltext_hits.csv"

UA = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 (opensource@example.com)")
API = "https://efts.sec.gov/LATEST/search-index?q={q}&dateRange=custom&startdt={sd}&enddt={ed}&forms={forms}"

KEYWORDS = [
    '"going concern"',
    '"material weakness"',
    '"restatement"',
    '"restate our"',
    '"strategic alternatives"',
    '"internal investigation"',
    '"SEC subpoena"',
    '"DOJ investigation"',
    '"cyberattack"',
    '"ransomware"',
    '"bankruptcy"',
    '"Chapter 11"',
    '"reverse stock split"',
    '"delist"',
    '"qualified opinion"',
]


def fetch(url: str, timeout: int = 25) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"edgar_ft: {url[-40:]} -> {e}")
        return None


def main():
    today = dt.date.today()
    start = (today - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    rows = []
    for phrase in KEYWORDS:
        q = urllib.parse.quote(phrase)
        url = API.format(q=q, sd=start, ed=end, forms="10-K%2C10-Q%2C8-K%2CNT+10-K%2CNT+10-Q")
        data = fetch(url)
        if not data:
            continue
        hits = (data.get("hits") or {}).get("hits") or []
        for h in hits[:40]:
            src = h.get("_source", {})
            display_names = src.get("display_names") or []
            comp = display_names[0] if display_names else ""
            ticker = ""
            tm = re.search(r"\(([A-Z]{1,5})\)", comp)
            if tm:
                ticker = tm.group(1)
            ciks = src.get("ciks") or []
            cik = ciks[0] if ciks else ""
            accession = (h.get("_id") or "").replace("-", "")
            filing_url = ""
            if cik and accession:
                accession_raw = h.get("_id", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession}/{accession_raw}-index.html"
                )
            rows.append({
                "ticker": ticker,
                "cik": cik,
                "company": comp[:120],
                "filed_date": (src.get("file_date") or "")[:10],
                "form": src.get("form", ""),
                "phrase": phrase.strip('"'),
                "filing_url": filing_url,
            })
    # Dedupe by (cik, accession, phrase)
    seen, dedup = set(), []
    for r in rows:
        k = (r["cik"], r["filing_url"], r["phrase"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ticker", "cik", "company", "filed_date", "form", "phrase", "filing_url"],
        )
        w.writeheader()
        w.writerows(dedup)
    with_tic = sum(1 for r in dedup if r["ticker"])
    print(f"edgar_fulltext_hits: {len(dedup)} hits ({with_tic} ticker-tagged) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
