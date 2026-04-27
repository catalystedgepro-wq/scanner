#!/usr/bin/env python3
"""build_spaceflight_news.py — Spaceflight News API v4 headlines.

Aggregates 80+ space industry publications. Novel catalysts for:
- SpaceX-adjacent names (IRDM, SATS, MAXR, RKLB, ASTR, PL, RDW)
- Boeing programs (BA: Starliner, SLS, X-37B)
- Lockheed Martin (LMT: Orion, GPS III, F-35 testing tie-ins)
- Northrop Grumman (NOC: NGI, launch cadence)
- Virgin Galactic / Virgin Orbit (SPCE, VORB)
- Blue Origin (private, AMZN halo)
- Space insurance (TRV, CB, ACGL on vehicle losses)
- Satellite imagery / geospatial (PL, MAXR, BKSY)
- Defense primes on hypersonic / directed energy
- Cyber/space (L3Harris LHX)

Three streams: articles (news), blogs (analysis), reports (agency).

Source: api.spaceflightnewsapi.net/v4 (free, no auth).

Output: spaceflight_news.csv
Columns: kind, title, authors, summary, news_site, published_at,
         url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "spaceflight_news.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.spaceflightnewsapi.net/v4"

STREAMS = [("article", "/articles/", 40),
           ("blog", "/blogs/", 10),
           ("report", "/reports/", 10)]


def _fetch(path: str, limit: int) -> list:
    qs = urllib.parse.urlencode({"limit": limit,
                                 "ordering": "-published_at"})
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        return d.get("results") or []
    except Exception as e:
        print(f"spaceflight_news {path}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    for kind, path, limit in STREAMS:
        for item in _fetch(path, limit):
            if not isinstance(item, dict):
                continue
            authors = item.get("authors") or []
            author_str = "|".join(
                (a.get("name") or "") for a in authors
                if isinstance(a, dict))[:80]
            rows.append({
                "kind": kind,
                "title": str(item.get("title") or "")[:200],
                "authors": author_str,
                "summary": str(item.get("summary") or "")[:220],
                "news_site": str(item.get("news_site") or "")[:40],
                "published_at": str(item.get("published_at") or "")[:19],
                "url": str(item.get("url") or "")[:200],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"spaceflight_news: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["published_at"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["kind", "title", "authors", "summary", "news_site",
                  "published_at", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    sites: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        if r["news_site"]:
            sites[r["news_site"]] = sites.get(r["news_site"], 0) + 1
    k_str = " ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
    top_site = max(sites.items(), key=lambda kv: kv[1], default=("?", 0))
    print(f"spaceflight_news: {len(rows)} items | {k_str} | "
          f"top site: {top_site[0]}={top_site[1]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
