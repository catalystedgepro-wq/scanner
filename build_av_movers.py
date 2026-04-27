#!/usr/bin/env python3
"""build_av_movers.py — Alpha Vantage US top movers (demo key).

Official Alpha Vantage `TOP_GAINERS_LOSERS` endpoint returns:
- top 20 gainers (pct_change desc)
- top 20 losers  (pct_change asc)
- top 20 most actively traded (volume desc)

The demo key rate-limits to ~5 req/day but the data is complete and
refreshed at market close. Used as a CROSS-CHECK against our own
gappers list, and as a source for "squeeze / meme" candidates not
yet in SEC catalyst flow.

Output: av_movers.csv
Columns: category, rank, ticker, price, change_amount,
change_pct, volume, last_updated, captured_at

Source: alphavantage.co/query (no signup, demo key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "av_movers.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www.alphavantage.co/query"
       "?function=TOP_GAINERS_LOSERS&apikey=demo")


def _pct(s: str) -> str:
    if not s:
        return ""
    return s.replace("%", "").strip()


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"av_movers: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"av_movers: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(d, dict) or "Information" in d and "last_updated" not in d:
        # Rate-limited or error envelope.
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"av_movers: rate-limited, keeping existing {OUT_CSV.name}")
        return

    last_updated = d.get("last_updated", "")[:25]
    cats = [
        ("gainers", d.get("top_gainers") or []),
        ("losers",  d.get("top_losers")  or []),
        ("active",  d.get("most_actively_traded") or []),
    ]

    rows: list[dict] = []
    for cat, lst in cats:
        for idx, m in enumerate(lst, start=1):
            rows.append({
                "category": cat,
                "rank": idx,
                "ticker": (m.get("ticker") or "")[:12],
                "price": m.get("price", ""),
                "change_amount": m.get("change_amount", ""),
                "change_pct": _pct(m.get("change_percentage", "")),
                "volume": m.get("volume", ""),
                "last_updated": last_updated,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"av_movers: empty payload, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["category", "rank", "ticker", "price", "change_amount",
                  "change_pct", "volume", "last_updated", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top_g = next((r for r in rows if r["category"] == "gainers"), {})
    top_l = next((r for r in rows if r["category"] == "losers"), {})
    top_a = next((r for r in rows if r["category"] == "active"), {})
    print(f"av_movers: {len(rows)} rows (3 categories) | "
          f"top gainer {top_g.get('ticker','?')} +{top_g.get('change_pct','?')}% | "
          f"top loser {top_l.get('ticker','?')} {top_l.get('change_pct','?')}% | "
          f"top active {top_a.get('ticker','?')} vol={top_a.get('volume','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
