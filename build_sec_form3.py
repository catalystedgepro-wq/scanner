#!/usr/bin/env python3
"""build_sec_form3.py — EDGAR Form 3 initial ownership tape.

Form 3 is the FIRST insider filing: the statement of initial
beneficial ownership filed by a new director, officer, or 10%
holder within 10 days of becoming subject to Section 16. Unlike
Form 4 (transaction-based), Form 3 flags the arrival of a new
insider — a signal of executive churn, board refresh, or
activist 10% stake accumulation.

Economic readthrough:
- Multiple Form 3 clustered on a ticker -> board rebuild or
  management refresh (often precedes Form 4 buying cluster).
- Named 10% holder -> activist campaign or concentrated
  strategic stake.
- Director departures are also reflected (Form 3 is filed for
  the replacement, giving us the arrival date).

Source: SEC EDGAR full-text search
https://efts.sec.gov/LATEST/search-index?forms=3

Output: sec_form3.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_form3.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"


def _fetch(d_from: str, d_to: str, page: int = 1) -> dict:
    qs = urllib.parse.urlencode({
        "q": "",
        "dateRange": "custom",
        "startdt": d_from,
        "enddt": d_to,
        "forms": "3",
        "from": (page - 1) * 100,
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sec_form3: fetch p{page} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=14)).isoformat()
    d_to = today.isoformat()

    all_hits: list[dict] = []
    for page in (1, 2, 3, 4, 5):
        j = _fetch(d_from, d_to, page)
        hits = j.get("hits", {}).get("hits", [])
        if not hits:
            break
        all_hits.extend(hits)
        if len(hits) < 100:
            break

    if not all_hits:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_form3: no hits, keeping {OUT_CSV.name}")
        return

    by_ticker: dict[str, dict] = {}
    rows: list[dict] = []
    for h in all_hits:
        src = h.get("_source", {})
        ciks = src.get("ciks") or []
        names = src.get("display_names") or []
        period = src.get("period_ending", "")
        filed = src.get("file_date", "")
        # Extract ticker from any "(TICK)" substring in display_names
        ticker = ""
        issuer = ""
        for n in names:
            m = re.search(r"\(([A-Z\.\-]{1,6})\)", n)
            if m and not ticker:
                ticker = m.group(1)
            if "CIK" not in n and not issuer:
                issuer = n
        insider = ""
        for n in names:
            if "(CIK" in n and not insider:
                insider = n[:60]
        rows.append({
            "filed": filed or period,
            "period": period,
            "ticker": ticker,
            "issuer": issuer[:60],
            "insider": insider,
            "ciks": "|".join(ciks[:2])[:50],
        })
        if ticker:
            by_ticker.setdefault(ticker, {
                "count": 0,
                "insiders": set(),
            })
            by_ticker[ticker]["count"] += 1
            by_ticker[ticker]["insiders"].add(insider[:40])

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_form3: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "period", "ticker", "issuer", "insider",
                  "ciks", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    clusters = sorted(by_ticker.items(),
                       key=lambda kv: -kv[1]["count"])[:5]
    cb = " | ".join(f"{t}:{v['count']}" for t, v in clusters)
    with_t = sum(1 for r in rows if r["ticker"])
    print(f"sec_form3: {len(rows)} 14d ({with_t} tagged) | "
          f"top new-insider clusters: [{cb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
