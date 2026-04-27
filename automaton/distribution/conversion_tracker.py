#!/usr/bin/env python3
"""conversion_tracker.py — Distribution Automaton.

Records UTM-tagged traffic from each blog post → /preview/ signup. Reads
two sources:

  1. /home/operator/.openclaw/workspace/data/preview_signups.jsonl
     (one JSON object per line, expected shape:
         {"ts": "...", "email": "...", "utm_source": "blog",
          "utm_campaign": "<slug>", "ip": "...", "ua": "..."})

  2. A hypothetical /api/utm-stats endpoint on the droplet — stubbed for now.
     The conversion_tracker will use the local JSONL as the source of truth
     until the endpoint is wired.

Outputs:
  - logs/conversion_leaderboard_<YYYY-MM-DD>.csv  (full week roll-up)
  - logs/conversion_leaderboard_latest.txt        (human-readable summary)

Usage:
    python3 conversion_tracker.py                   # weekly summary, last 7d
    python3 conversion_tracker.py --days 30         # custom window
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
LOG_DIR = WORKSPACE / "logs"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR = WORKSPACE / "data"
SIGNUPS_PATH = DATA_DIR / "preview_signups.jsonl"
TRAFFIC_PATH = DATA_DIR / "blog_traffic.jsonl"  # optional, future source

sys.path.insert(0, str(ROOT))
from content_smith import _read_queue, _now_iso  # type: ignore


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] conversion_tracker: {msg}"
    print(line)
    with open(LOG_DIR / "distribution_loop.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_signups(days: int) -> list[dict]:
    if not SIGNUPS_PATH.exists():
        _log(f"signups file missing ({SIGNUPS_PATH}) — empty leaderboard")
        return []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    rows: list[dict] = []
    with open(SIGNUPS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get("ts", "")
            try:
                t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                if t < cutoff:
                    continue
            except Exception:
                pass
            if rec.get("utm_source") != "blog":
                continue
            rows.append(rec)
    return rows


def _load_traffic(days: int) -> dict[str, int]:
    """Optional: pageview counts per slug, sourced from blog_traffic.jsonl
    (one record per pageview). Stubbed until the /api/utm-stats endpoint is
    wired — the leaderboard will fall back to a campaign:0 default."""
    out: dict[str, int] = {}
    if not TRAFFIC_PATH.exists():
        return out
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    with open(TRAFFIC_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            slug = rec.get("utm_campaign") or rec.get("slug")
            if not slug:
                continue
            ts = rec.get("ts", "")
            try:
                t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                if t < cutoff:
                    continue
            except Exception:
                pass
            out[slug] = out.get(slug, 0) + 1
    return out


def _build_leaderboard(days: int) -> list[dict]:
    queue = _read_queue()
    posts = queue.get("posts", [])
    signups = _load_signups(days)
    traffic = _load_traffic(days)

    by_slug: dict[str, dict] = {}
    for p in posts:
        slug = p.get("slug")
        if not slug:
            continue
        by_slug[slug] = {
            "slug": slug,
            "title": p.get("title", ""),
            "state": p.get("state", "?"),
            "published_at": p.get("published_at", ""),
            "pageviews": traffic.get(slug, 0),
            "signups": 0,
            "conv_rate_pct": 0.0,
        }

    for s in signups:
        slug = s.get("utm_campaign", "")
        if slug not in by_slug:
            continue
        by_slug[slug]["signups"] += 1

    rows = list(by_slug.values())
    for r in rows:
        if r["pageviews"] > 0:
            r["conv_rate_pct"] = round(100.0 * r["signups"] / r["pageviews"], 2)
    rows.sort(key=lambda r: (r["conv_rate_pct"], r["signups"]), reverse=True)
    return rows


def _write_outputs(rows: list[dict], days: int) -> None:
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    csv_path = LOG_DIR / f"conversion_leaderboard_{today}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["slug", "title", "state", "published_at", "pageviews", "signups", "conv_rate_pct"],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    _log(f"CSV written: {csv_path}")

    txt_path = LOG_DIR / "conversion_leaderboard_latest.txt"
    lines: list[str] = []
    lines.append(f"Catalyst Edge — Distribution Automaton conversion leaderboard")
    lines.append(f"Window: last {days} days  ·  generated {today}")
    lines.append("=" * 78)
    lines.append(
        f"{'slug':<38} {'state':<10} {'PV':>6} {'SU':>6} {'conv%':>7}"
    )
    lines.append("-" * 78)
    for r in rows:
        lines.append(
            f"{r['slug'][:38]:<38} {r['state']:<10} {r['pageviews']:>6} "
            f"{r['signups']:>6} {r['conv_rate_pct']:>7}"
        )
    if not rows:
        lines.append("(no posts in queue)")
    lines.append("-" * 78)
    lines.append("PV = pageviews from blog_traffic.jsonl   SU = /preview/ signups")
    lines.append("Until /api/utm-stats is wired, PV will be 0; SU is live.")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log(f"summary written: {txt_path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7,
                        help="lookback window (days)")
    args = parser.parse_args(argv)
    rows = _build_leaderboard(args.days)
    _write_outputs(rows, args.days)
    print(f"\nLeaderboard ({len(rows)} posts) — see logs/conversion_leaderboard_latest.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
