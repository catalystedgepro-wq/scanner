#!/usr/bin/env python3
"""build_jse_africa.py — Africa catalyst news (JSE + ADRs + key sub-Saharan).

Covers South Africa (.JO), African ADRs trading on NYSE/NASDAQ, plus the
biggest sub-Saharan names (Nigeria, Kenya, Morocco, Egypt) where Yahoo
news is available.

Output: docs/jse_africa.csv + docs/data/africa_panels.json
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
        if (cand / "build_jse_africa.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/jse_africa.csv"
OUT_JSON = ROOT / "docs/data/africa_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 6
TICKERS = [
    # South Africa — JSE
    ("NPN.JO", "Naspers", "ZAF"), ("MTN.JO", "MTN Group", "ZAF"),
    ("SBK.JO", "Standard Bank", "ZAF"), ("FSR.JO", "FirstRand", "ZAF"),
    ("AGL.JO", "Anglo American JO", "ZAF"), ("SOL.JO", "Sasol", "ZAF"),
    ("BHP.JO", "BHP JO", "ZAF"), ("VOD.JO", "Vodacom", "ZAF"),
    # South Africa ADRs trading on US exchanges (gold + tech + telecom)
    ("AU", "AngloGold Ashanti ADR", "ZAF"),
    ("GFI", "Gold Fields ADR", "ZAF"),
    ("SBSW", "Sibanye-Stillwater ADR", "ZAF"),
    ("HMY", "Harmony Gold ADR", "ZAF"),
    ("SSL", "Sasol ADR", "ZAF"),
    # Nigeria — NSX Lagos
    ("DANGCEM.LG", "Dangote Cement", "NGA"),
    ("MTNN.LG", "MTN Nigeria", "NGA"),
    # Kenya — NSE Nairobi
    ("SCOM.NR", "Safaricom", "KEN"),
    ("EQTY.NR", "Equity Group", "KEN"),
    # Morocco — Casablanca SE
    ("ATW.MA", "Attijariwafa Bank", "MAR"),
    ("IAM.MA", "Maroc Telecom", "MAR"),
    # Egypt — EGX
    ("COMI.CR", "Commercial International Bank", "EGY"),
    ("HRHO.CR", "EFG Hermes Holding", "EGY"),
]

KIND_PATTERNS = [
    ("results",       r"results|earnings|profit"),
    ("dividend",      r"dividend|distribution"),
    ("merger",        r"merger|acquisition|takeover|stake"),
    ("regulatory",    r"regulator|sebi|cma|nse|investigation"),
    ("commodity",     r"gold|copper|platinum|coal|mining"),
    ("guidance",      r"guidance|outlook|forecast"),
]


def classify(h):
    t = (h or "").lower()
    for k, p in KIND_PATTERNS:
        if re.search(p, t):
            return k
    return "other"


def fetch_news(item):
    ticker, name, iso = item
    out = []
    try:
        news = yf.Ticker(ticker).news or []
    except Exception:
        return out
    for n in news[:6]:
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
            "exchange": "AFRICA-MULTI", "country_iso": iso,
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
    by_country = defaultdict(int)
    for r in rows:
        r["captured_at"] = captured
        by_kind[r["kind"]] += 1
        by_country[r["country_iso"]] += 1
    rows.sort(key=lambda r: r.get("issued_at", ""), reverse=True)
    rows = rows[:300]
    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    OUT_JSON.write_text(json.dumps({
        "generated_at": captured,
        "source": "Yahoo Finance news per JSE + African ADR ticker",
        "continent": "Africa",
        "count": len(rows),
        "by_country": dict(by_country),
        "by_kind": dict(by_kind),
        "recent": rows[:50],
    }, indent=2))
    print(f"jse_africa: {len(rows)} headlines | countries: {dict(by_country)} | "
          f"top kinds: {sorted(by_kind.items(), key=lambda x: -x[1])[:3]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
