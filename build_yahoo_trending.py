#!/usr/bin/env python3
"""build_yahoo_trending.py — Yahoo Finance trending tickers (US + intl).

Retail attention signal. Yahoo Finance trending list is derived from
search + quote-page impressions. Strong leading indicator for:
- Meme-squeeze candidates (GME-style attention spikes)
- Upcoming-event anticipation (crypto rallies, earnings runs)
- Contagion plays (when sector leader trending, laggards follow)

Five geo endpoints: US, CA, GB, HK, IN. Merged into one CSV.

Output: yahoo_trending.csv
Columns: geo, rank, symbol, job_timestamp, captured_at

Source: query2.finance.yahoo.com/v1/finance/trending/{geo}
(no key, live, rate-limited but friendly to daily fetches).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "yahoo_trending.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
GEOS = ["US", "CA", "GB", "HK", "IN"]


def _fetch(geo: str) -> dict | None:
    url = f"https://query2.finance.yahoo.com/v1/finance/trending/{geo}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"yahoo_trending {geo}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    for geo in GEOS:
        d = _fetch(geo)
        if not d:
            continue
        results = (d.get("finance") or {}).get("result") or []
        if not results:
            continue
        r0 = results[0]
        quotes = r0.get("quotes") or []
        ts = r0.get("jobTimestamp", "")
        for idx, q in enumerate(quotes, start=1):
            sym = (q.get("symbol") or "").strip()
            if not sym:
                continue
            rows.append({
                "geo": geo,
                "rank": idx,
                "symbol": sym[:16],
                "job_timestamp": str(ts)[:20],
                "captured_at": now,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"yahoo_trending: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    fieldnames = ["geo", "rank", "symbol", "job_timestamp", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_geo: dict[str, list[str]] = {}
    for r in rows:
        by_geo.setdefault(r["geo"], []).append(r["symbol"])
    us_top = ",".join(by_geo.get("US", [])[:5])
    print(f"yahoo_trending: {len(rows)} rows across "
          f"{len(by_geo)} geos | US top5: {us_top} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
