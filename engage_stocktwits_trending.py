#!/usr/bin/env python3
"""engage_stocktwits_trending.py — Engage StockTwits trending tickers.

Calls the public StockTwits trending API, cross-references our gap scanner
results, and posts relevant commentary to build followers organically.

Strategy:
- Tickers in our scanner AND trending: post gap/vol data as a new message
- Tickers trending only: fetch Yahoo Finance quote, post watchlist comment
- Max 8 posts per run, 12-second delay between posts
- Gate with .st_trending_{date}_{ticker} flags to avoid duplicate posts

Required env var:
  STOCKTWITS_ACCESS_TOKEN

Optional (loaded from .sec_email_env as fallback):
  NEWSLETTER_URL
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
GAP_CSV        = ROOT / "gap_scanner_top.csv"
GAPPERS_CSV    = ROOT / "sec_top_gappers.csv"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "catalystedge.agency")
API_BASE       = "https://api.stocktwits.com/api/2"
TRENDING_URL   = f"{API_BASE}/trending/symbols.json"
YAHOO_CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1m&range=1d"
)
MAX_POSTS      = 3    # reduced from 8 — stay under radar
POST_DELAY     = 45   # seconds between posts — human-paced


# ── Env / token ──────────────────────────────────────────────────────────────

def _load_env() -> None:
    """Load .sec_email_env into os.environ for local testing fallback."""
    env_file = ROOT / ".sec_email_env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v.strip()


def get_token() -> str:
    _load_env()
    token = os.environ.get("STOCKTWITS_ACCESS_TOKEN", "").strip()
    if not token:
        print("engage_stocktwits_trending: STOCKTWITS_ACCESS_TOKEN not set — skipping")
        raise SystemExit(0)
    return token


# ── Flag gating ──────────────────────────────────────────────────────────────

def already_posted(date_str: str, ticker: str) -> bool:
    return (ROOT / f".st_trending_{date_str}_{ticker}").exists()


def mark_posted(date_str: str, ticker: str) -> None:
    (ROOT / f".st_trending_{date_str}_{ticker}").touch()


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_scanner_tickers() -> dict[str, dict]:
    """Return {ticker: row_dict} for all tickers in our gap scanner CSVs."""
    result: dict[str, dict] = {}
    for csv_path in [GAP_CSV, GAPPERS_CSV]:
        if not csv_path.exists():
            continue
        try:
            with csv_path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker", "").strip().upper()
                    if t and t not in result:
                        result[t] = row
        except Exception:
            pass
    return result


# ── API calls ────────────────────────────────────────────────────────────────

def fetch_trending() -> list[str]:
    """Fetch StockTwits trending tickers (no auth required)."""
    req = urllib.request.Request(
        TRENDING_URL,
        headers={"User-Agent": "CatalystEdge/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        symbols = data.get("symbols", [])
        return [s.get("symbol", "").upper() for s in symbols if s.get("symbol")]
    except Exception as e:
        print(f"engage_stocktwits_trending: trending fetch error — {e}")
        return []


def fetch_yahoo_quote(symbol: str) -> dict | None:
    """Fetch a live quote via Yahoo Finance v8 chart endpoint."""
    url = YAHOO_CHART.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        meta   = result.get("meta", {})
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        price  = next((c for c in reversed(closes) if c is not None),
                      meta.get("regularMarketPrice", 0))
        prev   = meta.get("chartPreviousClose") or price
        chg    = ((price - prev) / prev * 100) if prev else 0
        return {
            "regularMarketPrice":         price,
            "regularMarketChangePercent": chg,
        }
    except Exception as e:
        print(f"  yahoo quote error {symbol}: {e}")
        return None


# ── Message builders ─────────────────────────────────────────────────────────

def build_scanner_message(ticker: str, row: dict) -> str:
    """Build message for a ticker that appeared in our scanner AND is trending."""
    gap_pct   = row.get("gap_pct", row.get("gap", ""))
    vol_ratio = row.get("vol_ratio", "")
    price     = row.get("price", "")

    try:
        gap_str = f"+{float(gap_pct):.1f}% gap" if gap_pct else ""
    except (ValueError, TypeError):
        gap_str = ""
    try:
        vol_str = f"{float(vol_ratio):.1f}x avg vol" if vol_ratio else ""
    except (ValueError, TypeError):
        vol_str = ""
    try:
        price_str = f"@ ${float(price):.2f}" if price else ""
    except (ValueError, TypeError):
        price_str = ""

    stats = " | ".join(s for s in [gap_str, vol_str] if s)

    lines = [
        f"${ticker} showed up on our pre-market gap scanner today {price_str}",
    ]
    if stats:
        lines.append(stats)
    lines.extend([
        "",
        f"Scanning 1,600+ tickers before open -> {NEWSLETTER_URL} | t.me/CatalystEdgePro",
    ])
    return "\n".join(lines)[:1000]


def build_watch_message(ticker: str, quote: dict) -> str | None:
    """Build message for a trending ticker NOT in our scanner."""
    try:
        price     = float(quote.get("regularMarketPrice") or 0)
        chg_pct   = float(quote.get("regularMarketChangePercent") or 0)
    except (TypeError, ValueError):
        return None

    if price <= 0:
        return None

    sign   = "+" if chg_pct >= 0 else ""
    chg_str = f"{sign}{chg_pct:.2f}%"

    body = (
        f"Watching ${ticker} -- currently ${price:.2f} ({chg_str}). "
        f"Running our gap scanner across 1,600 tickers before every open -> "
        f"{NEWSLETTER_URL} | t.me/CatalystEdgePro"
    )
    return body[:1000]


# ── StockTwits post ──────────────────────────────────────────────────────────

def post_stocktwits(token: str, body: str, sentiment: str) -> int | None:
    """Post a new message. Returns message ID or None on failure."""
    data = urllib.parse.urlencode({
        "access_token": token,
        "body":         body,
        "sentiment":    sentiment,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/messages/create.json",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent":   "CatalystEdge/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return result.get("message", {}).get("id")
    except urllib.error.HTTPError as e:
        print(f"  stocktwits error: {e.code} {e.read()[:150]}")
        return None
    except Exception as e:
        print(f"  stocktwits error: {e}")
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    token     = get_token()
    today_str = dt.date.today().isoformat()

    trending = fetch_trending()
    if not trending:
        print("engage_stocktwits_trending: no trending tickers fetched — skipping")
        return 0

    scanner_map = load_scanner_tickers()
    print(f"engage_stocktwits_trending: {len(trending)} trending, {len(scanner_map)} scanner tickers")

    posted = 0

    # --- Pass 1: Trending tickers also in our scanner ---
    for ticker in trending:
        if posted >= MAX_POSTS:
            break
        if already_posted(today_str, ticker):
            continue
        if ticker not in scanner_map:
            continue

        row  = scanner_map[ticker]
        body = build_scanner_message(ticker, row)
        mid  = post_stocktwits(token, body, "Bullish")

        if mid:
            mark_posted(today_str, ticker)
            print(f"  [scanner+trending] posted ${ticker} -> msg {mid}")
            posted += 1
            time.sleep(POST_DELAY)
        else:
            time.sleep(2)

    # --- Pass 2: Remaining trending tickers not in our scanner ---
    for ticker in trending:
        if posted >= MAX_POSTS:
            break
        if already_posted(today_str, ticker):
            continue
        if ticker in scanner_map:
            continue  # already handled above (or skipped)

        quote = fetch_yahoo_quote(ticker)
        if not quote:
            continue

        body = build_watch_message(ticker, quote)
        if not body:
            continue

        # Sentiment based on price direction
        try:
            chg = float(quote.get("regularMarketChangePercent") or 0)
            sentiment = "Bullish" if chg >= 0 else "Bearish"
        except (TypeError, ValueError):
            sentiment = "Bullish"

        mid = post_stocktwits(token, body, sentiment)

        if mid:
            mark_posted(today_str, ticker)
            print(f"  [trending-only] posted ${ticker} ({sentiment}) -> msg {mid}")
            posted += 1
            time.sleep(POST_DELAY)
        else:
            time.sleep(2)

    print(f"engage_stocktwits_trending: {posted} post(s) made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
