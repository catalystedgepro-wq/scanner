#!/usr/bin/env python3
"""build_rns_uk.py — UK LSE RNS announcement scanner via yfinance news.

The London Stock Exchange's RNS feed sits behind anti-bot protection. yfinance
exposes Yahoo's news endpoint per ticker, which aggregates RNS publications
for UK-listed names. This is the most reliable free source.

Output:
  docs/rns_uk_announcements.csv
  docs/data/rns_panels.json
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
        if (cand / "build_rns_uk.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/rns_uk_announcements.csv"
OUT_JSON = ROOT / "docs/data/rns_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 6

# Top FTSE 100 + AIM names that move on RNS catalysts
TICKERS = [
    ("SHEL.L", "Shell"), ("AZN.L", "AstraZeneca"), ("HSBA.L", "HSBC"),
    ("BP.L", "BP"), ("ULVR.L", "Unilever"), ("GSK.L", "GSK"),
    ("RIO.L", "Rio Tinto"), ("BARC.L", "Barclays"), ("LLOY.L", "Lloyds"),
    ("NWG.L", "NatWest"), ("VOD.L", "Vodafone"), ("DGE.L", "Diageo"),
    ("BATS.L", "BAT"), ("RKT.L", "Reckitt"), ("PRU.L", "Prudential"),
    ("AAL.L", "Anglo American"), ("GLEN.L", "Glencore"), ("REL.L", "RELX"),
    ("EXPN.L", "Experian"), ("CRH.L", "CRH"), ("STAN.L", "Standard Chartered"),
    ("BT-A.L", "BT Group"), ("ITV.L", "ITV"), ("MNG.L", "M&G"),
    ("CNA.L", "Centrica"), ("SSE.L", "SSE"), ("OCDO.L", "Ocado"),
    ("RR.L", "Rolls-Royce"), ("BA.L", "BAE Systems"), ("CCH.L", "Coca-Cola HBC"),
]

KIND_PATTERNS = [
    ("results",            r"results|interim|annual report|trading update|preliminary|profit"),
    ("director_dealings",  r"director.?s? deal|pdmr|notification of trans"),
    ("holdings",           r"holdings? in company|major holding|tr-?1|stake"),
    ("dividend",           r"dividend|distribution|ex-?div|special payment"),
    ("capital_raise",      r"placing|share issue|capital raise|placement|subscription"),
    ("buyback",            r"share buyback|repurchase|buy.?back"),
    ("takeover_offer",     r"takeover|offer document|recommended offer|cash offer|bid"),
    ("merger",             r"merger|combination|acquires|to acquire"),
    ("board_change",       r"board change|director appoint|ceo|chairman|resignation"),
    ("trading_update",     r"trading update|guidance|outlook|forecast"),
    ("contract_won",       r"contract|awarded|wins"),
    ("agm",                r"agm|annual general meeting|notice of meeting"),
]


def classify(headline: str) -> str:
    t = (headline or "").lower()
    for kind, pattern in KIND_PATTERNS:
        if re.search(pattern, t):
            return kind
    return "other"


def fetch_news(item: tuple) -> list[dict]:
    ticker, name = item
    out = []
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
    except Exception:
        return out
    for n in news[:8]:
        # yfinance news shape varies — handle both old (top-level) and new (content) formats
        c = n.get("content") if isinstance(n.get("content"), dict) else n
        title = c.get("title") or n.get("title") or ""
        publish_ts = (n.get("providerPublishTime")
                      or c.get("pubDate")
                      or c.get("displayTime") or 0)
        if isinstance(publish_ts, (int, float)) and publish_ts > 0:
            published = dt.datetime.fromtimestamp(publish_ts, tz=dt.timezone.utc).isoformat(timespec="seconds")
        else:
            published = str(publish_ts) if publish_ts else ""
        link = (c.get("canonicalUrl", {}).get("url")
                if isinstance(c.get("canonicalUrl"), dict) else None) \
            or c.get("clickThroughUrl", {}).get("url") if isinstance(c.get("clickThroughUrl"), dict) else None \
            or n.get("link") or ""
        publisher = (c.get("provider", {}).get("displayName")
                     if isinstance(c.get("provider"), dict) else None) \
            or n.get("publisher") or ""
        if not title:
            continue
        out.append({
            "ticker": ticker, "company": name,
            "exchange": "LSE", "country_iso": "GBR",
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
        "source": "Yahoo Finance news per LSE ticker",
        "exchange": "LSE", "country_iso": "GBR",
        "count": len(rows),
        "by_kind": dict(by_kind),
        "recent": rows[:50],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    top = sorted(by_kind.items(), key=lambda x: -x[1])[:5]
    print(f"rns_uk: {len(rows)} headlines | top kinds: {top}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
