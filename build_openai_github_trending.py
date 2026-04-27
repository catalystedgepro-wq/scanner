#!/usr/bin/env python3
"""build_openai_github_trending.py — GitHub trending repos (daily).

GitHub trending = developer-tool adoption signal. Rapid star growth on
AI infra repos → NVDA/ARM/AMD demand. LLM-adjacent tools trending →
MDB/SNOW/DDOG/NET. Crypto/DeFi trending → COIN/MSTR/MARA. Open source
finance tools trending → TRAD/IBKR. Fintech trending → NU/SOFI.

Source: gh-trending-api via api.gitterapp.com or scrape github.com/trending
Output: openai_github_trending.csv
Columns: rank, repo, language, stars, stars_today, description,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "github_trending.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Public unofficial JSON mirror of github.com/trending
FEED = "https://api.gitterapp.com/repositories?language=&since=daily"


def fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"gh_trending: {e}")
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for i, it in enumerate(items[:50], 1):
        rows.append({
            "rank": i,
            "repo": f"{it.get('author','')}/{it.get('name','')}",
            "language": it.get("language", "") or "",
            "stars": it.get("stars", 0) or 0,
            "stars_today": it.get("currentPeriodStars", 0) or 0,
            "description": (it.get("description") or "")[:180],
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank", "repo", "language", "stars",
                "stars_today", "description", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"gh_trending: {len(rows)} repos | #1 "
          f"{top.get('repo','?')} (+{top.get('stars_today','?')}) "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
