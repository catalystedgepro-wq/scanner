#!/usr/bin/env python3
"""build_edgar_fts.py — SEC EDGAR full-text search red-flag phrases.

Live hits on institutional-grade red-flag phrases across all SEC filings
(10-K, 10-Q, 8-K, DEF 14A) posted in the last 30 days. Each phrase is
a known correlate of stock repricing:

- "material weakness"     → internal control deficiency → -3 to -8%
- "going concern"         → ongoing viability doubt    → -5 to -20%
- "restatement"           → prior-year earnings revision → -2 to -10%
- "sec investigation"     → enforcement action risk    → -5 to -15%
- "class action lawsuit"  → litigation disclosure      → -2 to -8%
- "covenant default"      → debt covenant breach       → -5 to -15%
- "impairment"            → asset write-down           → -1 to -8%
- "auditor resignation"   → control failure tell       → -5 to -20%
- "subpoena"              → DOJ/SEC heat              → -3 to -12%

Bullish tape phrases also tracked:
- "record revenue"        → guidance up                → +1 to +5%
- "strategic review"      → M&A-speak, breakup candidate → +3 to +15%

Source: efts.sec.gov/LATEST/search-index (free, no key).

Output: edgar_fts.csv
Columns: phrase, polarity, cik, ticker_hint, form, filed_date,
         period, adsh, score, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "edgar_fts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://efts.sec.gov/LATEST/search-index"

PHRASES = [
    ("material weakness",     "bear", "10-K,10-Q,8-K"),
    ("going concern",         "bear", "10-K,10-Q,8-K"),
    ("restatement",           "bear", "10-K,10-Q,8-K"),
    ("class action lawsuit",  "bear", "10-K,10-Q,8-K"),
    ("covenant default",      "bear", "10-K,10-Q,8-K"),
    ("auditor resignation",   "bear", "8-K"),
    ("subpoena",              "bear", "10-K,10-Q,8-K"),
    ("record revenue",        "bull", "8-K"),
    ("strategic review",      "bull", "8-K,DEF 14A"),
    ("exploring strategic alternatives", "bull", "8-K"),
]


def _search(phrase: str, forms: str) -> list:
    today = dt.date.today()
    start = today - dt.timedelta(days=30)
    qs = urllib.parse.urlencode({
        "q": f'"{phrase}"',
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": today.isoformat(),
        "forms": forms,
        "hits": 10,
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        hits = ((d.get("hits") or {}).get("hits") or [])
        return hits
    except Exception as e:
        print(f"edgar_fts \"{phrase[:20]}\": {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    seen: set[str] = set()

    for phrase, polarity, forms in PHRASES:
        hits = _search(phrase, forms)
        for h in hits:
            src = h.get("_source") or {}
            adsh = h.get("_id", "")
            key = f"{phrase}|{adsh}"
            if key in seen:
                continue
            seen.add(key)
            ciks = src.get("ciks") or []
            cik = ciks[0] if ciks else ""
            ticker_hint = (src.get("display_names") or [""])[0][:48]
            filed = (src.get("file_date") or "")[:10]
            period = (src.get("period_ending") or "")[:10]
            form = (src.get("form") or "")[:12]
            score = float(h.get("_score", 0) or 0)
            rows.append({
                "phrase": phrase,
                "polarity": polarity,
                "cik": str(cik).zfill(10) if cik else "",
                "ticker_hint": ticker_hint,
                "form": form,
                "filed_date": filed,
                "period": period,
                "adsh": adsh[:48],
                "score": f"{score:.2f}",
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"edgar_fts: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["phrase"], -float(r["score"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["phrase", "polarity", "cik", "ticker_hint", "form",
                  "filed_date", "period", "adsh", "score", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    bear = sum(1 for r in rows if r["polarity"] == "bear")
    bull = sum(1 for r in rows if r["polarity"] == "bull")
    per_phrase: dict[str, int] = {}
    for r in rows:
        per_phrase[r["phrase"]] = per_phrase.get(r["phrase"], 0) + 1
    top_phrase = max(per_phrase.items(), key=lambda kv: kv[1],
                     default=("?", 0))
    print(f"edgar_fts: {len(rows)} filings (30-d) | bear={bear} "
          f"bull={bull} | top phrase: \"{top_phrase[0]}\"="
          f"{top_phrase[1]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
