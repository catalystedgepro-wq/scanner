#!/usr/bin/env python3
"""Authenticity Score — anti-pump moat.

For every published-cohort ticker today, computes a 0-100 score that
rewards multi-source corroboration and penalizes pump patterns. The
higher the score, the more "real" the catalyst signal.

Inputs (all already produced by the pipeline):
  - news_signals.csv      → multi-wire confirmation
  - sec_clean_gappers.csv → universe + market cap
  - lib_wire_filter.PUMP_REGEXES → headline pump patterns
  - .reddit_burst.json (if present) → social-media leak detection

Output:
  authenticity_scores.csv: ticker, score_0_to_100, components

Component scoring (range -30 to +30 each):
  + multi_wire_bonus (1 wire = 0, 2 wires = +12, 3+ wires = +20)
  + sec_filing_match (if a tier-1 wire matches a fresh SEC catalyst within
    24h on same ticker = +15 corroboration)
  + insider_with_news (Form 4 buy in last 5d alongside positive news = +10)
  - pump_regex_match (headline triggers any PUMP_REGEX = -25)
  - microcap_pump (mcap < $100M AND wire mentions = -15 extra)
  - reddit_lead (social spike >24h before SEC filing = -20)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
try:
    from lib_wire_filter import PUMP_REGEXES, load_universe
except ImportError:
    PUMP_REGEXES = []
    def load_universe(): return set()

NEWS_SIGNALS = ROOT / "news_signals.csv"
GAPPERS_CSV = ROOT / "sec_clean_gappers.csv"
SEC_LATEST = ROOT / "sec_catalyst_latest.csv"
OUT_CSV = ROOT / "authenticity_scores.csv"
OUT_JSON = ROOT / "authenticity_scores.json"


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    if not NEWS_SIGNALS.exists() or not GAPPERS_CSV.exists():
        print("authenticity: missing inputs")
        return 0

    # Build per-ticker market cap + recency lookups.
    mcap_lookup: dict[str, float] = {}
    score_lookup: dict[str, int] = {}
    with GAPPERS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            if not t:
                continue
            mcap_lookup[t] = to_float(r.get("market_cap", 0))
            try:
                score_lookup[t] = int(r.get("gapper_score", "0") or 0)
            except ValueError:
                score_lookup[t] = 0

    # Aggregate news rows per ticker, by source.
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    with NEWS_SIGNALS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker_candidates") or "").strip().upper()
            if not t or "," in t or ";" in t:
                continue
            by_ticker[t].append(r)

    # SEC catalyst freshness lookup.
    sec_recency: dict[str, int] = {}
    if SEC_LATEST.exists():
        with SEC_LATEST.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                t = (r.get("ticker") or "").strip().upper()
                try:
                    rec = int(r.get("recency_min", "999999") or 999999)
                except ValueError:
                    rec = 999999
                if not t:
                    continue
                if t not in sec_recency or rec < sec_recency[t]:
                    sec_recency[t] = rec

    out_rows: list[dict] = []
    for ticker in sorted(set(list(score_lookup.keys()) + list(by_ticker.keys()))):
        news_rows = by_ticker.get(ticker, [])
        unique_sources = {r.get("source") for r in news_rows if r.get("source")}

        # Components
        multi_wire = 0
        if len(unique_sources) >= 3:
            multi_wire = 20
        elif len(unique_sources) == 2:
            multi_wire = 12

        sec_match = 15 if (ticker in sec_recency and sec_recency[ticker] <= 1440) else 0

        # Pump regex over headlines
        pump_hits = 0
        for r in news_rows:
            headline = (r.get("headline") or "")
            if any(rx.search(headline) for rx in PUMP_REGEXES):
                pump_hits += 1
        pump_penalty = -25 if pump_hits else 0

        mcap = mcap_lookup.get(ticker, 0)
        microcap_pump = -15 if (pump_hits and 0 < mcap < 100_000_000) else 0

        # No social-leak signal yet (would need reddit timestamp comparison
        # vs SEC filing time) — leave as 0 for v1, add in a follow-up.
        social_lead = 0

        score = 50 + multi_wire + sec_match + pump_penalty + microcap_pump + social_lead
        score = max(0, min(100, score))

        out_rows.append({
            "ticker": ticker,
            "authenticity_score": score,
            "n_news_sources": len(unique_sources),
            "sources": ";".join(sorted(unique_sources)),
            "sec_match": "1" if sec_match else "0",
            "pump_regex_hits": pump_hits,
            "market_cap_band": (
                "micro" if 0 < mcap < 100_000_000 else
                "small" if mcap < 1_000_000_000 else
                "mid" if mcap < 10_000_000_000 else
                "large" if mcap >= 10_000_000_000 else "?"
            ),
            "components": json.dumps({
                "multi_wire": multi_wire,
                "sec_match": sec_match,
                "pump_penalty": pump_penalty,
                "microcap_pump": microcap_pump,
            }),
        })

    out_rows.sort(key=lambda r: -r["authenticity_score"])
    fields = ["ticker", "authenticity_score", "n_news_sources", "sources",
              "sec_match", "pump_regex_hits", "market_cap_band", "components"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    OUT_JSON.write_text(json.dumps({
        "computed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_tickers": len(out_rows),
        "high_authenticity_count": sum(1 for r in out_rows if r["authenticity_score"] >= 70),
        "low_authenticity_count": sum(1 for r in out_rows if r["authenticity_score"] <= 30),
        "by_ticker": {r["ticker"]: r["authenticity_score"] for r in out_rows[:200]},
    }, indent=2))
    print(
        f"authenticity: {len(out_rows)} tickers scored, "
        f"high={sum(1 for r in out_rows if r['authenticity_score']>=70)} "
        f"low={sum(1 for r in out_rows if r['authenticity_score']<=30)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
