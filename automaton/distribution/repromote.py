#!/usr/bin/env python3
"""repromote.py — Weekly distribution amplifier.

Picks the N oldest already-promoted posts and re-runs social_rotator on each
with a freshness flag, producing new platform variants in social_inbox/. The
existing dispatch_inbox.sh drains them on the next morning fire. Closes the
loop: every published post gets re-shared every 7 days for the first 4 weeks.

State machine: posts gain 'repromoted_count' (int) and 'repromoted_at' (ISO).
Cap at 4 re-promotions to avoid spamming.

Usage:
    python3 repromote.py --count 2          # default — pick 2 oldest eligible
    python3 repromote.py --slug <slug>      # force re-promote one post
    python3 repromote.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
LOG_PATH = WORKSPACE / "logs" / "distribution_loop.log"

sys.path.insert(0, str(ROOT))
from content_smith import _read_queue, _write_queue, _now_iso, _today  # type: ignore

MAX_REPROMOTIONS = 4
COOLDOWN_DAYS = 7


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] repromote: {msg}"
    print(line)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _days_since(iso_date) -> int:
    if not iso_date:
        return 9999
    try:
        if isinstance(iso_date, dt.datetime):
            d = iso_date.date()
        elif isinstance(iso_date, dt.date):
            d = iso_date
        else:
            d = dt.date.fromisoformat(str(iso_date)[:10])
        return (dt.date.today() - d).days
    except Exception:
        return 9999


def _eligible(post: dict) -> bool:
    if post.get("state") != "promoted":
        return False
    if post.get("repromoted_count", 0) >= MAX_REPROMOTIONS:
        return False
    last = post.get("repromoted_at") or post.get("promoted_at") or post.get("published_at")
    return _days_since(last) >= COOLDOWN_DAYS


def _rotate(slug: str, dry: bool) -> bool:
    if dry:
        _log(f"DRY-RUN would re-rotate {slug}")
        return True
    cmd = ["python3", str(ROOT / "social_rotator.py"), "--slug", slug]
    try:
        result = subprocess.run(cmd, check=False, timeout=120,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            _log(f"re-rotated {slug}")
            return True
        _log(f"re-rotate FAILED {slug} rc={result.returncode} "
             f"err={result.stderr.decode(errors='replace')[:200]}")
        return False
    except Exception as e:
        _log(f"re-rotate ERROR {slug}: {e}")
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--slug", help="force re-promote one slug")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    queue = _read_queue()
    posts = queue.get("posts", [])

    if args.slug:
        targets = [p for p in posts if p.get("slug") == args.slug]
        if not targets:
            _log(f"slug not found: {args.slug}")
            return 2
    else:
        eligible = [p for p in posts if _eligible(p)]
        # oldest first by published_at, then by repromoted_count ascending
        eligible.sort(key=lambda p: (p.get("repromoted_at") or p.get("promoted_at")
                                     or p.get("published_at") or "0"))
        targets = eligible[:args.count]

    if not targets:
        _log("nothing eligible to re-promote")
        return 1

    rotated = 0
    for p in targets:
        slug = p["slug"]
        if _rotate(slug, args.dry_run):
            if not args.dry_run:
                p["repromoted_count"] = int(p.get("repromoted_count", 0)) + 1
                p["repromoted_at"] = _today()
            rotated += 1

    if not args.dry_run and rotated:
        _write_queue(queue)

    _log(f"re-promote done: {rotated}/{len(targets)} slugs rotated")
    return 0 if rotated > 0 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
