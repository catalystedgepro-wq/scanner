#!/usr/bin/env python3
"""build_options_activity.py — Detect unusual options activity for top SEC catalyst picks.

Hits Yahoo Finance free options endpoint for each top gapper.
Detects: vol/OI sweeps > 3x, bullish/bearish flow, large premium estimates.
Outputs options_activity.csv for the SEO scanner page.
"""
from __future__ import annotations
import csv, json, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT        = Path(__file__).parent
OUT         = ROOT / "options_activity.csv"
TOP_GAPPERS = ROOT / "sec_top_gappers.csv"
LIMIT       = 15  # top N tickers to check

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":     "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_tickers() -> list[str]:
    p = TOP_GAPPERS
    if not p.exists():
        return []
    tickers = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = row.get("ticker", "").strip()
            # skip warrants, rights, very long tickers
            if t and len(t) <= 5 and t.isalpha():
                tickers.append(t)
            if len(tickers) >= LIMIT:
                break
    return tickers


def fetch_options(ticker: str) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v7/finance/options/{ticker}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  options {ticker}: {e}")
        return None


def analyze(ticker: str, data: dict) -> dict | None:
    try:
        results = data.get("optionChain", {}).get("result", [])
        if not results:
            return None
        result = results[0]
        options_list = result.get("options", [{}])
        if not options_list:
            return None
        opt = options_list[0]
        calls = opt.get("calls", [])
        puts  = opt.get("puts",  [])

        def safe_vol(contract): return int(contract.get("volume") or 0)
        def safe_oi(contract):  return int(contract.get("openInterest") or 0)
        def safe_price(c):      return float(c.get("lastPrice") or 0)

        call_vol = sum(safe_vol(c) for c in calls)
        put_vol  = sum(safe_vol(p) for p in puts)

        # Unusual = vol/OI ratio > 3 (strong signal)
        unusual_calls = [c for c in calls if safe_oi(c) > 0 and safe_vol(c)/safe_oi(c) > 3]
        unusual_puts  = [p for p in puts  if safe_oi(p) > 0 and safe_vol(p)/safe_oi(p) > 3]

        # Premium estimate: top 5 calls by volume
        top_calls_by_vol = sorted(calls, key=safe_vol, reverse=True)[:5]
        premium_est = int(sum(safe_vol(c) * safe_price(c) * 100 for c in top_calls_by_vol))

        pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else 0

        # Determine signal
        signal = "neutral"
        uc, up = len(unusual_calls), len(unusual_puts)
        if uc >= 2 and uc > up:        signal = "bullish sweep"
        elif up >= 2 and up > uc:      signal = "bearish sweep"
        elif call_vol > 0 and put_vol > 0:
            if call_vol / (put_vol or 1) >= 2: signal = "bullish flow"
            elif put_vol / (call_vol or 1) >= 2: signal = "bearish flow"

        # Top contract info
        top_call = max(calls, key=safe_vol, default={})
        strike   = top_call.get("strike", "")
        exp_ts   = top_call.get("expiration", 0)
        expiry   = datetime.utcfromtimestamp(exp_ts).strftime("%b %d") if exp_ts else ""

        return {
            "ticker":        ticker,
            "call_vol":      call_vol,
            "put_vol":       put_vol,
            "pc_ratio":      pc_ratio,
            "top_strike":    strike,
            "expiry":        expiry,
            "premium_est":   premium_est,
            "unusual_calls": uc,
            "unusual_puts":  up,
            "signal":        signal,
        }
    except Exception as ex:
        print(f"  analyze {ticker}: {ex}")
        return None


def main() -> int:
    tickers = load_tickers()
    if not tickers:
        print("build_options_activity: no tickers — skipping")
        return 0

    results = []
    for t in tickers:
        print(f"  options: {t}")
        data = fetch_options(t)
        if data:
            row = analyze(t, data)
            if row:
                results.append(row)
                sig = row["signal"]
                cv, pv = row["call_vol"], row["put_vol"]
                print(f"    {sig}  calls={cv:,} puts={pv:,}  unusual_c={row['unusual_calls']} unusual_p={row['unusual_puts']}")
        time.sleep(0.6)  # polite rate-limiting

    if results:
        fields = ["ticker","call_vol","put_vol","pc_ratio","top_strike","expiry",
                  "premium_est","unusual_calls","unusual_puts","signal"]
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(results)
        print(f"build_options_activity: {len(results)} tickers → {OUT.name}")
    else:
        print("build_options_activity: no data retrieved (market may be closed)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
