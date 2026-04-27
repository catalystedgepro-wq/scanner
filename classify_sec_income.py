#!/usr/bin/env python3
"""Classify SEC filings for conservative/income investors.

Scans the same sec_catalyst_latest.csv produced by sec_catalyst_list.py and
identifies tickers with dividend, buyback, and balance-sheet-quality signals
that appeal to income-focused, lower-risk investors.

Outputs:
  sec_income_picks.csv        — scored income candidates (top 25)
  sec_income_tickers.txt      — one ticker per line

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
import time
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
INPUT = ROOT / "sec_catalyst_latest.csv"

OUT_CSV = ROOT / "sec_income_picks.csv"
OUT_TXT = ROOT / "sec_income_tickers.txt"

CACHE_FILE = ROOT / ".sec_filing_text_cache.json"
CACHE_QUOTE_FILE = ROOT / ".sec_quote_cache.json"
CACHE_TTL_SEC = 48 * 3600
QUOTE_CACHE_TTL_SEC = 20 * 60

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"

# ---------------------------------------------------------------------------
# Signal keyword lists
# ---------------------------------------------------------------------------

# Strong income / dividend signals
POS_INCOME = [
    "dividend increase",
    "dividend increased",
    "raises dividend",
    "increased quarterly dividend",
    "quarterly dividend declared",
    "quarterly cash dividend",
    "special dividend",
    "special cash dividend",
    "cash dividend declared",
    "regular quarterly dividend",
    "annual dividend increase",
    "dividend per share",
    "dividend yield",
    "consecutive dividend",
    "dividend aristocrat",
]

# Capital return / balance sheet strength signals
POS_QUALITY = [
    "share repurchase",
    "buyback program",
    "authorized repurchase",
    "stock repurchase program",
    "repurchase up to",
    "debt reduction",
    "deleveraging",
    "paid down",
    "repaid",
    "investment grade",
    "credit upgrade",
    "upgraded to",
    "credit rating",
    "free cash flow",
    "strong balance sheet",
    "debt-free",
]

# Risk flags — penalize or exclude
NEG_INCOME = [
    "dividend cut",
    "dividend suspension",
    "suspends dividend",
    "eliminates dividend",
    "dividend reduction",
    "offering",
    "private placement",
    "atm program",
    "at-the-market",
    "going concern",
    "bankruptcy",
    "chapter 11",
    "delist",
    "non-compliance",
    "material weakness",
    "default",
    "debt default",
]

# Defensive sectors — get a quality bonus
DEFENSIVE_KEYWORDS = [
    "utilities", "utility", "electric", "gas distribution",
    "water utility", "water company",
    "healthcare", "health care", "hospital", "pharma",
    "consumer staples", "food", "beverage",
    "insurance", "reinsurance",
    "real estate investment trust", "reit",
    "telecommunications", "telecom",
]

# ---------------------------------------------------------------------------
# Cache helpers (reuse patterns from classify_sec_catalysts.py)
# ---------------------------------------------------------------------------

def load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def load_quote_cache() -> dict[str, Any]:
    if not CACHE_QUOTE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_QUOTE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_quote_cache(cache: dict[str, Any]) -> None:
    CACHE_QUOTE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def _http_get(url: str, timeout: int = 20) -> bytes:
    ua = os.getenv("SEC_USER_AGENT", "CatalystEdge/1.0 (opensource@example.com)")
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.info().get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw

# ---------------------------------------------------------------------------
# SEC filing text fetch (shared cache with classify_sec_catalysts.py)
# ---------------------------------------------------------------------------

def fetch_filing_text(link: str, cache: dict[str, Any]) -> str:
    now = time.time()
    entry = cache.get(link)
    if entry and now - entry.get("ts", 0) < CACHE_TTL_SEC:
        return entry.get("text", "")
    try:
        html = _http_get(link).decode("utf-8", errors="replace")
        # Strip tags
        text = re.sub(r"<[^>]+>", " ", html)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text)[:8000]
        cache[link] = {"ts": now, "text": text}
        time.sleep(0.25)
        return text
    except Exception:
        cache[link] = {"ts": now, "text": ""}
        return ""


# ---------------------------------------------------------------------------
# Price / market data fetch via Stooq (shared cache)
# ---------------------------------------------------------------------------

def fetch_stooq_quote(symbol: str, quote_cache: dict[str, Any]) -> dict[str, float]:
    now = time.time()
    entry = quote_cache.get(symbol)
    if entry and now - entry.get("ts", 0) < QUOTE_CACHE_TTL_SEC:
        return entry.get("data", {})
    try:
        url = STOOQ_DAILY_URL.format(symbol=symbol.lower())
        raw = _http_get(url).decode("utf-8", errors="replace")
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            raise ValueError("no data")
        header = [h.lower() for h in lines[0].split(",")]
        rows = [dict(zip(header, l.split(","))) for l in lines[1:]]
        rows = [r for r in rows if r.get("close", "null") not in ("null", "", "N/A")]
        if not rows:
            raise ValueError("all null")
        closes = [float(r["close"]) for r in rows[-60:] if r.get("close") not in ("null", "")]
        volumes = [float(r.get("volume", 0) or 0) for r in rows[-60:] if r.get("volume") not in ("null", "")]
        price = closes[-1] if closes else 0.0
        avg_vol = sum(volumes) / len(volumes) if volumes else 0.0
        data = {"price": price, "avg_vol": avg_vol}
        quote_cache[symbol] = {"ts": now, "data": data}
        time.sleep(0.12)
        return data
    except Exception:
        quote_cache[symbol] = {"ts": now, "data": {}}
        return {}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_income(text_lower: str, title_lower: str) -> tuple[int, int, list[str]]:
    """Return (dividend_score, quality_score, positive_tags)."""
    combined = f"{title_lower} {text_lower}"
    tags: list[str] = []

    div_score = 0
    for kw in POS_INCOME:
        if kw in combined:
            div_score += 2
            tags.append(f"+{kw.replace(' ', '_')}")
            if div_score >= 8:
                break

    qual_score = 0
    for kw in POS_QUALITY:
        if kw in combined:
            qual_score += 1
            tags.append(f"+{kw.replace(' ', '_')}")
            if qual_score >= 4:
                break

    # Defensive sector bonus
    for kw in DEFENSIVE_KEYWORDS:
        if kw in combined:
            qual_score += 1
            tags.append("+defensive_sector")
            break

    # Negative penalty
    for kw in NEG_INCOME:
        if kw in combined:
            div_score = max(0, div_score - 3)
            tags.append(f"-{kw.replace(' ', '_')}")
            break

    return div_score, qual_score, list(dict.fromkeys(tags))  # dedupe


# ---------------------------------------------------------------------------
# Investability quality gate for income investors
# Conservative thresholds: larger companies, stable price, decent volume
# ---------------------------------------------------------------------------

MIN_PRICE = 5.0       # exclude penny stocks
MIN_AVG_VOL = 200_000  # some liquidity required
MIN_MCAP_PROXY = 0    # we don't have direct mcap here; use price*vol as proxy signal


def passes_quality_gate(price: float, avg_vol: float) -> bool:
    if price < MIN_PRICE:
        return False
    if avg_vol < MIN_AVG_VOL:
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT.exists():
        print("classify_sec_income: input not found, skipping")
        return

    with INPUT.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Deduplicate by ticker — keep most recent
    seen_tickers: dict[str, dict] = {}
    for row in rows:
        t = row.get("ticker", "").strip().upper()
        if not t or len(t) < 1 or len(t) > 5:
            continue
        # Skip warrants, preferred, units
        if "-" in t or t.endswith(("WW", "WS", "WT")) or (len(t) >= 5 and t.endswith("W")):
            continue
        if t not in seen_tickers:
            seen_tickers[t] = row

    filing_cache = load_cache()
    quote_cache = load_quote_cache()

    results: list[dict] = []

    for ticker, row in seen_tickers.items():
        link = row.get("link", "")
        title = row.get("title", "")
        form = row.get("form", "")

        title_lower = title.lower()

        # Fast pre-filter: skip if no income keyword in title at all
        # (avoid fetching full text for clearly irrelevant filings)
        title_has_signal = any(kw in title_lower for kw in [
            "dividend", "buyback", "repurchase", "debt", "yield", "income",
            "cash return", "share repurchase", "buyback",
        ])

        text = ""
        if link and (title_has_signal or form in ("8-K", "6-K")):
            text = fetch_filing_text(link, filing_cache)

        text_lower = text.lower()

        div_score, qual_score, tags = score_income(text_lower, title_lower)
        total_score = div_score + qual_score

        # Must have at least one dividend or quality signal
        if total_score < 2:
            continue

        # Has a risk flag — skip entirely
        combined = f"{title_lower} {text_lower}"
        if any(neg in combined for neg in [
            "going concern", "bankruptcy", "chapter 11", "delist", "non-compliance"
        ]):
            continue

        # Market data
        qdata = fetch_stooq_quote(ticker, quote_cache)
        price = qdata.get("price", 0.0)
        avg_vol = qdata.get("avg_vol", 0.0)

        if price > 0 and not passes_quality_gate(price, avg_vol):
            continue

        recency = row.get("recency_min", "")

        results.append({
            "ticker": ticker,
            "form": form,
            "income_score": total_score,
            "dividend_score": div_score,
            "quality_score": qual_score,
            "tags": ",".join(tags),
            "price": f"{price:.2f}" if price > 0 else "",
            "avg_vol_3m": f"{avg_vol:.0f}" if avg_vol > 0 else "",
            "recency_min": recency,
            "link": link,
        })

    save_cache(filing_cache)
    save_quote_cache(quote_cache)

    # Sort by income_score desc, then dividend_score desc
    results.sort(key=lambda r: (int(r["income_score"]), int(r["dividend_score"])), reverse=True)
    results = results[:25]

    fieldnames = ["ticker", "form", "income_score", "dividend_score", "quality_score",
                  "tags", "price", "avg_vol_3m", "recency_min", "link"]

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    with OUT_TXT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(r["ticker"] + "\n")

    print(f"classify_sec_income: {len(results)} income picks → {OUT_CSV.name}")


if __name__ == "__main__":
    main()
