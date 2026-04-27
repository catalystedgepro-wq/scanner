#!/usr/bin/env python3
"""build_sec_form144.py — EDGAR Form 144 intent-to-sell restricted
stock tape.

Form 144 is the notice of *proposed* sale of restricted or control
securities under Rule 144. Unlike Form 4 (already-executed insider
sales), Form 144 is a FORWARD-looking signal — the insider has
declared intent to sell over the next 90 days. A Form 144 cluster
on a single ticker = incoming supply overhang.

Economic readthrough:
- Single large Form 144 -> -5bps to -50bps drift over 10d as
  the filer executes the sale under 10b5-1 or open-market.
- Cluster of Form 144 across multiple insiders on one ticker ->
  sharper supply overhang, often precedes cluster of Form 4
  sales and can coincide with share-price cap.
- Named 10% holder filing Form 144 -> distribution event, can
  break technical ranges.

Source: SEC EDGAR full-text search, forms=144
https://efts.sec.gov/LATEST/search-index

Output: sec_form144.csv
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
OUT_CSV = ROOT / "sec_form144.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"


def _fetch(d_from: str, d_to: str, page: int = 1) -> dict:
    qs = urllib.parse.urlencode({
        "q": "",
        "dateRange": "custom",
        "startdt": d_from,
        "enddt": d_to,
        "forms": "144",
        "from": (page - 1) * 100,
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sec_form144: fetch p{page} failed: {e}")
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
            print(f"sec_form144: no hits, keeping {OUT_CSV.name}")
        return

    by_ticker: dict[str, dict] = {}
    rows: list[dict] = []
    for h in all_hits:
        src = h.get("_source", {})
        ciks = src.get("ciks") or []
        names = src.get("display_names") or []
        filed = src.get("file_date", "")
        ticker = ""
        issuer = ""
        for n in names:
            m = re.search(r"\(([A-Z\.\-]{1,6})\)", n)
            if m and not ticker:
                ticker = m.group(1)
            if "CIK" in n and not issuer:
                issuer = n.split("  (")[0][:60]
        insider = ""
        for n in names[1:]:
            if "(CIK" in n and "(" not in n.split("(CIK")[0].strip():
                insider = n[:60]
                break
        if not insider and len(names) >= 2:
            insider = names[1][:60]
        rows.append({
            "filed": filed,
            "ticker": ticker,
            "issuer": issuer,
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
            print(f"sec_form144: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "ticker", "issuer", "insider", "ciks",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    clusters = sorted(by_ticker.items(),
                       key=lambda kv: -kv[1]["count"])[:5]
    cb = " | ".join(f"{t}:{v['count']}" for t, v in clusters)
    with_t = sum(1 for r in rows if r["ticker"])
    print(f"sec_form144: {len(rows)} 14d ({with_t} tagged) | "
          f"top supply-overhang: [{cb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
