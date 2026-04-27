#!/usr/bin/env python3
"""build_hkex_news.py — Hong Kong HKEX news scanner via yfinance.

Same shape as build_rns_uk.py but for HKEX-listed names. Pulls Yahoo's
aggregated news per ticker (Tencent, Alibaba, Meituan, ICBC, etc.).

Output:
  docs/hkex_news.csv
  docs/data/hkex_panels.json
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

warnings.filterwarnings("ignore")
import yfinance as yf  # noqa: E402


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_hkex_news.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/hkex_news.csv"
OUT_JSON = ROOT / "docs/data/hkex_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 6
TICKERS = [
    ("0700.HK", "Tencent"), ("9988.HK", "Alibaba"), ("3690.HK", "Meituan"),
    ("0939.HK", "China Construction Bank"), ("0941.HK", "China Mobile"),
    ("1299.HK", "AIA Group"), ("1398.HK", "ICBC"), ("2318.HK", "Ping An"),
    ("3988.HK", "Bank of China"), ("0883.HK", "CNOOC"), ("0005.HK", "HSBC HK"),
    ("1810.HK", "Xiaomi"), ("9618.HK", "JD.com"), ("9999.HK", "NetEase"),
    ("2020.HK", "Anta Sports"), ("2628.HK", "China Life"), ("0388.HK", "HKEX"),
    ("0017.HK", "New World Dev"), ("2382.HK", "Sunny Optical"),
    ("9888.HK", "Baidu"),
]

KIND_PATTERNS = [
    ("results",         r"results|interim|annual report|earnings|profit"),
    ("dividend",        r"dividend|distribution"),
    ("buyback",         r"buyback|repurchase"),
    ("merger",          r"merger|acquisition|combine|takeover"),
    ("regulatory",      r"regulatory|sanction|fine|investigation|antitrust"),
    ("listing_event",   r"listing|spin.?off|secondary listing"),
    ("trading_halt",    r"trading halt|suspension"),
    ("guidance_update", r"guidance|outlook|forecast"),
    ("partnership",     r"partner|collaboration|joint venture|jv"),
]


def classify(h: str) -> str:
    t = (h or "").lower()
    for kind, pattern in KIND_PATTERNS:
        if re.search(pattern, t):
            return kind
    return "other"


def fetch_news(item):
    ticker, name = item
    out = []
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
    except Exception:
        return out
    for n in news[:8]:
        c = n.get("content") if isinstance(n.get("content"), dict) else n
        title = c.get("title") or n.get("title") or ""
        ts = n.get("providerPublishTime") or c.get("pubDate") or c.get("displayTime") or 0
        if isinstance(ts, (int, float)) and ts > 0:
            published = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat(timespec="seconds")
        else:
            published = str(ts) if ts else ""
        link = (c.get("canonicalUrl", {}).get("url")
                if isinstance(c.get("canonicalUrl"), dict) else None) \
            or n.get("link") or ""
        publisher = (c.get("provider", {}).get("displayName")
                     if isinstance(c.get("provider"), dict) else None) or n.get("publisher") or ""
        if not title:
            continue
        out.append({
            "ticker": ticker, "company": name,
            "exchange": "HKEX", "country_iso": "HKG",
            "headline": title[:200],
            "kind": classify(title),
            "publisher": (publisher or "")[:60],
            "issued_at": published,
            "url": (link or "")[:300],
        })
    return out


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for batch in ex.map(fetch_news, TICKERS):
            rows.extend(batch)

    by_kind: dict = defaultdict(int)
    for r in rows:
        r["captured_at"] = captured
        by_kind[r["kind"]] += 1
    rows.sort(key=lambda r: r.get("issued_at", ""), reverse=True)
    rows = rows[:300]

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    payload = {
        "generated_at": captured,
        "source": "Yahoo Finance news per HKEX ticker",
        "exchange": "HKEX", "country_iso": "HKG",
        "count": len(rows),
        "by_kind": dict(by_kind),
        "recent": rows[:50],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    top = sorted(by_kind.items(), key=lambda x: -x[1])[:5]
    print(f"hkex_news: {len(rows)} headlines | top kinds: {top}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
