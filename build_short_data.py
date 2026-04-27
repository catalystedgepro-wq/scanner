#!/usr/bin/env python3
"""Fetch short interest metrics for all pipeline tickers via Finviz.

Outputs: short_data.csv
Columns: ticker, short_pct_float, days_to_cover, float_shares,
         avg_volume, si_trend_pct
"""
from __future__ import annotations

import csv
import datetime
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT       = Path(__file__).parent
OUT_CSV    = ROOT / "short_data.csv"
CACHE_FILE = ROOT / ".short_data_cache.json"
CACHE_TTL  = 8 * 3600  # Finviz data updates infrequently — 8h cache

FINVIZ_URL = "https://finviz.com/quote.ashx?t={symbol}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

FIELDNAMES = [
    "ticker", "short_pct_float", "days_to_cover",
    "float_shares_m", "avg_volume_m", "si_pct_raw", "si_trend_pct",
]


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_cache(c: dict) -> None:
    CACHE_FILE.write_text(json.dumps(c))


def _extract(html: str, label: str) -> str:
    idx = html.find(label)
    if idx < 0:
        return ""
    chunk = html[idx:idx + 300]
    m = re.search(r"<b>([^<]+)</b>", chunk)
    return m.group(1).strip() if m else ""


def _parse_pct(s: str) -> float:
    """'16.11%' → 16.11"""
    try:
        return float(s.replace("%", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _parse_float_m(s: str) -> float:
    """'407.30M' or '1.20B' → value in millions"""
    s = s.strip()
    try:
        if s.endswith("B"):
            return float(s[:-1]) * 1000
        if s.endswith("M"):
            return float(s[:-1])
        if s.endswith("K"):
            return float(s[:-1]) / 1000
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def fetch_finviz(symbol: str) -> dict:
    url = FINVIZ_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        short_float  = _extract(html, "Short Float")
        short_ratio  = _extract(html, "Short Ratio")
        shs_float    = _extract(html, "Shs Float")
        avg_vol      = _extract(html, "Avg Volume")

        si_pct  = _parse_pct(short_float)
        dtc     = float(short_ratio) if short_ratio and short_ratio != "-" else 0.0
        flt_m   = _parse_float_m(shs_float)
        avol_m  = _parse_float_m(avg_vol)

        if si_pct == 0.0 and short_float == "":
            return {}  # Finviz page didn't load or no data

        return {
            "ticker":           symbol.upper(),
            "short_pct_float":  round(si_pct, 2),
            "days_to_cover":    round(dtc, 2),
            "float_shares_m":   round(flt_m, 2),
            "avg_volume_m":     round(avol_m, 2),
            "si_pct_raw":       short_float,
            "si_trend_pct":     0.0,   # computed below from history
        }
    except Exception:
        return {}


def load_tickers() -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for csv_path in [
        ROOT / "combined_priority.csv",
        ROOT / "sec_top_gappers.csv",
        ROOT / "sec_top_value.csv",
        ROOT / "sec_top_moat.csv",
    ]:
        if not csv_path.exists():
            continue
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("ticker") or "").strip().upper()
                if t and t not in seen and "-" not in t and len(t) <= 6:
                    seen.add(t)
                    tickers.append(t)
    return tickers[:80]  # Finviz is slower — cap at 80


def main() -> int:
    now_ts = int(datetime.datetime.now().timestamp())
    cache  = load_cache()
    rows: list[dict] = []
    tickers = load_tickers()
    print(f"build_short_data: fetching {len(tickers)} tickers via Finviz")

    for i, ticker in enumerate(tickers):
        entry = cache.get(ticker)
        if entry and now_ts - int(entry.get("ts", 0)) < CACHE_TTL:
            data = entry.get("data", {})
        else:
            data = fetch_finviz(ticker)
            cache[ticker] = {"ts": now_ts, "data": data}
            # Be polite — 1 req/sec
            time.sleep(1.1)

        if data:
            # Compute SI trend vs previous cached reading (7+ days ago)
            prev_entry = cache.get(f"_prev_{ticker}")
            if prev_entry:
                prev_si = float(prev_entry.get("short_pct_float", 0) or 0)
                curr_si = float(data.get("short_pct_float", 0) or 0)
                if prev_si > 0:
                    data["si_trend_pct"] = round((curr_si - prev_si) / prev_si * 100, 2)
            # Store prev reading if current data is fresh (not from cache)
            entry = cache.get(ticker)
            if entry and now_ts - int(entry.get("ts", 0)) >= CACHE_TTL:
                old_data = entry.get("data", {})
                if old_data:
                    cache[f"_prev_{ticker}"] = old_data
            rows.append(data)

        if (i + 1) % 10 == 0:
            print(f"  ... {i+1}/{len(tickers)}")

    save_cache(cache)
    rows.sort(key=lambda r: float(r.get("short_pct_float", 0) or 0), reverse=True)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    high_si = [r for r in rows if float(r.get("short_pct_float", 0) or 0) >= 20]
    print(f"  Wrote {len(rows)} rows | {len(high_si)} with SI >= 20%")
    if rows:
        top = rows[:5]
        print("  Top SI tickers:")
        for r in top:
            print(f"    {r['ticker']:8s}  SI={r['short_pct_float']:.1f}%  DTC={r['days_to_cover']:.1f}d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
