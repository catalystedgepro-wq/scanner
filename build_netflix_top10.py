#!/usr/bin/env python3
"""build_netflix_top10.py — Netflix global Top 10 (weekly).

Film/TV hit timing -> NFLX stock catalyst + tangential trades. Big
Korean/Japanese hits -> KRE/EWJ sector names. Documentary series
boosting specific companies (Tinder Swindler -> MTCH, WeCrashed ->
softbank). Also proxies ad-tier adoption (NFLX-Wise) + churn risk.

Source: top10.netflix.com/data/all-weeks-global.tsv (public TSV).
Output: netflix_top10.csv
Columns: week, category, rank, title, hours_viewed, views, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "netflix_top10.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
URL = "https://top10.netflix.com/data/all-weeks-global.tsv"


def fetch_tsv() -> list[list[str]]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"netflix: {e}")
        return []
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return [ln.split("\t") for ln in lines]


def main() -> None:
    grid = fetch_tsv()
    rows: list[dict] = []
    if len(grid) < 2:
        OUT_CSV.write_text(
            "week,category,rank,title,hours_viewed,views,captured_at\n"
        )
        print("netflix_top10: 0 rows (tsv empty)")
        return
    header = [h.strip() for h in grid[0]]
    idx = {h: i for i, h in enumerate(header)}
    # Required columns
    if not {"week", "category", "weekly_rank",
            "show_title"}.issubset(idx.keys()):
        print(f"netflix_top10: unexpected header {header[:8]}")
        return
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # Keep only the latest 3 weeks of data to stay lean
    weeks = sorted({r[idx["week"]] for r in grid[1:] if len(r) > idx["week"]},
                   reverse=True)
    keep = set(weeks[:3])
    for r in grid[1:]:
        if len(r) <= idx["show_title"]:
            continue
        wk = r[idx["week"]]
        if wk not in keep:
            continue
        title = r[idx["show_title"]]
        season = r[idx["season_title"]] if "season_title" in idx and len(r) > idx["season_title"] else ""
        full_title = f"{title} - {season}" if season and season != title else title
        rows.append({
            "week": wk,
            "category": r[idx["category"]][:40],
            "rank": r[idx["weekly_rank"]],
            "title": full_title[:120],
            "hours_viewed": r[idx.get("weekly_hours_viewed", -1)]
                if "weekly_hours_viewed" in idx
                and len(r) > idx["weekly_hours_viewed"] else "",
            "views": r[idx.get("weekly_views", -1)]
                if "weekly_views" in idx
                and len(r) > idx["weekly_views"] else "",
            "captured_at": now,
        })
    rows.sort(key=lambda x: (x["week"], x["category"], int(x["rank"] or 999)),
              reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["week", "category", "rank", "title",
                        "hours_viewed", "views", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"netflix_top10: {len(rows)} rows | latest week "
          f"{top.get('week','?')} | #1 {top.get('title','?')[:50]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
