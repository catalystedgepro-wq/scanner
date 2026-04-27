#!/usr/bin/env python3
"""Search EDGAR EFTS for high-confidence keywords in today's 8-K filings.

Uses EDGAR full-text search to confirm pipeline picks and surface new tickers.
Outputs: keyword_hits.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
UA = "CatalystEdge/1.0 (opensource@example.com)"

KEYWORD_SEARCHES = [
    ("FDA approval",            "fda_approval",      10),
    ("FDA clearance",           "fda_clearance",     10),
    ("breakthrough therapy",    "fda_breakthrough",  10),
    ("definitive agreement",    "merger_acq",         9),
    ("clinical trial results",  "clinical_trial",     9),
    ("contract award",          "contract_award",     8),
    ("awarded contract",        "contract_award",     8),
    ("record revenue",          "record_revenue",     8),
    ("raises guidance",         "guidance_raise",     8),
    ("share repurchase program","buyback",            7),
    ("earnings beat",           "earnings_beat",      7),
    ("positive results",        "positive_results",   7),
]


def efts_search(keyword: str, form: str, today: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": f'"{keyword}"',
        "dateRange": "custom",
        "startdt": today,
        "enddt": today,
        "forms": form,
    })
    req = urllib.request.Request(
        f"{EFTS_URL}?{params}",
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("hits", {}).get("hits", [])
    except Exception as e:
        print(f"keyword_hits: EFTS failed for '{keyword}': {e}")
        return []


def extract_ticker(hit: dict) -> str:
    for name in hit.get("_source", {}).get("display_names", []):
        if "(" in name and ")" in name:
            candidate = name.rsplit("(", 1)[-1].rstrip(")")
            if 1 <= len(candidate) <= 5 and candidate.isalpha() and candidate.isupper():
                return candidate
    return ""


def main() -> int:
    today = dt.date.today().isoformat()

    existing_tickers: set[str] = set()
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv", "sec_clean_moat_core.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv"]:
        path = ROOT / fname
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper()
                if t:
                    existing_tickers.add(t)

    out_rows: list[dict] = []
    seen: set[str] = set()

    for keyword, label, boost in KEYWORD_SEARCHES:
        for hit in efts_search(keyword, "8-K", today)[:15]:
            ticker = extract_ticker(hit)
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            src = hit.get("_source", {})
            entity = src.get("entity_name", "")
            in_pipeline = ticker in existing_tickers
            filing_link = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?company={urllib.parse.quote(entity)}&type=8-K&dateb=&owner=include&count=5&action=getcompany"
                if entity else ""
            )
            out_rows.append({
                "ticker": ticker,
                "keyword": keyword,
                "keyword_label": label,
                "confidence_boost": boost,
                "entity_name": entity,
                "file_date": src.get("file_date", today),
                "in_pipeline": "1" if in_pipeline else "0",
                "filing_link": filing_link,
            })

    out_rows.sort(key=lambda r: (-int(r["in_pipeline"]), -int(r["confidence_boost"])))

    out_path = ROOT / "keyword_hits.csv"
    fieldnames = ["ticker","keyword","keyword_label","confidence_boost",
                  "entity_name","file_date","in_pipeline","filing_link"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    confirmed = sum(1 for r in out_rows if r["in_pipeline"] == "1")
    new_found = len(out_rows) - confirmed
    print(f"keyword_hits: {len(out_rows)} hits — {confirmed} confirm pipeline, {new_found} new → {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
