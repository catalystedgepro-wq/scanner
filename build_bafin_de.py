#!/usr/bin/env python3
"""build_bafin_de.py — Germany DAX/MDAX news via yfinance per .DE ticker.

Same shape as build_rns_uk.py. Output:
  docs/bafin_de.csv
  docs/data/bafin_panels.json
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
        if (cand / "build_bafin_de.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/bafin_de.csv"
OUT_JSON = ROOT / "docs/data/bafin_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 6
TICKERS = [
    ("SAP.DE", "SAP"), ("SIE.DE", "Siemens"), ("DTE.DE", "Deutsche Telekom"),
    ("ALV.DE", "Allianz"), ("BAS.DE", "BASF"), ("BMW.DE", "BMW"),
    ("MBG.DE", "Mercedes-Benz"), ("VOW3.DE", "Volkswagen"), ("DBK.DE", "Deutsche Bank"),
    ("BAYN.DE", "Bayer"), ("RWE.DE", "RWE"), ("ENR.DE", "Siemens Energy"),
    ("ADS.DE", "Adidas"), ("MUV2.DE", "Munich Re"), ("HEN3.DE", "Henkel"),
    ("DPW.DE", "DHL"), ("IFX.DE", "Infineon"), ("DB1.DE", "Deutsche Boerse"),
    ("BEI.DE", "Beiersdorf"), ("FRE.DE", "Fresenius"),
]

KIND_PATTERNS = [
    ("results",       r"results|earnings|profit|gewinn|umsatz"),
    ("dividend",      r"dividend|distribution"),
    ("buyback",       r"buyback|repurchase|aktienrück"),
    ("merger",        r"merger|acquisition|übernahme|fusion"),
    ("regulatory",    r"regulator|bafin|investigation|fine"),
    ("ev_tech",       r"ev|electric|battery|chip|ai"),
    ("guidance",      r"guidance|outlook|prognose|ausblick"),
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
            "exchange": "XETRA", "country_iso": "DEU",
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
        "source": "Yahoo Finance news per XETRA ticker",
        "exchange": "XETRA", "country_iso": "DEU",
        "count": len(rows), "by_kind": dict(by_kind),
        "recent": rows[:50],
    }, indent=2))
    print(f"bafin_de: {len(rows)} headlines | top kinds: {sorted(by_kind.items(), key=lambda x: -x[1])[:3]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
