"""
build_deepvalue_screen.py — Keith Gill-style deep value screen
Fetches Finviz metrics for top 60 tickers from combined_priority.csv
Output: deepvalue_screen.csv
Cache: .deepvalue_cache.json (TTL 12h)
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
CACHE_FILE = ROOT / ".deepvalue_cache.json"
OUTPUT_FILE = ROOT / "deepvalue_screen.csv"
CACHE_TTL_HOURS = 12
SLEEP_S = 1.2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def load_cache():
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            return data
        except Exception:
            pass
    return {}

def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def is_fresh(entry, ttl_hours=CACHE_TTL_HOURS):
    ts = entry.get("_ts", 0)
    age_h = (time.time() - ts) / 3600
    return age_h < ttl_hours

def parse_val(raw):
    """Parse a Finviz value string to float.

    Returns -1.0 on missing/unparseable input so score_ticker() can distinguish
    missing data (skip) from a genuine 0.0 (e.g. zero-debt = real signal).
    """
    if not raw or raw in ("-", "N/A", ""):
        return -1.0
    raw = raw.strip().rstrip("%").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return -1.0

def extract_finviz_label(html, label):
    """Find a Finviz table label and return the bold value after it."""
    idx = html.find(label)
    if idx == -1:
        return ""
    snippet = html[idx:idx+400]
    m = re.search(r"<b[^>]*>([^<]+)</b>", snippet)
    if m:
        return m.group(1).strip()
    return ""

def fetch_finviz(ticker):
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] Finviz fetch failed for {ticker}: {e}")
        return ""

def score_ticker(pb, pfcf, debt_eq, insider_own, roe, eps_next_y, short_float):
    pts = 0
    # P/B
    if pb > 0 and pb < 1.0:
        pts += 20
    elif pb > 0 and pb < 2.0:
        pts += 10
    # P/FCF
    if pfcf > 0 and pfcf < 15:
        pts += 15
    elif pfcf > 0 and pfcf < 25:
        pts += 8
    # Debt/Eq
    if debt_eq >= 0 and debt_eq < 0.5:
        pts += 15
    elif debt_eq >= 0 and debt_eq < 1.0:
        pts += 8
    # Insider Own
    if insider_own > 10:
        pts += 15
    elif insider_own > 5:
        pts += 8
    # ROE
    if roe > 15:
        pts += 15
    elif roe > 8:
        pts += 8
    # EPS next Y
    if eps_next_y > 0:
        pts += 10
    # Short Float bonus
    if short_float > 15:
        pts += 5
    return pts

def grade(score):
    if score >= 70:
        return "A"
    elif score >= 50:
        return "B"
    elif score >= 30:
        return "C"
    return "F"

def load_tickers():
    path = ROOT / "combined_priority.csv"
    tickers = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tickers.append(row["ticker"])
    return tickers[:60]

def main():
    cache = load_cache()
    tickers = load_tickers()
    print(f"Processing {len(tickers)} tickers from combined_priority.csv")

    results = []
    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}", end=" ")

        if ticker in cache and is_fresh(cache[ticker]):
            entry = cache[ticker]
            print("(cached)")
        else:
            html = fetch_finviz(ticker)
            time.sleep(SLEEP_S)

            pb_raw       = extract_finviz_label(html, ">P/B<")
            pfcf_raw     = extract_finviz_label(html, ">P/FCF<")
            debt_eq_raw  = extract_finviz_label(html, ">Debt/Eq<")
            insider_raw  = extract_finviz_label(html, ">Insider Own<")
            roe_raw      = extract_finviz_label(html, ">ROE<")
            eps_raw      = extract_finviz_label(html, ">EPS next Y<")
            short_raw    = extract_finviz_label(html, ">Short Float<")

            entry = {
                "pb": parse_val(pb_raw),
                "pfcf": parse_val(pfcf_raw),
                "debt_eq": parse_val(debt_eq_raw),
                "insider_own": parse_val(insider_raw),
                "roe": parse_val(roe_raw),
                "eps_next_y": parse_val(eps_raw),
                "short_float": parse_val(short_raw),
                "_ts": time.time(),
            }
            cache[ticker] = entry
            print(f"pb={entry['pb']} pfcf={entry['pfcf']} roe={entry['roe']}")

        sc = score_ticker(
            entry["pb"], entry["pfcf"], entry["debt_eq"],
            entry["insider_own"], entry["roe"], entry["eps_next_y"],
            entry["short_float"]
        )
        results.append({
            "ticker":          ticker,
            "deepvalue_score": sc,
            "pb_ratio":        entry["pb"],
            "pfcf_ratio":      entry["pfcf"],
            "debt_eq":         entry["debt_eq"],
            "insider_own_pct": entry["insider_own"],
            "roe_pct":         entry["roe"],
            "eps_next_y":      entry["eps_next_y"],
            "short_float_pct": entry["short_float"],
            "grade":           grade(sc),
        })

    save_cache(cache)

    results.sort(key=lambda x: x["deepvalue_score"], reverse=True)

    fieldnames = [
        "ticker", "deepvalue_score", "pb_ratio", "pfcf_ratio",
        "debt_eq", "insider_own_pct", "roe_pct", "eps_next_y",
        "short_float_pct", "grade"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} rows to {OUTPUT_FILE}")
    top = [r for r in results if r["grade"] in ("A", "B")]
    print(f"Grade A/B tickers: {len(top)}")
    for r in results[:5]:
        print(f"  {r['ticker']}: score={r['deepvalue_score']} grade={r['grade']} pb={r['pb_ratio']} roe={r['roe_pct']}")

if __name__ == "__main__":
    main()
