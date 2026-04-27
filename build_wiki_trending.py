#!/usr/bin/env python3
"""build_wiki_trending.py — Wikipedia top-viewed articles, 7-day rolling.

Complements `build_wiki_attention.py` (which z-scores a pre-defined 30-
ticker list). This spoke surfaces attention spikes on companies,
products, films, and events that ARE NOT on the pre-defined list — the
"unknown unknowns" of retail attention. By capturing the daily top 200
articles, we can cross-reference against full ticker / product / CEO
dictionaries and find:

- **Product launches**: "iPhone 17 Pro" surge → AAPL demand proxy.
- **Scandals / outages**: "CrowdStrike" trending → CRWD short signal 2
  days before earnings warning (precedent July-2024).
- **Films / streaming**: Top-10 film page surges precede box-office
  beats → DIS, NFLX, WBD, CNK, AMC catalysts.
- **M&A gossip**: Pages editable-protected + view surge → pre-leak
  merger catalyst (target renames, rumor activity).
- **Death / exit events**: Executive death → succession-risk sell-off
  (historical: MAT / BRK-B Buffett-succession interest surges).
- **Geopolitics**: Country / conflict pages → oil/defense rotation.

Methodology:
- Da, Engelberg, Gao (2011) established Wikipedia pageview z-scores as
  a robust retail-attention proxy. Top-view *rank* adds ordinal
  information the predefined-list z-score cannot capture (you need to
  already know the ticker to z-score it).
- Meta pages (Main_Page, Special:*, Wikipedia:*, Portal:*, File:*,
  Help:*, Category:*, List_of_*) are excluded — these are structural
  traffic, not attention signals.
- 7-day window = rolling one-week picture of what the retail internet
  is paying attention to.

Trade uses:
- Company / product trending in top-100 → cross-ref against ticker
  table for 1-3 day momentum setup. Rank < 50 typically implies
  material news cycle.
- Fresh entry into top-50 (not trending yesterday) → higher-conviction
  signal (new catalyst) vs sustained trending (already-priced-in).
- Entity mentioned in `bloomberg_headlines.csv` AND trending = news +
  attention confluence.

Source: Wikimedia REST API pageviews/top endpoint (free, no key,
rate-limit 100/sec/IP, public-domain data).

Output: wiki_trending.csv
Columns: date, rank, article, views, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "wiki_trending.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
        "en.wikipedia/all-access")

DAYS_BACK = 7
TOP_N = 200

# Meta-page prefixes to strip — these are Wikipedia structural pages,
# not subject matter. Main_Page alone is 7M+ views/day.
META_RE = re.compile(
    r"^("
    r"Main_Page|Special:|Wikipedia:|Portal:|File:|Help:|Category:|"
    r"Template:|Draft:|User:|Talk:|Module:|MediaWiki:|Book:"
    r")",
    re.IGNORECASE,
)
LIST_RE = re.compile(r"^List_of_", re.IGNORECASE)
DEATHS_RE = re.compile(r"^Deaths_in_\d{4}$")


def fetch_day(date: dt.date) -> list[dict]:
    url = f"{BASE}/{date.strftime('%Y/%m/%d')}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"wiki_trending: {date} -> {e}")
        return []

    items = (data.get("items") or [{}])[0].get("articles") or []
    return items


def is_content(article: str) -> bool:
    if META_RE.match(article):
        return False
    if LIST_RE.match(article):
        return False
    if DEATHS_RE.match(article):
        return False
    return True


def main() -> None:
    today = dt.date.today()
    rows: list[dict] = []

    for i in range(1, DAYS_BACK + 1):
        d = today - dt.timedelta(days=i)
        items = fetch_day(d)
        if not items:
            continue

        kept = 0
        for a in items:
            article = a.get("article", "")
            if not is_content(article):
                continue
            rows.append({
                "date": d.isoformat(),
                "rank": str(a.get("rank", "")),
                "article": article,
                "views": str(a.get("views", "")),
            })
            kept += 1
            if kept >= TOP_N:
                break

        time.sleep(0.35)  # ≤3 req/sec per Wikimedia best-practice

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"wiki_trending: all fetches failed, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "rank", "article", "views",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Summary: most-recent day's top 5 content articles.
    dates = sorted({r["date"] for r in rows}, reverse=True)
    latest = dates[0] if dates else "?"
    latest_rows = [r for r in rows if r["date"] == latest]
    latest_rows.sort(key=lambda r: int(r["rank"]))
    top5 = ", ".join(
        f"#{r['rank']} {r['article'][:30]} ({int(r['views']):,})"
        for r in latest_rows[:5]
    )

    print(f"wiki_trending: {len(rows)} rows across {len(dates)} days | "
          f"latest {latest} top5: {top5} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
