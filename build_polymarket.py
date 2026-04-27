#!/usr/bin/env python3
"""Polymarket spoke — prediction market probability surge detector.

Pulls active markets from gamma-api.polymarket.com and surfaces ones with:
  - Public-equity nexus (FDA approval / M&A / earnings markets that name a ticker)
  - Probability shift >= 10pp in last 24h (the "surge" signal)
  - Volume >= $5,000 (avoid noise-floor markets)

Per academic finding (Ng/Peng/Tao/Zhou 2025): Polymarket leads Kalshi in
price discovery; net order imbalance predicts subsequent equity returns.
This is leading-indicator alpha NOT in our SEC-catalyst stack today.

Output: polymarket_signals.csv — same shape as wire spokes so
build_news_momentum.py picks it up via load_polymarket_rows().

Free public API, no auth required.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from lib_wire_filter import load_universe, extract_tickers
except ImportError:
    def load_universe(): return set()
    def extract_tickers(t, u): return []

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "polymarket_signals.csv"
STATUS_JSON = ROOT / "polymarket_status.json"
API = "https://gamma-api.polymarket.com/markets"
USER_AGENT = "CatalystEdge/1.0 (opensource@example.com)"

# Topic keywords that suggest a market may have public-equity impact.
EQUITY_NEXUS_TOPICS = {
    "fda": "biotech",
    "approval": "biotech",
    "earnings": "earnings",
    "merger": "merger",
    "acquisition": "merger",
    "acquire": "merger",
    "election": "macro_election",
    "rate cut": "macro_rates",
    "rate hike": "macro_rates",
    "fed": "macro_rates",
    "recession": "macro",
    "tariff": "trade",
    "ipo": "ipo",
    "bankruptcy": "credit",
}


def fetch_markets(active_only: bool = True, limit: int = 500) -> list[dict]:
    params = {
        "limit": str(limit),
        "active": "true" if active_only else "false",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return []
    if isinstance(data, list):
        return data
    return data.get("markets", []) if isinstance(data, dict) else []


def equity_nexus_label(question: str, description: str) -> str:
    text = (question + " " + description).lower()
    for kw, label in EQUITY_NEXUS_TOPICS.items():
        if kw in text:
            return label
    return ""


def to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    universe = load_universe()
    markets = fetch_markets()
    now_utc = dt.datetime.now(dt.timezone.utc)
    rows: list[dict] = []
    surges = 0
    nexus_count = 0
    for m in markets:
        question = (m.get("question") or "").strip()
        description = (m.get("description") or "").strip()
        slug = (m.get("slug") or "").strip()
        nexus = equity_nexus_label(question, description)
        if not nexus:
            continue
        nexus_count += 1
        vol_24h = to_float(m.get("volume24hr") or 0)
        if vol_24h < 5_000:
            continue
        # current YES probability (best ask price ≈ implied probability for YES side)
        last_price = to_float(m.get("lastTradePrice") or 0)
        if last_price <= 0 or last_price >= 1.0:
            continue
        # Net change vs 24h ago
        prev_price = to_float(m.get("oneDayPriceChange") or 0)
        # oneDayPriceChange is delta, not prior. Surge = abs(delta) >= 0.10.
        surge = abs(prev_price) >= 0.10
        # Try to extract referenced tickers from question + description.
        tickers = extract_tickers(f"{question} {description}", universe) if universe else []
        # Also pattern-grep biotech/M&A markets that name companies — we map
        # company names to tickers via the universe-locked extractor only.
        # Markets without ticker context still emit a sector-tag row.
        ticker_field = ",".join(tickers) if tickers else ""
        if surge:
            surges += 1
        rows.append({
            "timestamp_utc": now_utc.isoformat(),
            "market_slug": slug,
            "question": question[:200],
            "nexus": nexus,
            "ticker_candidates": ticker_field,
            "current_probability": f"{last_price:.4f}",
            "delta_24h": f"{prev_price:+.4f}",
            "volume_24h_usd": f"{vol_24h:.2f}",
            "surge_flag": "1" if surge else "0",
            "url": f"https://polymarket.com/event/{slug}" if slug else "",
        })
    rows.sort(key=lambda r: (-int(r["surge_flag"]), -float(r["volume_24h_usd"])))
    fields = ["timestamp_utc", "market_slug", "question", "nexus",
              "ticker_candidates", "current_probability", "delta_24h",
              "volume_24h_usd", "surge_flag", "url"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    STATUS_JSON.write_text(json.dumps({
        "status": "ok" if rows else "empty",
        "ts_utc": now_utc.isoformat(),
        "markets_scanned": len(markets),
        "equity_nexus_markets": nexus_count,
        "rows_kept": len(rows),
        "surges_detected": surges,
    }, indent=2), encoding="utf-8")
    print(f"polymarket: scanned={len(markets)} nexus={nexus_count} kept={len(rows)} surges={surges}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
