"""
build_dark_pool.py — Detect unusual volume patterns as dark pool proxy via Yahoo Finance v8
Output: dark_pool.csv
Cache: .dark_pool_cache.json (TTL 4h)
"""

import csv
import json
import time
import urllib.request
import urllib.error
import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).parent
CACHE_FILE = ROOT / ".dark_pool_cache.json"
OUTPUT_FILE = ROOT / "dark_pool.csv"
CACHE_TTL_HOURS = 4
SLEEP_S = 0.3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

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
    return tickers[:40]

def fetch_yahoo(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=35d"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [WARN] Yahoo fetch failed for {ticker}: {e}")
        return {}

def parse_yahoo(data):
    """Returns (closes, volumes) lists or ([], [])."""
    try:
        result = data["chart"]["result"][0]
        closes  = result["indicators"]["quote"][0].get("close", [])
        volumes = result["indicators"]["quote"][0].get("volume", [])
        # Filter out None values
        pairs = [(c, v) for c, v in zip(closes, volumes) if c is not None and v is not None]
        if not pairs:
            return [], []
        closes, volumes = zip(*pairs)
        return list(closes), list(volumes)
    except Exception:
        return [], []

def detect_signal(closes, volumes):
    """Detect volume signal. Returns (signal_type, today_vol, avg_vol_30d, vol_ratio, price_chg_pct)."""
    if len(volumes) < 6:
        return "INSUFFICIENT_DATA", 0, 0, 0, 0

    # Use up to last 31 entries for 30d avg, last entry as today
    hist_vols = volumes[:-1]  # all but last
    today_vol = volumes[-1]
    today_close = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]

    # 30d avg from historical
    avg_vol_30d = mean(hist_vols[-30:]) if len(hist_vols) >= 1 else today_vol

    vol_ratio = today_vol / avg_vol_30d if avg_vol_30d > 0 else 0
    price_chg_pct = (today_close - prev_close) / prev_close * 100 if prev_close else 0

    # Last 5 days (excluding today)
    last5_vols = hist_vols[-5:] if len(hist_vols) >= 5 else hist_vols
    last5_avg = mean(last5_vols) if last5_vols else 0

    signal = "NORMAL"
    if vol_ratio > 2.5:
        signal = "UNUSUAL_VOLUME"
    elif (0.8 <= vol_ratio <= 1.5
          and abs(price_chg_pct) < 1.0
          and last5_avg > avg_vol_30d):
        signal = "ACCUMULATION"
    elif (all(v < avg_vol_30d for v in last5_vols)
          and vol_ratio > 1.5):
        signal = "STEALTH_BUILD"

    return signal, today_vol, avg_vol_30d, vol_ratio, price_chg_pct

def main():
    cache = load_cache()
    tickers = load_tickers()
    today_str = datetime.date.today().isoformat()

    print(f"Processing {len(tickers)} tickers")

    results = []
    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}", end=" ")

        cache_key = f"{ticker}_{today_str}"
        if cache_key in cache and is_fresh(cache[cache_key]):
            entry = cache[cache_key]
            print("(cached)")
        else:
            data = fetch_yahoo(ticker)
            time.sleep(SLEEP_S)
            closes, volumes = parse_yahoo(data)
            signal, today_vol, avg_vol_30d, vol_ratio, price_chg = detect_signal(closes, volumes)

            entry = {
                "signal_type":    signal,
                "today_volume":   int(today_vol),
                "avg_volume_30d": int(avg_vol_30d),
                "volume_ratio":   round(vol_ratio, 3),
                "price_change_pct": round(price_chg, 3),
                "_ts": time.time(),
            }
            cache[cache_key] = entry
            print(f"signal={signal} ratio={vol_ratio:.2f} price_chg={price_chg:.2f}%")

        dark_flag = entry["signal_type"] in ("ACCUMULATION", "UNUSUAL_VOLUME", "STEALTH_BUILD")
        results.append({
            "ticker":           ticker,
            "signal_type":      entry["signal_type"],
            "today_volume":     entry["today_volume"],
            "avg_volume_30d":   entry["avg_volume_30d"],
            "volume_ratio":     entry["volume_ratio"],
            "price_change_pct": entry["price_change_pct"],
            "dark_pool_flag":   str(dark_flag),
        })

    save_cache(cache)

    results.sort(key=lambda x: (x["dark_pool_flag"] == "True", x["volume_ratio"]), reverse=True)

    fieldnames = [
        "ticker", "signal_type", "today_volume", "avg_volume_30d",
        "volume_ratio", "price_change_pct", "dark_pool_flag"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    flagged = [r for r in results if r["dark_pool_flag"] == "True"]
    print(f"\nWrote {len(results)} rows to {OUTPUT_FILE}")
    print(f"Dark pool signals: {len(flagged)}")
    for r in results[:5]:
        print(f"  {r['ticker']}: {r['signal_type']} ratio={r['volume_ratio']} flag={r['dark_pool_flag']}")

if __name__ == "__main__":
    main()
