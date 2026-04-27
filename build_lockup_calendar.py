"""
build_lockup_calendar.py — Track IPO lockup expiries from S-1 filings
Output: lockup_calendar.csv
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
OUTPUT_FILE = ROOT / "lockup_calendar.csv"
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

def extract_company_name(display_name):
    name = re.sub(r'\s*\([A-Z]{1,6}\)\s*$', '', str(display_name)).strip()
    return name

def load_insider_clusters():
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
                    "latest_utc": row.get("latest_utc", ""),
                }
    return result

def main():
    today = datetime.date.today()
    today_str = today.isoformat()
    one_year_ago = (today - datetime.timedelta(days=365)).isoformat()

    # For 180-day lockup: we want expiry dates in range [-14, +30] days from today
    # => filing dates in range [today-194, today-150]
    target_start = (today - datetime.timedelta(days=194)).isoformat()
    target_end   = (today - datetime.timedelta(days=150)).isoformat()
    print(f"Fetching S-1 filings from {target_start} to {target_end} (for ~180d lockup window)")

    all_hits = []
    # Paginate: EDGAR returns 100 hits per request, use from parameter
    for page_start in range(0, 500, 100):
        url = (
            f"https://efts.sec.gov/LATEST/search-index?forms=S-1"
            f"&dateRange=custom&startdt={target_start}&enddt={target_end}"
            f"&hits.hits._source=display_names,file_date,adsh,ciks"
            f"&from={page_start}"
        )
        data = search_edgar(url)
        time.sleep(SLEEP_S)
        page_hits = data.get("hits", {}).get("hits", [])
        if not page_hits:
            break
        all_hits.extend(page_hits)
        total = data.get("hits", {}).get("total", {}).get("value", 0)
        if len(all_hits) >= total:
            break

    hits = all_hits
    print(f"Found {len(hits)} S-1 filings")

    insider_map = load_insider_clusters()

    rows = []
    seen_tickers = set()

    for hit in hits:
        src = hit.get("_source", {})
        display_names = src.get("display_names", [])
        file_date_str = src.get("file_date", "")
        acc = hit.get("_id", "")

        if not file_date_str:
            continue

        # Parse file date
        try:
            file_date = datetime.date.fromisoformat(file_date_str)
        except ValueError:
            continue

        lockup_expiry = file_date + datetime.timedelta(days=180)
        days_until = (lockup_expiry - today).days

        # Classify status
        if days_until <= 0 and days_until >= -14:
            status = "RECENTLY_EXPIRED"
        elif 0 < days_until <= 7:
            status = "EXPIRES_THIS_WEEK"
        elif 7 < days_until <= 30:
            status = "UPCOMING_30D"
        else:
            continue  # Not relevant

        # Extract ticker and company
        ticker = ""
        company_name = ""
        for dn in (display_names if isinstance(display_names, list) else [display_names]):
            t = extract_ticker(dn)
            if t:
                ticker = t
                company_name = extract_company_name(dn)
                break

        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        # Build link
        link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=S-1&dateb=&owner=include&count=10"
        if acc:
            link = f"https://efts.sec.gov/LATEST/search-index?q=%22{acc}%22"

        # Check insider activity after lockup expiry
        insider_info = insider_map.get(ticker, {})
        insider_bought_after = False
        if insider_info.get("confirmed_buy") == "1":
            latest_utc = insider_info.get("latest_utc", "")
            if latest_utc:
                try:
                    # Parse ISO datetime
                    latest_date_str = latest_utc[:10]
                    latest_date = datetime.date.fromisoformat(latest_date_str)
                    if latest_date >= lockup_expiry:
                        insider_bought_after = True
                except Exception:
                    pass

        rows.append({
            "ticker":             ticker,
            "company_name":       company_name,
            "filing_date":        file_date_str,
            "lockup_expiry_date": lockup_expiry.isoformat(),
            "days_until_expiry":  days_until,
            "status":             status,
            "insider_bought_after": str(insider_bought_after),
            "link":               link,
        })

    # Sort: soonest expiry first, then recently expired
    status_order = {"EXPIRES_THIS_WEEK": 0, "RECENTLY_EXPIRED": 1, "UPCOMING_30D": 2}
    rows.sort(key=lambda x: (status_order.get(x["status"], 9), x["days_until_expiry"]))

    fieldnames = [
        "ticker", "company_name", "filing_date", "lockup_expiry_date",
        "days_until_expiry", "status", "insider_bought_after", "link"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_FILE}")
    if rows:
        for r in rows[:5]:
            print(f"  {r['ticker']}: {r['status']} expires={r['lockup_expiry_date']} insider_after={r['insider_bought_after']}")
    else:
        print("  No qualifying lockup events found (empty CSV written with headers)")

if __name__ == "__main__":
    main()
