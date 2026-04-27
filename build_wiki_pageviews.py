#!/usr/bin/env python3
"""build_wiki_pageviews.py — Wikipedia top article pageviews (daily).

Top Wikipedia pages = Google Trends proxy. Breaking news articles
rank top → narrative velocity for companies (NVDA, AAPL, TSLA, META).
Wiki pageview spikes precede earnings surprises and breaking events.
Also flags celebrity deaths/illnesses affecting brand ambassadors
(NKE, WWE, DIS, LVMH).

Source: wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/
Output: wiki_pageviews.csv
Columns: rank, article, views, date, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "wiki_pageviews.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch_day(d: dt.date) -> list[dict]:
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
        f"en.wikipedia/all-access/"
        f"{d.year}/{d.month:02d}/{d.day:02d}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"wiki {d}: {e}")
        return []
    items = data.get("items") or []
    if not items:
        return []
    return items[0].get("articles", []) or []


def main() -> None:
    # Wikimedia lags ~2 days; try 2 then 3 as fallback
    target = dt.date.today() - dt.timedelta(days=2)
    articles = fetch_day(target)
    if not articles:
        target = dt.date.today() - dt.timedelta(days=3)
        articles = fetch_day(target)
    yesterday = target
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for a in articles[:200]:
        art = a.get("article", "")
        if art in {"Main_Page", "Special:Search", "Special:Random"}:
            continue
        rows.append({
            "rank": a.get("rank", 0),
            "article": art[:120].replace("_", " "),
            "views": a.get("views", 0),
            "date": yesterday.isoformat(),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["rank", "article", "views", "date", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"wiki: {len(rows)} articles | #1 {top.get('article','?')[:40]} "
          f"({top.get('views','?')} views) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
