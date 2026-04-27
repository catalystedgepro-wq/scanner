"""
build_nt_radar.py — Detect NT (late filing) alerts and cross-reference with insider buys
Output: nt_radar.csv
"""

import csv
import json
import re
import time
import urllib.request
import urllib.error
import datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT_FILE = ROOT / "nt_radar.csv"
SLEEP_S = 0.5

UA = "LocalScanner/1.0 (opensource@example.com)"

def search_edgar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [WARN] EDGAR request failed: {e}")
        return {}

def extract_ticker(display_name):
    m = re.search(r'\(([A-Z]{1,6})\)', str(display_name))
    return m.group(1) if m else ""

def load_insider_clusters():
    """Return dict: ticker -> {confirmed_buy, filing_count}"""
    path = ROOT / "insider_clusters.csv"
    result = {}
    if not path.exists():
        return result
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get("ticker", "").strip()
            if ticker:
                result[ticker] = {
                    "confirmed_buy": row.get("confirmed_buy", "0").strip(),
                    "filing_count":  int(row.get("filing_count", 0) or 0),
                }
    return result

def load_sec_catalyst():
    """Return set of tickers with recent SEC activity."""
    path = ROOT / "sec_catalyst_latest.csv"
    tickers = set()
    if not path.exists():
        return tickers
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tickers.add(row.get("ticker", "").strip())
    return tickers

def fetch_nt_filings(days=45):
    """Fetch NT 10-K and NT 10-Q from EDGAR for last N days."""
    today = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    url = (
        f"https://efts.sec.gov/LATEST/search-index?forms=NT+10-K,NT+10-Q"
        f"&dateRange=custom&startdt={start}&enddt={today}"
    )
    print(f"Fetching NT filings from {start} to {today}")
    data = search_edgar(url)
    time.sleep(SLEEP_S)
    return data.get("hits", {}).get("hits", [])

def main():
    hits = fetch_nt_filings(days=45)
    print(f"Found {len(hits)} NT filings")

    insider_map = load_insider_clusters()
    sec_tickers = load_sec_catalyst()

    rows = []
    seen = {}  # ticker -> best row (prefer POSITIVE_NT)

    for hit in hits:
        src = hit.get("_source", {})
        display_names = src.get("display_names", [])
        form_type = src.get("form", src.get("form_type", src.get("file_type", "")))
        file_date = src.get("file_date", "")

        # Extract filer name and ticker
        filer_name = ""
        ticker = ""
        for dn in (display_names if isinstance(display_names, list) else [display_names]):
            t = extract_ticker(dn)
            if t:
                ticker = t
                filer_name = re.sub(r'\s*\([A-Z]{1,6}\)\s*$', '', str(dn)).strip()
                break

        if not ticker:
            continue

        # Build link from accession number (adsh)
        acc = src.get("adsh", hit.get("_id", ""))
        if acc:
            link = f"https://www.sec.gov/Archives/edgar/data/{src.get('ciks', [''])[0].lstrip('0')}/{acc.replace('-','')}/{acc}-index.htm"
        else:
            link = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=NT+10-K,NT+10-Q"

        # Cross-reference insider clusters
        insider_info = insider_map.get(ticker, {})
        confirmed_buy = insider_info.get("confirmed_buy", "0")
        insider_count = insider_info.get("filing_count", 0)
        has_insider_buy = confirmed_buy == "1"

        signal_type = "POSITIVE_NT" if has_insider_buy else "CAUTION_NT"

        row = {
            "ticker":         ticker,
            "signal_type":    signal_type,
            "nt_form":        form_type,
            "filed_date":     file_date,
            "filer_name":     filer_name,
            "has_insider_buy": str(has_insider_buy),
            "insider_count":  insider_count,
            "link":           link,
        }

        # Keep best signal per ticker
        existing = seen.get(ticker)
        if existing is None:
            seen[ticker] = row
        elif signal_type == "POSITIVE_NT" and existing["signal_type"] != "POSITIVE_NT":
            seen[ticker] = row
        elif file_date > existing["filed_date"]:
            seen[ticker] = row

    rows = sorted(seen.values(), key=lambda x: (x["signal_type"] == "POSITIVE_NT", x["filed_date"]), reverse=True)

    fieldnames = [
        "ticker", "signal_type", "nt_form", "filed_date",
        "filer_name", "has_insider_buy", "insider_count", "link"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_FILE}")
    positive = [r for r in rows if r["signal_type"] == "POSITIVE_NT"]
    print(f"POSITIVE_NT (insider buy + NT filing): {len(positive)}")
    for r in rows[:5]:
        print(f"  {r['ticker']}: {r['signal_type']} form={r['nt_form']} date={r['filed_date']}")

if __name__ == "__main__":
    main()
