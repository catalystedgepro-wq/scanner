#!/usr/bin/env python3
"""build_hn_tech.py — Hacker News tech/macro sentiment.

Technologist community attention signal via HN Algolia front-page
search. Retail-adjacent tech sentiment (startup/developer mindshare)
that leads equity narratives by ~days to weeks.

Queries cover:
- Fed / rate / inflation → macro sentiment shift
- AI / OpenAI / Claude / Anthropic → NVDA/MSFT/GOOGL narrative
- Layoffs → tech HR cycle (META, GOOGL, AMZN ruthlessness)
- Crypto / bitcoin → COIN/MSTR attention
- Earnings / IPO / acquisition → deal-flow priors
- Antitrust / regulation → FTC/DOJ risk (GOOGL, AAPL, META)

Output: hn_tech.csv
Columns: bucket, title, points, comments, url, created_at, author,
captured_at

Source: hn.algolia.com/api/v1/search_by_date (no key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "hn_tech.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://hn.algolia.com/api/v1/search_by_date"

BUCKETS = [
    ("fed_rates",    "fed rate inflation"),
    ("ai_llm",       "openai anthropic claude"),
    ("nvidia_chip",  "nvidia chip gpu"),
    ("layoffs",      "layoffs firing"),
    ("crypto",       "bitcoin ethereum crypto"),
    ("ipo_ma",       "ipo acquisition merger"),
    ("antitrust",    "antitrust regulation ftc"),
    ("earnings",     "earnings revenue beat miss"),
]


def _fetch(q: str, hits: int = 20) -> list:
    qs = urllib.parse.urlencode({
        "query": q,
        "tags": "story",
        "hitsPerPage": hits,
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        return d.get("hits") or []
    except Exception as e:
        print(f"hn_tech {q[:20]}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    seen_ids: set[str] = set()

    for bucket, q in BUCKETS:
        hits = _fetch(q, hits=15)
        for h in hits:
            sid = str(h.get("objectID", ""))
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            title = (h.get("title") or "")[:120]
            if not title:
                continue
            rows.append({
                "bucket": bucket,
                "story_id": sid,
                "title": title,
                "points": str(h.get("points") or "0"),
                "comments": str(h.get("num_comments") or "0"),
                "url": (h.get("url") or "")[:120],
                "created_at": (h.get("created_at") or "")[:20],
                "author": (h.get("author") or "")[:20],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"hn_tech: no data, keeping existing {OUT_CSV.name}")
        return

    # Sort by points desc within bucket.
    def _pts(r: dict) -> int:
        try:
            return int(r["points"])
        except (ValueError, TypeError):
            return 0
    rows.sort(key=lambda r: (r["bucket"], -_pts(r)))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["bucket", "story_id", "title", "points", "comments",
                  "url", "created_at", "author", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    per_bucket: dict[str, int] = {}
    for r in rows:
        per_bucket[r["bucket"]] = per_bucket.get(r["bucket"], 0) + 1
    top = max(rows, key=_pts, default={})
    print(f"hn_tech: {len(rows)} stories ({len(per_bucket)} buckets) | "
          f"top: \"{top.get('title','')[:50]}\" "
          f"({top.get('points','?')}pts, {top.get('bucket','?')}) "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
