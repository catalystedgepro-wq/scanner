#!/usr/bin/env python3
"""build_github_trending.py — GitHub trending repos (developer ecosystem).

Broader than HF trending (AI-model only). GitHub trending captures
framework, tooling, devops, infra, database, and open-source SaaS
repos that signal developer mindshare shifts.

Equity implications:
- Framework dominance → bias cloud platforms (AWS vs AZURE vs GCP
  embedded metrics). MongoDB/Elastic/Snowflake references track.
- Developer-tools spike → MSFT Copilot / CRM MuleSoft / OKTA signal.
- Infrastructure repos surge → bullish for MDB, ESTC, DDOG, SNOW.
- Lang-specific velocity → Rust repos climbing = hot for systems
  startups (private, but AMZN / Meta infra tracks).

Output: github_trending.csv
Columns: rank, repo, stars, forks, language, created, description,
captured_at

Source: api.github.com/search/repositories (unauth rate-limit
10 req/min — plenty for one daily fetch).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "github_trending.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
ENDPOINT = "https://api.github.com/search/repositories"


def _fetch(q: str, per: int = 30) -> dict | None:
    qs = urllib.parse.urlencode({
        "q": q,
        "sort": "stars",
        "order": "desc",
        "per_page": per,
    })
    url = f"{ENDPOINT}?{qs}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"github_trending {q[:32]}: {e}")
        return None


def main() -> None:
    today = dt.date.today()
    since_30 = (today - dt.timedelta(days=30)).isoformat()
    since_7 = (today - dt.timedelta(days=7)).isoformat()

    queries = [
        ("trending_30d", f"created:>{since_30} stars:>500"),
        ("trending_7d",  f"created:>{since_7} stars:>100"),
        ("ai_7d",        f"topic:ai created:>{since_7} stars:>50"),
    ]

    rows: list[dict] = []
    for bucket, q in queries:
        data = _fetch(q, per=25)
        if not data:
            continue
        items = data.get("items") or []
        for idx, it in enumerate(items, start=1):
            desc = (it.get("description") or "")[:100]
            rows.append({
                "bucket": bucket,
                "rank": idx,
                "repo": (it.get("full_name") or "")[:48],
                "stars": it.get("stargazers_count", 0),
                "forks": it.get("forks_count", 0),
                "language": (it.get("language") or "")[:16],
                "created": (it.get("created_at") or "")[:10],
                "description": desc,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"github_trending: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["bucket", "rank", "repo", "stars", "forks", "language",
                  "created", "description", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    t30 = [r for r in rows if r["bucket"] == "trending_30d"]
    t7 = [r for r in rows if r["bucket"] == "trending_7d"]
    ai7 = [r for r in rows if r["bucket"] == "ai_7d"]
    top30 = t30[0] if t30 else {}
    top7 = t7[0] if t7 else {}
    print(f"github_trending: {len(rows)} rows ({len(t30)}/30d, "
          f"{len(t7)}/7d, {len(ai7)}/ai7d) | top 30d "
          f"{top30.get('repo','?')} ({top30.get('stars',0)}★) | top 7d "
          f"{top7.get('repo','?')} ({top7.get('stars',0)}★) "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
