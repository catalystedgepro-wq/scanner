#!/usr/bin/env python3
"""build_asx_announcements.py — ASX price-sensitive announcements tape.

Australian Stock Exchange announcements are the clearest corporate-
catalyst feed outside the US.  Relevant readthrough for ADR-holders
and commodity cycles:

- BHP / RIO / FMG (iron ore, copper) → VALE / FCX / CLF
- CBA / NAB / ANZ / WBC (big-four banks) → GS / MS financial beta
- CSL / COH / RMD (healthcare) → ABT / TMO / MDT
- WES / COL / WOW (retail) → WMT / KR
- TCL / QAN / TLS (infra/telco) → consumer Aussie demand signal

The `isPriceSensitive` flag is ASX-enforced under Listing Rule 3.1 —
it is the highest-signal single bit on this feed.

Source: asx.api.markitdigital.com/asx-research/1.0/companies
Output: asx_announcements.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_asx_announcements.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT_CSV = ROOT / "docs/asx_announcements.csv"
OUT_JSON = ROOT / "docs/data/asx_panels.json"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://asx.api.markitdigital.com/asx-research/1.0/companies"

# Top-30 ASX tickers by market cap / catalyst flow.
TICKERS = [
    "BHP", "CBA", "CSL", "NAB", "WBC", "ANZ", "FMG", "WES",
    "MQG", "RIO", "TLS", "WOW", "WDS", "GMG", "TCL", "ALL",
    "COL", "QBE", "STO", "SUN", "REA", "RMD", "COH", "XRO",
    "JHX", "ORG", "NEM", "BXB", "QAN", "JBH",
]

PER_TICKER_COUNT = 10


def _get_json(url: str) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"asx_announcements: {url[-40:]}: {e}")
        return None


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    cutoff = now - dt.timedelta(days=14)
    rows: list[dict] = []

    for i, ticker in enumerate(TICKERS):
        url = (f"{BASE}/{ticker}/announcements"
               f"?count={PER_TICKER_COUNT}&market_sensitive=true")
        payload = _get_json(url)
        if not isinstance(payload, dict):
            continue
        data = payload.get("data") or {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        for ann in items:
            if not isinstance(ann, dict):
                continue
            date_str = (ann.get("date") or "")[:19]
            try:
                d = dt.datetime.fromisoformat(date_str.replace("Z", ""))
                d = d.replace(tzinfo=dt.timezone.utc)
            except Exception:
                d = None
            if d and d < cutoff:
                continue
            rows.append({
                "ticker": ticker,
                "date": date_str,
                "type": (ann.get("announcementType") or "")[:60],
                "headline": (ann.get("headline") or "")[:240],
                "price_sensitive": ("1" if ann.get("isPriceSensitive")
                                    else "0"),
                "doc_key": (ann.get("documentKey") or "")[:60],
                "file_size": (ann.get("fileSize") or "")[:20],
                "captured_at": now_iso,
            })
        if i % 5 == 4:
            time.sleep(0.3)  # polite to markit digital

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"asx_announcements: no fetch, keeping "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["price_sensitive"] == "0", r["date"]),
              reverse=False)
    # Actually want: price_sensitive first, then newest first.
    rows.sort(key=lambda r: (-int(r["price_sensitive"]), r["date"]),
              reverse=True)
    # Simpler: two-key sort — price_sensitive desc, date desc.
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows.sort(key=lambda r: r["price_sensitive"], reverse=True)

    fieldnames = ["ticker", "date", "type", "headline",
                  "price_sensitive", "doc_key", "file_size",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    ps = sum(1 for r in rows if r["price_sensitive"] == "1")
    per_tk: dict[str, int] = {}
    for r in rows:
        per_tk[r["ticker"]] = per_tk.get(r["ticker"], 0) + 1
    top = " ".join(f"{k}={v}" for k, v in
                   sorted(per_tk.items(), key=lambda x: -x[1])[:5])

    # JSON panel for /international/ consumption
    payload = {
        "generated_at": now_iso,
        "source": "Markit Digital ASX Research v1.0",
        "exchange": "ASX",
        "country_iso": "AUS",
        "count": len(rows),
        "price_sensitive_count": ps,
        "top_per_ticker": dict(sorted(per_tk.items(), key=lambda x: -x[1])[:15]),
        "top_price_sensitive": [r for r in rows if r["price_sensitive"] == "1"][:30],
        "recent": rows[:50],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    print(f"asx_announcements: {len(rows)} filings | "
          f"price_sensitive={ps} | top[{top}]")


if __name__ == "__main__":
    main()
