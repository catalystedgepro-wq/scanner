#!/usr/bin/env python3
"""build_hacker_news.py — Hacker News top stories (tech signal).

HN top stories → B2B SaaS product releases, breach disclosures, dev-tool
traction. Rising HN share for a company → early-cycle bullish (CRWD, NET,
DDOG, MDB, SNOW, OKTA, HACK, ZS, ESTC). Breach/incident posts → opposite.

Source: HN Firebase API (free, no auth).
Output: hacker_news.csv
Columns: post_id, title, url, score, comments, created_at, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "hacker_news.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


def fetch_json(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"hn: {e}")
        return None


def main() -> None:
    ids = fetch_json(TOP_URL) or []
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for pid in ids[:50]:
        it = fetch_json(ITEM_URL.format(id=pid)) or {}
        if not isinstance(it, dict) or it.get("type") != "story":
            continue
        rows.append({
            "post_id": pid,
            "title": (it.get("title") or "")[:140],
            "url": (it.get("url") or "")[:200],
            "score": it.get("score", 0),
            "comments": it.get("descendants", 0),
            "created_at": dt.datetime.fromtimestamp(
                it.get("time", 0), tz=dt.timezone.utc
            ).isoformat(timespec="seconds"),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "post_id", "title", "url", "score",
                "comments", "created_at", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"hacker_news: {len(rows)} stories | #1 \"{(top.get('title') or '')[:50]}\" "
          f"({top.get('score','?')}p) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
