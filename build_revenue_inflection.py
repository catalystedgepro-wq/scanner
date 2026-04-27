"""
build_revenue_inflection.py — Detect first positive 8-K sentiment after a streak of silence
Output: revenue_inflection.csv
"""

import csv
import glob
import datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT_FILE = ROOT / "revenue_inflection.csv"

POSITIVE_KEYWORDS = {
    "record revenue", "raises guidance", "earnings beat", "positive results",
    "fda approval", "fda clearance", "breakthrough therapy", "contract award",
    "clinical trial results"
}

def load_keyword_hits(path):
    """Load a keyword_hits CSV. Returns list of dicts."""
    rows = []
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception:
        pass
    return rows

def load_sec_catalyst():
    """Load sec_catalyst_latest.csv, return dict ticker -> tags"""
    path = ROOT / "sec_catalyst_latest.csv"
    result = {}
    if not path.exists():
        return result
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get("ticker", "").strip()
                if ticker:
                    result.setdefault(ticker, []).append(row.get("tags", ""))
    except Exception:
        pass
    return result

def get_date_from_filename(fp):
    """Extract date from keyword_hits_YYYY-MM-DD.csv filename."""
    stem = Path(fp).stem  # keyword_hits_2026-03-15
    parts = stem.split("_")
    # Last part should be the date
    for part in reversed(parts):
        try:
            return datetime.date.fromisoformat(part)
        except ValueError:
            continue
    return None

def main():
    today = datetime.date.today()

    # Step 1: Load today's keyword_hits
    today_hits = load_keyword_hits(ROOT / "keyword_hits.csv")
    print(f"Today's keyword hits: {len(today_hits)}")

    # Find tickers with positive keywords today
    today_positive = {}  # ticker -> {keyword, form, link, filed_date}
    for row in today_hits:
        ticker = row.get("ticker", "").strip()
        kw = row.get("keyword", "").strip().lower()
        if not ticker:
            continue
        # Check if keyword matches any positive keyword (substring or exact)
        matched_kw = None
        for pos_kw in POSITIVE_KEYWORDS:
            if pos_kw in kw or kw in pos_kw:
                matched_kw = pos_kw
                break
        if matched_kw:
            if ticker not in today_positive:
                today_positive[ticker] = {
                    "keyword":    matched_kw,
                    "form":       row.get("keyword_label", row.get("form", "")),
                    "link":       row.get("filing_link", ""),
                    "filed_date": row.get("file_date", today.isoformat()),
                }

    print(f"Tickers with positive keywords today: {len(today_positive)}")

    if not today_positive:
        # Write empty output and exit
        fieldnames = [
            "ticker", "signal_strength", "positive_keyword",
            "days_since_last_positive", "form", "filed_date", "link"
        ]
        with open(OUTPUT_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        print(f"No positive hits today. Wrote empty {OUTPUT_FILE}")
        return

    # Step 2: Load archived keyword_hits files, sorted by date
    archived_files = sorted(glob.glob(str(ROOT / "keyword_hits_*.csv")))
    print(f"Found {len(archived_files)} archived keyword_hits files")

    # Build a timeline: date -> set of tickers with positive keywords
    archived_positive_by_date = {}  # date -> set of tickers

    for fp in archived_files:
        d = get_date_from_filename(fp)
        if d is None:
            continue
        rows = load_keyword_hits(fp)
        pos_tickers = set()
        for row in rows:
            ticker = row.get("ticker", "").strip()
            kw = row.get("keyword", "").strip().lower()
            if not ticker:
                continue
            for pos_kw in POSITIVE_KEYWORDS:
                if pos_kw in kw or kw in pos_kw:
                    pos_tickers.add(ticker)
                    break
        archived_positive_by_date[d] = pos_tickers

    # Sort dates descending (most recent first, excluding today)
    sorted_dates = sorted(archived_positive_by_date.keys(), reverse=True)

    # Step 3: For each ticker positive today, count consecutive days of absence
    sec_catalyst_map = load_sec_catalyst()

    results = []
    for ticker, info in today_positive.items():
        # Walk backward through dates counting days ticker was absent
        days_silent = 0
        for d in sorted_dates:
            if ticker in archived_positive_by_date[d]:
                break  # Found it — stop counting
            days_silent += (today - d).days if days_silent == 0 else 1
        else:
            # Never seen before — use total span
            if sorted_dates:
                days_silent = (today - sorted_dates[-1]).days
            else:
                days_silent = 30  # default assumption

        # More precise: count actual calendar days of absence
        # Re-count: iterate days, see if ticker was positive on any given archived date
        if sorted_dates:
            # Find the most recent archived date where ticker had positive keyword
            last_positive_date = None
            for d in sorted_dates:
                if ticker in archived_positive_by_date[d]:
                    last_positive_date = d
                    break
            if last_positive_date:
                days_silent = (today - last_positive_date).days
            else:
                # Check oldest available date
                days_silent = (today - sorted_dates[-1]).days if sorted_dates else 30

        # Classify signal strength
        if days_silent >= 14:
            signal_strength = "STRONG"
        elif days_silent >= 7:
            signal_strength = "MODERATE"
        elif days_silent >= 3:
            signal_strength = "MILD"
        else:
            continue  # Not an inflection

        # Check sec_catalyst corroboration
        tags_list = sec_catalyst_map.get(ticker, [])
        corroborated = any(t.startswith("+") for tags in tags_list for t in tags.split(";"))

        results.append({
            "ticker":                 ticker,
            "signal_strength":        signal_strength,
            "positive_keyword":       info["keyword"],
            "days_since_last_positive": days_silent,
            "form":                   info["form"],
            "filed_date":             info["filed_date"],
            "link":                   info["link"],
        })

    # Sort by signal strength then days_silent
    strength_order = {"STRONG": 0, "MODERATE": 1, "MILD": 2}
    results.sort(key=lambda x: (strength_order.get(x["signal_strength"], 9), -x["days_since_last_positive"]))

    fieldnames = [
        "ticker", "signal_strength", "positive_keyword",
        "days_since_last_positive", "form", "filed_date", "link"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} rows to {OUTPUT_FILE}")
    for r in results[:5]:
        print(f"  {r['ticker']}: {r['signal_strength']} ({r['days_since_last_positive']}d silent) kw='{r['positive_keyword']}'")

if __name__ == "__main__":
    main()
