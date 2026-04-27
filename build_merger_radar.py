"""
build_merger_radar.py — Detect M&A pre-announcement signals from SEC filings
Output: merger_signals.csv
"""

import csv
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT_FILE = ROOT / "merger_signals.csv"
SLEEP_S = 0.4

UA = "LocalScanner/1.0 (opensource@example.com)"

SIGNAL_RANK = {
    "TENDER_OFFER":     4,
    "ACTIVIST_DEAL":    3,
    "STRATEGIC_REVIEW": 2,
    "IN_PLAY":          1,
}

def search_edgar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [WARN] EDGAR request failed ({url[:80]}): {e}")
        return {}

def extract_ticker(display_name):
    m = re.search(r'\(([A-Z]{1,6})\)', str(display_name))
    return m.group(1) if m else ""

def extract_all_tickers(display_names):
    tickers = set()
    for dn in (display_names if isinstance(display_names, list) else [display_names]):
        t = extract_ticker(dn)
        if t:
            tickers.add(t)
    return tickers

def load_pipeline_tickers():
    path = ROOT / "combined_priority.csv"
    tickers = set()
    if not path.exists():
        return tickers
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tickers.add(row["ticker"].strip())
    return tickers

def load_keyword_hits():
    """Return dict: ticker -> [keywords]"""
    path = ROOT / "keyword_hits.csv"
    result = {}
    if not path.exists():
        return result
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get("ticker", "").strip()
            kw = row.get("keyword", "").strip().lower()
            if ticker:
                result.setdefault(ticker, []).append(kw)
    return result

def fetch_form_hits(forms, days, signal_type, label):
    today = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    # Preserve pre-escaped form codes like "SC 13D%2FA" — using quote() here
    # double-encodes the %2F to %252F and breaks the 13D/A feed query.
    encoded_forms = urllib.parse.quote(forms, safe="%,+")
    url = (
        f"https://efts.sec.gov/LATEST/search-index?forms={encoded_forms}"
        f"&dateRange=custom&startdt={start}&enddt={today}"
    )
    print(f"  Fetching {label} ({start} to {today})...")
    data = search_edgar(url)
    time.sleep(SLEEP_S)
    hits = data.get("hits", {}).get("hits", [])
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        display_names = src.get("display_names", [])
        form_type = src.get("form_type", forms)
        file_date = src.get("file_date", "")
        acc = hit.get("_id", "")
        link = f"https://efts.sec.gov/LATEST/search-index?q=%22{acc}%22" if acc else ""
        for ticker in extract_all_tickers(display_names):
            results.append({
                "ticker":      ticker,
                "signal_type": signal_type,
                "form":        form_type,
                "date":        file_date,
                "link":        link,
                "description": label,
            })
    return results

def fetch_keyword_hits(keyword, days, signal_type, label):
    today = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    q = urllib.parse.quote(f'"{keyword}"')
    url = (
        f"https://efts.sec.gov/LATEST/search-index?q={q}"
        f"&forms=8-K&dateRange=custom&startdt={start}&enddt={today}"
    )
    print(f"  Fetching keyword '{keyword}' 8-Ks...")
    data = search_edgar(url)
    time.sleep(SLEEP_S)
    hits = data.get("hits", {}).get("hits", [])
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        display_names = src.get("display_names", [])
        file_date = src.get("file_date", "")
        acc = hit.get("_id", "")
        link = f"https://efts.sec.gov/LATEST/search-index?q=%22{acc}%22" if acc else ""
        for ticker in extract_all_tickers(display_names):
            results.append({
                "ticker":      ticker,
                "signal_type": signal_type,
                "form":        "8-K",
                "date":        file_date,
                "link":        link,
                "description": label,
            })
    return results

def main():
    pipeline_tickers = load_pipeline_tickers()
    keyword_map = load_keyword_hits()
    print(f"Pipeline tickers: {len(pipeline_tickers)}")

    all_hits = []

    # Step 1: Tender offers and proxy contests
    all_hits += fetch_form_hits("SC TO-T,DEFA14A", 45, "TENDER_OFFER", "Tender/Proxy")

    # Step 2: Activist amendments
    all_hits += fetch_form_hits("SC 13D%2FA", 30, "ACTIVIST_DEAL", "Activist 13D/A")

    # Step 3: Strategic review 8-Ks
    all_hits += fetch_keyword_hits("strategic alternatives", 30, "STRATEGIC_REVIEW", "Strategic Review")
    all_hits += fetch_keyword_hits("fairness opinion", 30, "IN_PLAY", "Fairness Opinion")

    # Step 4: Keyword hits from our pipeline
    ma_keywords = {"definitive agreement", "merger agreement"}
    for ticker, keywords in keyword_map.items():
        for kw in keywords:
            if kw in ma_keywords:
                all_hits.append({
                    "ticker":      ticker,
                    "signal_type": "IN_PLAY",
                    "form":        "keyword_hit",
                    "date":        datetime.date.today().isoformat(),
                    "link":        "",
                    "description": f"keyword: {kw}",
                })

    print(f"Total raw hits: {len(all_hits)}")

    # Group by ticker: track all signal types and count
    by_ticker = {}
    for h in all_hits:
        ticker = h["ticker"]
        entry = by_ticker.setdefault(ticker, {
            "ticker":        ticker,
            "signal_type":   h["signal_type"],
            "form":          h["form"],
            "signal_count":  0,
            "latest_date":   "",
            "description":   h["description"],
            "link":          h["link"],
            "rank":          SIGNAL_RANK.get(h["signal_type"], 0),
        })
        entry["signal_count"] += 1
        if h["date"] > entry["latest_date"]:
            entry["latest_date"] = h["date"]
        # Upgrade to highest signal type
        if SIGNAL_RANK.get(h["signal_type"], 0) > entry["rank"]:
            entry["signal_type"] = h["signal_type"]
            entry["rank"] = SIGNAL_RANK[h["signal_type"]]
            entry["form"] = h["form"]
            entry["description"] = h["description"]
            entry["link"] = h["link"]

    # Filter to pipeline tickers only, or keep all if pipeline set is small
    rows = list(by_ticker.values())
    if pipeline_tickers:
        rows = [r for r in rows if r["ticker"] in pipeline_tickers]

    rows.sort(key=lambda x: (x["rank"], x["signal_count"]), reverse=True)

    fieldnames = [
        "ticker", "signal_type", "form", "signal_count",
        "latest_date", "description", "link"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_FILE}")
    for r in rows[:5]:
        print(f"  {r['ticker']}: {r['signal_type']} count={r['signal_count']} date={r['latest_date']}")

if __name__ == "__main__":
    main()
