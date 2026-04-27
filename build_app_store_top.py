#!/usr/bin/env python3
"""build_app_store_top.py — Apple App Store top grossing / top free apps.

Top-grossing = consumer spend. Breakout apps (TikTok, CapCut, CashApp)
reveal consumer behavior shifts. If BYND's Shake Shack app shoots up,
or Wayfair/Etsy apps surge on Black Friday week, that's a catalyst
gauge. Also captures gaming trends (RBLX, EA, TTWO, NTES pre-earnings).

Source: itunes.apple.com/us/rss/topgrossingapplications / topfreeapps (JSON).
Output: app_store_top.csv
Columns: rank, app_name, category, chart, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "app_store_top.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

CHARTS = [
    ("topgrossing", "https://itunes.apple.com/us/rss/topgrossingapplications/limit=50/json"),
    ("topfree", "https://itunes.apple.com/us/rss/topfreeapplications/limit=50/json"),
    ("topfreegames", "https://itunes.apple.com/us/rss/topfreeapplications/limit=50/genre=6014/json"),
]


def fetch(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"appstore {url[-40:]}: {e}")
        return []
    return (data.get("feed") or {}).get("entry", []) or []


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for chart, url in CHARTS:
        entries = fetch(url)
        for i, e in enumerate(entries, 1):
            name = (e.get("im:name") or {}).get("label", "")
            cat = ((e.get("category") or {}).get("attributes") or {}).get("label", "")
            rows.append({
                "rank": i,
                "app_name": name[:80],
                "category": cat[:40],
                "chart": chart,
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["rank", "app_name", "category", "chart", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    tg = [r for r in rows if r["chart"] == "topgrossing"]
    top = tg[0] if tg else {}
    print(f"app_store: {len(rows)} entries | #1 grossing {top.get('app_name','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
