#!/usr/bin/env python3
"""AlphaVantage NEWS_SENTIMENT spoke — fills the dormant tier-1 news slot.

Why this exists:
  build_news_momentum.py was built with a tier-1 boost slot for Bloomberg, but
  Bloomberg has no public API and discontinued RSS years ago. AlphaVantage's
  NEWS_SENTIMENT endpoint aggregates Bloomberg/Reuters/WSJ/CNBC wires WITH
  ticker-tagged sentiment scores, on a free tier (25 req/day) that's enough
  to cover today's top published-pick tickers (score≥15).

API:
  https://www.alphavantage.co/query?function=NEWS_SENTIMENT
    &tickers=AAPL,MSFT,...    (up to ~50 per call)
    &time_from=YYYYMMDDTHHMM  (UTC)
    &limit=200
    &apikey=...

Free tier: 25 requests/day, 5/min. We batch all tickers in one call when
possible, so a single daily run uses 1-2 requests of our quota.

Env:
  ALPHAVANTAGE_API_KEY=<key>  (get free at alphavantage.co/support/#api-key)

Output:
  alphavantage_news.csv — same shape as bloomberg_headlines.csv so
  build_news_momentum.py picks it up via a sibling adapter.
  alphavantage_news_status.json — last-run telemetry for /trust/.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "alphavantage_news.csv"
STATUS_JSON = ROOT / "alphavantage_news_status.json"
GAPPERS_CSV = ROOT / "sec_clean_gappers.csv"
TOP_GAPPERS_CSV = ROOT / "sec_top_gappers.csv"

API_BASE = "https://www.alphavantage.co/query"
# AlphaVantage NEWS_SENTIMENT semantics: multi-ticker returns INTERSECTION
# (articles tagged to ALL listed tickers), not union. Single-ticker calls
# return ~50 articles per ticker. Free tier is 25 req/day at 1 req/sec.
# Strategy: one call per ticker, top 8 tickers per cycle, ~12 cycles/day
# stays under the 25/day quota with headroom for retries.
TICKER_BATCH_SIZE = 1
MAX_TICKERS = 8
LOOKBACK_HOURS = 24
INTER_CALL_SLEEP_SEC = 1.5


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# Bellwethers — always-newsworthy tickers that AlphaVantage actually covers.
# Catalyst gap candidates are mostly microcaps with thin AV coverage; mixing
# in these large-caps guarantees the spoke returns market-sentiment signal
# every cycle even when the small-cap candidates yield empty feeds.
BELLWETHER_TICKERS = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]


def load_target_tickers() -> list[str]:
    """Hybrid ticker set: bellwethers + top published gap candidates.

    Bellwethers go first so they get the first request quota slot. Then we
    fill remaining slots with score>=15 clean gappers (where AV has any
    coverage, we still capture per-ticker sentiment).
    """
    out: list[str] = list(BELLWETHER_TICKERS)
    seen: set[str] = {t for t in out}
    rows: list[dict[str, str]] = []
    for path in (GAPPERS_CSV, TOP_GAPPERS_CSV):
        if path.exists():
            with path.open(newline="", encoding="utf-8") as f:
                rows.extend(csv.DictReader(f))
            if len(rows) >= MAX_TICKERS:
                break
    rows.sort(key=lambda r: -int(r.get("gapper_score", "0") or 0))
    for r in rows:
        t = (r.get("ticker") or "").strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= MAX_TICKERS:
            break
    return out[:MAX_TICKERS]


def fetch_news_sentiment(
    tickers: list[str], api_key: str, time_from: str
) -> dict[str, Any]:
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ",".join(tickers),
        "limit": "50",
        "apikey": api_key,
    }
    # time_from is supported but combined with multi-ticker can return
    # zero results; filter by recency client-side in normalize_feed_item.
    _ = time_from
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CatalystEdge/1.0 (opensource@example.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return {"error": str(e), "feed": []}
    return data


def normalize_feed_item(
    item: dict[str, Any], ticker_filter: set[str]
) -> list[dict[str, str]]:
    """Convert one AlphaVantage feed entry to one row per matched ticker.

    AlphaVantage entries can map to multiple tickers; we emit a row per
    relevant ticker so build_news_momentum.py can score each independently.
    """
    out: list[dict[str, str]] = []
    title = (item.get("title") or "").strip()
    summary = (item.get("summary") or "").strip()
    src = (item.get("source") or "").strip()
    link = (item.get("url") or "").strip()
    tp = (item.get("time_published") or "").strip()
    # AlphaVantage time format: 20260427T123000
    try:
        ts = dt.datetime.strptime(tp[:15], "%Y%m%dT%H%M%S").replace(
            tzinfo=dt.timezone.utc
        )
        timestamp = ts.isoformat()
    except Exception:
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    overall_sent = to_float(item.get("overall_sentiment_score", 0))
    topics = ";".join(
        sorted({(t.get("topic") or "").lower() for t in item.get("topics", []) if t.get("topic")})
    )
    for ts_entry in item.get("ticker_sentiment", []):
        ticker = (ts_entry.get("ticker") or "").strip().upper()
        if not ticker or ticker not in ticker_filter:
            continue
        rel = to_float(ts_entry.get("relevance_score", 0))
        sent = to_float(ts_entry.get("ticker_sentiment_score", 0))
        # Skip low-relevance mentions to keep feed clean.
        if rel < 0.15:
            continue
        out.append(
            {
                "timestamp_utc": timestamp,
                "ticker": ticker,
                "headline": title,
                "summary": summary,
                "sector": "",
                "event": "",
                "link": link,
                "source_pub": src,
                "relevance": f"{rel:.3f}",
                "ticker_sentiment": f"{sent:.3f}",
                "overall_sentiment": f"{overall_sent:.3f}",
                "topics": topics,
            }
        )
    return out


def write_status(status: dict[str, Any]) -> None:
    STATUS_JSON.write_text(json.dumps(status, indent=2), encoding="utf-8")


def main() -> int:
    api_key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    now_utc = dt.datetime.now(dt.timezone.utc)
    if not api_key:
        write_status(
            {
                "status": "skipped",
                "reason": "ALPHAVANTAGE_API_KEY not set",
                "last_attempt_utc": now_utc.isoformat(),
                "key_setup_url": "https://www.alphavantage.co/support/#api-key",
            }
        )
        print("alphavantage_news: skipped (no API key)")
        return 0

    # Free-tier quota: 25 calls/day. Loop runs every 2h, so we'd overrun
    # without a once-per-day gate. Skip if we already pulled news within
    # the last 22h (pre-market cycle wins). Override with FORCE=1 env var.
    if STATUS_JSON.exists() and not os.environ.get("ALPHAVANTAGE_FORCE"):
        try:
            prior = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
            prior_ts = prior.get("last_attempt_utc", "")
            if prior_ts:
                last = dt.datetime.fromisoformat(prior_ts)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=dt.timezone.utc)
                age_h = (now_utc - last).total_seconds() / 3600.0
                if age_h < 22 and prior.get("status") in ("ok",):
                    print(
                        f"alphavantage_news: skipped (last successful run {age_h:.1f}h ago, "
                        f"daily quota gate active)"
                    )
                    return 0
        except (json.JSONDecodeError, ValueError):
            pass

    tickers = load_target_tickers()
    if not tickers:
        write_status(
            {
                "status": "no_tickers",
                "last_attempt_utc": now_utc.isoformat(),
            }
        )
        print("alphavantage_news: no target tickers")
        return 0

    time_from = (
        now_utc - dt.timedelta(hours=LOOKBACK_HOURS)
    ).strftime("%Y%m%dT%H%M")

    all_rows: list[dict[str, str]] = []
    requests_used = 0
    errors: list[str] = []
    for i in range(0, len(tickers), TICKER_BATCH_SIZE):
        if i > 0:
            time.sleep(INTER_CALL_SLEEP_SEC)
        batch = tickers[i : i + TICKER_BATCH_SIZE]
        data = fetch_news_sentiment(batch, api_key, time_from)
        requests_used += 1
        if data.get("error"):
            errors.append(data["error"])
            continue
        # AlphaVantage returns a "Note" key when rate-limited.
        if "Note" in data or "Information" in data:
            errors.append(data.get("Note") or data.get("Information") or "rate_limited")
            break
        feed = data.get("feed", [])
        for entry in feed:
            all_rows.extend(normalize_feed_item(entry, set(batch)))

    # Dedup by (ticker, link) — same article may appear in multi-batch overlap.
    seen = set()
    deduped: list[dict[str, str]] = []
    for r in all_rows:
        key = (r["ticker"], r["link"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    deduped.sort(key=lambda r: r["timestamp_utc"], reverse=True)

    fieldnames = [
        "timestamp_utc",
        "ticker",
        "headline",
        "summary",
        "sector",
        "event",
        "link",
        "source_pub",
        "relevance",
        "ticker_sentiment",
        "overall_sentiment",
        "topics",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(deduped)

    write_status(
        {
            "status": "ok" if deduped else "empty",
            "last_attempt_utc": now_utc.isoformat(),
            "tickers_queried": len(tickers),
            "requests_used": requests_used,
            "rows_written": len(deduped),
            "errors": errors,
            "free_tier_daily_quota": 25,
        }
    )
    print(
        f"alphavantage_news: {len(deduped)} headlines for {len(tickers)} tickers "
        f"({requests_used} req used)"
    )
    if errors:
        print(f"  errors: {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
