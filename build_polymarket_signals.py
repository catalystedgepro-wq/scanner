#!/usr/bin/env python3
"""build_polymarket_signals.py — Fetch live Polymarket prediction market signals
for the Catalyst Edge newsletter.

Pulls the top macro/geopolitical/economic markets by 24h volume,
filters for finance-relevant ones, and saves to polymarket_signals.json
for use in the newsletter template.

No API key required — Gamma API is fully public.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
OUT  = ROOT / "polymarket_signals.json"

# Keywords that make a market relevant to traders
FINANCE_KEYWORDS = [
    "fed ", "federal reserve", "interest rate", "rate cut", "rate hike",
    "inflation", "recession", "gdp", "tariff", "trade war",
    "china trade", "iran", "oil price", "energy price", "crude",
    "bitcoin price", "crypto market", "gold price", "nasdaq", "s&p 500",
    "stock market", "earnings", "acquisition", "merger", "ipo", "layoffs",
    "unemployment", "treasury", "us dollar", "debt ceiling",
    "sanctions", "opec", "bank collapse", "financial crisis", "economic",
    "market crash", "bear market", "default", "powell", "ceasefire",
    "russia invade", "ukraine war", "north korea", "taiwan",
    "kharg island", "strait of hormuz",
]

# Exclude clearly non-financial markets
SPORTS_EXCLUDE = [
    # Traditional sports
    "nba", "nfl", "nhl", "mlb", "soccer", "football", "basketball",
    "hockey", "baseball", "tennis", "golf", "mma", "ufc", "f1",
    "super bowl", "world cup", "champions league", "premier league",
    "warriors", "lakers", "celtics", "jets", "eagles", "cowboys",
    "shockers", "hornets", "knicks", "cavaliers", "nuggets",
    "wichita", "tulsa", "vs.", "o/u", "spread:", "moneyline",
    "lebron", "mahomes",
    # Esports / gaming — nothing to do with macro markets
    "dota", "counter-strike", "cs:go", "csgo", "cs2",
    "esport", "e-sport", "esports",
    "league of legends", "valorant", "overwatch", "fortnite",
    "pubg", "apex legends", "rocket league", "starcraft",
    "hearthstone", "fifa", "call of duty", "warzone", "halo",
    "gaming tournament", "pro league", "esl ", "blast ", "faceit",
    "major championship",
    # Entertainment / reality TV / pop culture
    "oscar", "emmy", "grammy", "golden globe", "bafta",
    "survivor", "bachelor", "big brother", "american idol",
    "box office", "album", "song of the year", "best actor",
    "best picture", "celebrity", "kardashian", "taylor swift",
]

USER_AGENT = "CatalystEdge/1.0 (opensource@example.com)"


def fetch_active_markets(limit: int = 200) -> list[dict]:
    url = (
        f"https://gamma-api.polymarket.com/markets"
        f"?limit={limit}&active=true&closed=false&order=volume24hr&ascending=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  Polymarket fetch error: {e}")
        return []


def parse_probability(outcome_prices) -> float | None:
    """Return YES probability as 0-100 float."""
    try:
        if isinstance(outcome_prices, str):
            prices = json.loads(outcome_prices)
        else:
            prices = outcome_prices
        return round(float(prices[0]) * 100, 1)
    except Exception:
        return None


def is_finance_relevant(title: str) -> bool:
    t = title.lower()
    if any(ex in t for ex in SPORTS_EXCLUDE):
        return False
    return any(kw in t for kw in FINANCE_KEYWORDS)


def signal_label(prob: float) -> str:
    if prob >= 80:
        return "HIGH CONVICTION"
    if prob >= 60:
        return "LIKELY"
    if prob >= 40:
        return "CONTESTED"
    if prob >= 20:
        return "UNLIKELY"
    return "LOW PROBABILITY"


def market_impact(title: str) -> str:
    """Return a brief trader-facing impact note."""
    t = title.lower()
    if "iran" in t or "israel" in t or "ceasefire" in t:
        return "Energy stocks, defense, oil prices"
    if "fed" in t or "rate" in t or "interest" in t:
        return "Rate-sensitive: banks, REITs, growth stocks"
    if "tariff" in t or "trade war" in t or "china" in t:
        return "Manufacturing, supply chain, semiconductors"
    if "bitcoin" in t or "crypto" in t:
        return "Risk sentiment, crypto-adjacent equities"
    if "recession" in t or "gdp" in t:
        return "Broad market, defensives vs cyclicals"
    if "oil" in t or "opec" in t or "energy" in t:
        return "Energy sector, transportation, materials"
    if "russia" in t or "ukraine" in t:
        return "Commodities, defense, European equities"
    if "default" in t or "debt" in t:
        return "Treasuries, credit markets, financials"
    return "Macro / risk-off sentiment"


def main():
    print("build_polymarket_signals: fetching active markets...")
    markets = fetch_active_markets(200)
    print(f"  Fetched {len(markets)} active markets")

    signals = []
    for m in markets:
        title = (m.get("question") or m.get("groupItemTitle") or "").strip()
        if not title or not is_finance_relevant(title):
            continue

        prob = parse_probability(m.get("outcomePrices"))
        if prob is None:
            continue

        # Skip already-resolved (0% or 100%) unless very high volume
        vol24 = float(m.get("volume24hr") or 0)
        if prob in (0.0, 100.0) and vol24 < 5_000_000:
            continue

        end_date = (m.get("endDate") or "")[:10]
        total_vol = float(m.get("volume") or 0)

        signals.append({
            "title":       title,
            "probability": prob,
            "label":       signal_label(prob),
            "impact":      market_impact(title),
            "vol_24h":     vol24,
            "vol_total":   total_vol,
            "end_date":    end_date,
            "url":         f"https://polymarket.com/event/{(m.get('events') or [{}])[0].get('slug') or m.get('slug', '')}",
        })

    # Sort by 24h volume — most active = most relevant
    signals.sort(key=lambda x: x["vol_24h"], reverse=True)
    top = signals[:10]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals":      top,
    }

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"  Saved {len(top)} signals to {OUT.name}")
    print()
    print("  TOP POLYMARKET MACRO SIGNALS:")
    for s in top:
        bar = "█" * int(s["probability"] / 10) + "░" * (10 - int(s["probability"] / 10))
        print(f"  {s['probability']:5.1f}%  [{bar}]  {s['title'][:65]}")
        print(f"          Impact: {s['impact']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
