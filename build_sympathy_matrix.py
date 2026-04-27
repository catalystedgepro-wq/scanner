#!/usr/bin/env python3
"""build_sympathy_matrix.py — Pre-compute sector-pair return correlations.

Replaces the velocity-sum sympathy proxy (F-5) with actual return correlation
per Lo & MacKinlay (1990, RFS) and Cont (2001, QF).

The HUD currently measures "both tickers are hot" (velocity sum) but not
"they move together" (return correlation). Two tickers can both have high
velocity but move in opposite directions.

This script computes:
  1. Per-sector 5-day rolling return series from Yahoo Finance
  2. Pairwise sector correlation matrix
  3. Top sympathy pairs for HUD link rendering

Output: sympathy_matrix.json — consumed by api_server.py /api/sympathy endpoint
        and CerebroHUD.jsx sympathyStrengthBetween().

Pure stdlib — no numpy/pandas required.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
OUTPUT = ROOT / "sympathy_matrix.json"

# Representative ETFs for each GICS sector — single liquid proxy
SECTOR_ETFS: dict[str, str] = {
    "tech":        "XLK",
    "financials":  "XLF",
    "biotech":     "XBI",    # more representative than XLV for biotech
    "energy":      "XLE",
    "utilities":   "XLU",
    "real_estate": "XLRE",
    "consumer":    "XLY",
    "staples":     "XLP",
    "materials":   "XLB",
    "industrials": "XLI",
    "comms":       "XLC",
    "semis":       "SMH",
}

YAHOO_CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range=30d&interval=1d"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _fetch_closes(symbol: str) -> list[float]:
    """Fetch 30d daily closes from Yahoo Finance."""
    url = YAHOO_CHART.format(symbol=symbol.upper())
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
        if enc == "gzip":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return []
    results = data.get("chart", {}).get("result") or []
    if not results:
        return []
    quotes = (results[0].get("indicators", {}).get("quote") or [{}])[0]
    return [float(c) for c in (quotes.get("close") or []) if c is not None]


def _returns(closes: list[float]) -> list[float]:
    """Compute daily log returns from close prices."""
    if len(closes) < 2:
        return []
    return [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]


def _correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation between two return series (aligned by index)."""
    n = min(len(x), len(y))
    if n < 5:
        return 0.0
    x = x[-n:]
    y = y[-n:]
    try:
        mx = statistics.fmean(x)
        my = statistics.fmean(y)
    except statistics.StatisticsError:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / (n - 1)) if n > 1 else 0
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / (n - 1)) if n > 1 else 0
    if sx <= 0 or sy <= 0:
        return 0.0
    return round(max(-1.0, min(1.0, cov / (sx * sy))), 4)


def _rolling_correlation(x: list[float], y: list[float], window: int = 5) -> float:
    """5-day rolling correlation — most recent window."""
    n = min(len(x), len(y))
    if n < window:
        return _correlation(x, y)
    return _correlation(x[-window:], y[-window:])


def main() -> int:
    import datetime
    print("build_sympathy_matrix: computing sector-pair correlations...")

    # Fetch ETF closes for each sector
    sector_returns: dict[str, list[float]] = {}
    for sector, etf in SECTOR_ETFS.items():
        closes = _fetch_closes(etf)
        rets = _returns(closes)
        sector_returns[sector] = rets
        print(f"  {sector:12s} ({etf:4s}): {len(closes)} closes, {len(rets)} returns")
        time.sleep(0.3)

    # Compute pairwise correlation matrix
    sectors = sorted(sector_returns.keys())
    matrix: dict[str, dict[str, float]] = {}
    for s1 in sectors:
        matrix[s1] = {}
        for s2 in sectors:
            if s1 == s2:
                matrix[s1][s2] = 1.0
            else:
                r1 = sector_returns.get(s1, [])
                r2 = sector_returns.get(s2, [])
                corr = _rolling_correlation(r1, r2, window=5)
                matrix[s1][s2] = corr

    # Extract top sympathy pairs (correlation > 0.5)
    sympathy_pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for s1 in sectors:
        for s2 in sectors:
            if s1 >= s2:
                continue
            pair_key = (s1, s2)
            if pair_key in seen:
                continue
            seen.add(pair_key)
            corr = matrix[s1][s2]
            if abs(corr) >= 0.3:
                sympathy_pairs.append({
                    "sector_a": s1,
                    "sector_b": s2,
                    "correlation": corr,
                    "strength": round(max(0, corr), 4),
                    "polarity": "sympathetic" if corr > 0 else "divergent",
                })

    sympathy_pairs.sort(key=lambda x: -abs(x["correlation"]))

    # Also compute per-ticker sympathy for tickers that appear in multiple
    # active lists — use sector correlation as proxy
    ticker_sector: dict[str, str] = {}
    em_path = ROOT / "entity_master.json"
    if em_path.exists():
        try:
            em = json.loads(em_path.read_text(encoding="utf-8"))
            for t, rec in em.items():
                gics = rec.get("gics")
                if isinstance(gics, dict) and gics.get("s"):
                    ticker_sector[t] = gics["s"]
        except Exception:
            pass

    result = {
        "date": datetime.date.today().isoformat(),
        "sector_etfs": SECTOR_ETFS,
        "correlation_matrix": matrix,
        "sympathy_pairs": sympathy_pairs,
        "ticker_sector_map_count": len(ticker_sector),
        "method": "5-day rolling return correlation (Lo & MacKinlay 1990)",
    }

    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\n  Wrote {OUTPUT.name}")
    print(f"  Sector pairs with |corr| >= 0.3: {len(sympathy_pairs)}")
    print(f"  Top 5 sympathy pairs:")
    for p in sympathy_pairs[:5]:
        print(f"    {p['sector_a']:12s} <-> {p['sector_b']:12s}  "
              f"corr={p['correlation']:+.3f}  [{p['polarity']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
