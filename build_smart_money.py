"""
build_smart_money.py — Track 13-F institutional filings for pipeline tickers
Output: smart_money.csv
Cache: .smart_money_cache.json (TTL 8h)
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
CACHE_FILE = ROOT / ".smart_money_cache.json"
OUTPUT_FILE = ROOT / "smart_money.csv"
CACHE_TTL_HOURS = 8
SLEEP_S = 0.5

UA = "LocalScanner/1.0 (opensource@example.com)"

def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}

def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def is_fresh(entry, ttl_hours=CACHE_TTL_HOURS):
    ts = entry.get("_ts", 0)
    return (time.time() - ts) / 3600 < ttl_hours

def load_tickers():
    path = ROOT / "combined_priority.csv"
    tickers = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tickers.append(row["ticker"])
    return tickers[:30]

def search_13f(ticker, start_dt, end_dt):
    """Search EDGAR EFTS for 13F-HR filings mentioning ticker."""
    q = urllib.parse.quote(f'"{ticker}"')
    url = (
        f"https://efts.sec.gov/LATEST/search-index?q={q}"
        f"&forms=13F-HR&dateRange=custom&startdt={start_dt}&enddt={end_dt}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        hits = data.get("hits", {}).get("hits", [])
        return hits
    except Exception as e:
        print(f"  [WARN] EDGAR 13F search failed for {ticker}: {e}")
        return []

def extract_fund_name(display_names):
    if not display_names:
        return ""
    name = display_names[0] if isinstance(display_names, list) else str(display_names)
    # Strip trailing ticker symbol like "FUND NAME (XYZ)"
    name = re.sub(r'\s*\([A-Z]{1,6}\)\s*$', '', name).strip()
    return name

def main():
    cache = load_cache()
    tickers = load_tickers()
    today = datetime.date.today().isoformat()
    sixty_ago = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()

    print(f"Checking 13-F filings for {len(tickers)} tickers ({sixty_ago} to {today})")

    results = []
    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}", end=" ")

        cache_key = f"{ticker}_{today}"
        if cache_key in cache and is_fresh(cache[cache_key]):
            entry = cache[cache_key]
            print("(cached)")
        else:
            hits = search_13f(ticker, sixty_ago, today)
            time.sleep(SLEEP_S)

            fund_names = []
            latest_date = ""
            latest_fund = ""
            primary_link = ""

            for hit in hits:
                src = hit.get("_source", {})
                display_names = src.get("display_names", [])
                file_date = src.get("file_date", "")
                fund_name = extract_fund_name(display_names)
                if fund_name:
                    fund_names.append(fund_name)
                if file_date > latest_date:
                    latest_date = file_date
                    latest_fund = fund_name
                    # Build a rough link from accession number if available
                    acc = hit.get("_id", "")
                    if acc:
                        primary_link = f"https://www.sec.gov/Archives/edgar/data/{acc}"

            # Count distinct funds
            distinct_funds = list(dict.fromkeys(fund_names))  # preserve order, dedupe

            entry = {
                "fund_count": len(distinct_funds),
                "latest_fund_name": latest_fund,
                "latest_filed_date": latest_date,
                "total_mentions": len(hits),
                "primary_link": primary_link,
                "_ts": time.time(),
            }
            cache[cache_key] = entry
            print(f"funds={entry['fund_count']} mentions={entry['total_mentions']}")

        fund_count = entry["fund_count"]
        if fund_count >= 2:
            signal = "INSTITUTIONAL_INTEREST"
        elif fund_count == 1:
            signal = "WATCH"
        else:
            signal = "NONE"

        if signal != "NONE":
            results.append({
                "ticker":            ticker,
                "fund_count":        fund_count,
                "latest_fund_name":  entry["latest_fund_name"],
                "latest_filed_date": entry["latest_filed_date"],
                "total_mentions":    entry["total_mentions"],
                "signal":            signal,
                "primary_link":      entry["primary_link"],
            })

    save_cache(cache)

    results.sort(key=lambda x: x["fund_count"], reverse=True)

    fieldnames = [
        "ticker", "fund_count", "latest_fund_name", "latest_filed_date",
        "total_mentions", "signal", "primary_link"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} rows to {OUTPUT_FILE}")
    for r in results[:5]:
        print(f"  {r['ticker']}: signal={r['signal']} funds={r['fund_count']} latest={r['latest_fund_name']}")

if __name__ == "__main__":
    main()
