#!/usr/bin/env python3
"""build_tdnet_jp.py — Japan TSE catalyst news via yfinance per .T ticker.

Same shape as build_rns_uk.py. Output:
  docs/tdnet_jp.csv
  docs/data/tdnet_panels.json
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
    for cand in (Path("/opt/catalyst"),
                 Path("/home/operator/.openclaw/workspace"),
                 Path(__file__).resolve().parent):
        if (cand / "build_tdnet_jp.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/tdnet_jp.csv"
OUT_JSON = ROOT / "docs/data/tdnet_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 6
TICKERS = [
    ("7203.T", "Toyota"), ("6758.T", "Sony"), ("9984.T", "SoftBank Group"),
    ("6861.T", "Keyence"), ("8306.T", "Mitsubishi UFJ"), ("9432.T", "NTT"),
    ("7974.T", "Nintendo"), ("6098.T", "Recruit"), ("8035.T", "Tokyo Electron"),
    ("4063.T", "Shin-Etsu"), ("6501.T", "Hitachi"), ("9433.T", "KDDI"),
    ("8316.T", "Sumitomo Mitsui FG"), ("9020.T", "JR East"), ("4502.T", "Takeda"),
    ("6594.T", "Nidec"), ("7733.T", "Olympus"), ("8058.T", "Mitsubishi Corp"),
    ("8001.T", "Itochu"), ("4661.T", "Oriental Land"),
    ("4519.T", "Chugai Pharma"), ("4503.T", "Astellas"),
    ("6981.T", "Murata"), ("7741.T", "HOYA"),
]

KIND_PATTERNS = [
    ("results",     r"results|earnings|profit|forecast|guidance"),
    ("dividend",    r"dividend|distribution"),
    ("buyback",     r"buyback|repurchase"),
    ("merger",      r"merger|acquisition|takeover|tender"),
    ("partnership", r"partner|collaboration|joint venture|alliance"),
    ("regulatory",  r"regulatory|investigation|sanction|fine"),
    ("guidance",    r"raises|cuts|revises|outlook"),
]


def classify(h):
    t = (h or "").lower()
    for k, p in KIND_PATTERNS:
        if re.search(p, t):
            return k
    return "other"


def fetch_news(item):
    ticker, name = item
    out = []
    try:
        news = yf.Ticker(ticker).news or []
    except Exception:
        return out
    for n in news[:8]:
        c = n.get("content") if isinstance(n.get("content"), dict) else n
        title = c.get("title") or n.get("title") or ""
        ts = n.get("providerPublishTime") or c.get("pubDate") or c.get("displayTime") or 0
        published = (dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat(timespec="seconds")
                     if isinstance(ts, (int, float)) and ts > 0 else (str(ts) if ts else ""))
        link = ""
        if isinstance(c.get("canonicalUrl"), dict): link = c["canonicalUrl"].get("url", "")
        if not link: link = n.get("link", "")
        publisher = ""
        if isinstance(c.get("provider"), dict): publisher = c["provider"].get("displayName", "")
        if not publisher: publisher = n.get("publisher", "")
        if not title:
            continue
        out.append({
            "ticker": ticker, "company": name,
            "exchange": "TSE", "country_iso": "JPN",
            "headline": title[:200], "kind": classify(title),
            "publisher": (publisher or "")[:60], "issued_at": published,
            "url": (link or "")[:300],
        })
    return out


def main():
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for batch in ex.map(fetch_news, TICKERS):
            rows.extend(batch)
    by_kind = defaultdict(int)
    for r in rows:
        r["captured_at"] = captured
        by_kind[r["kind"]] += 1
    rows.sort(key=lambda r: r.get("issued_at", ""), reverse=True)
    rows = rows[:300]
    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    OUT_JSON.write_text(json.dumps({
        "generated_at": captured,
        "source": "Yahoo Finance news per TSE ticker",
        "exchange": "TSE", "country_iso": "JPN",
        "count": len(rows), "by_kind": dict(by_kind),
        "recent": rows[:50],
    }, indent=2))
    print(f"tdnet_jp: {len(rows)} headlines | top kinds: {sorted(by_kind.items(), key=lambda x: -x[1])[:3]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
