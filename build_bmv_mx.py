#!/usr/bin/env python3
"""build_bmv_mx.py — Mexico BMV catalyst news via yfinance per .MX ticker.

Output: docs/bmv_mx.csv + docs/data/bmv_panels.json
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
        if (cand / "build_bmv_mx.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/bmv_mx.csv"
OUT_JSON = ROOT / "docs/data/bmv_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 6
TICKERS = [
    ("WALMEX.MX", "Walmart Mexico"), ("AMXB.MX", "America Movil"),
    ("GFNORTEO.MX", "Banorte"), ("FEMSAUBD.MX", "FEMSA"),
    ("GMEXICOB.MX", "Grupo Mexico"), ("BIMBOA.MX", "Grupo Bimbo"),
    ("CEMEXCPO.MX", "Cemex"), ("TLEVISACPO.MX", "Televisa"),
    ("ALSEA.MX", "Alsea"), ("KIMBERA.MX", "Kimberly-Clark Mexico"),
    ("ALFAA.MX", "Alfa"), ("ELEKTRA.MX", "Elektra"),
]

KIND_PATTERNS = [
    ("results",       r"results|earnings|profit|trimestre|utilidad"),
    ("dividend",      r"dividend|distribution|reparto"),
    ("buyback",       r"buyback|repurchase|recompra"),
    ("merger",        r"merger|acquisition|adquisi|fusion"),
    ("regulatory",    r"cnbv|regulator|investigation|fine"),
    ("rating",        r"upgrade|downgrade|rating|moody|fitch"),
    ("guidance",      r"guidance|outlook|forecast"),
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
            "exchange": "BMV", "country_iso": "MEX",
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
        "source": "Yahoo Finance news per BMV ticker",
        "exchange": "BMV", "country_iso": "MEX",
        "count": len(rows), "by_kind": dict(by_kind),
        "recent": rows[:50],
    }, indent=2))
    print(f"bmv_mx: {len(rows)} headlines | top kinds: {sorted(by_kind.items(), key=lambda x: -x[1])[:3]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
