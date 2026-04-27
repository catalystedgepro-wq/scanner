#!/usr/bin/env python3
"""content_publisher.py — Distribution Automaton.

Takes a drafted post and:
  1. scp's /docs/blog/<slug>/index.html to cerebro:/opt/catalyst/docs/blog/<slug>/index.html
  2. Updates /docs/blog/index.html with a new card linking to it (top of list)
  3. Adds the post URL to /docs/sitemap.xml
  4. Transitions queue state drafted → published

Usage:
    python3 content_publisher.py --next-drafted     # publish the most recent draft
    python3 content_publisher.py --slug <slug>      # publish a specific slug
    python3 content_publisher.py --dry-run --slug <slug>   # build, skip scp
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
DOCS = WORKSPACE / "docs"
DOCS_BLOG = DOCS / "blog"
QUEUE_PATH = ROOT / "pending_content.yaml"
SITEMAP_PATH = DOCS / "sitemap.xml"
LOG_PATH = WORKSPACE / "logs" / "distribution_loop.log"

# We import the queue helpers from content_smith directly — single source of truth.
sys.path.insert(0, str(ROOT))
from content_smith import _read_queue, _write_queue, _now_iso, _today, _html_escape  # type: ignore


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] content_publisher: {msg}"
    print(line)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _scp_post(slug: str, dry: bool) -> bool:
    src = DOCS_BLOG / slug / "index.html"
    if not src.exists():
        _log(f"ERROR: missing source {src}")
        return False
    target = f"cerebro:/opt/catalyst/docs/blog/{slug}/index.html"
    if dry:
        _log(f"DRY-RUN: would scp {src} -> {target}")
        return True
    # ensure remote dir
    mkdir_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "cerebro",
                 f"mkdir -p /opt/catalyst/docs/blog/{shlex.quote(slug)}"]
    try:
        subprocess.run(mkdir_cmd, check=False, timeout=30,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        _log(f"WARN: mkdir remote failed: {e}")
    cp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", str(src), target]
    try:
        result = subprocess.run(cp_cmd, check=False, timeout=60,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            _log(f"scp OK: {src.name} -> {target}")
            return True
        _log(f"scp RC={result.returncode}: {result.stderr.decode(errors='replace')[:200]}")
        return False
    except Exception as e:
        _log(f"scp ERROR: {e}")
        return False


def _update_blog_index(post: dict) -> bool:
    """Insert a new <a class=\"post\"> card at the top of /docs/blog/index.html
    inside the post-list container."""
    idx = DOCS_BLOG / "index.html"
    if not idx.exists():
        _log(f"ERROR: blog index missing {idx}")
        return False
    text = idx.read_text(encoding="utf-8")
    slug = post["slug"]
    if f"/blog/{slug}/" in text:
        _log(f"blog index already lists {slug} — skipping insert")
        return True
    # Build the card
    today = _today()
    h1 = post.get("h1", post["title"])
    desc = post.get("rationale") or "New post."
    desc = re.sub(r"\s+", " ", desc).strip()
    if len(desc) > 220:
        desc = desc[:218].rsplit(" ", 1)[0] + "…"
    word_count = int(post.get("word_count_target", 1800))
    read_min = max(3, round(word_count / 230))
    card = (
        f"\n        <a class=\"post\" href=\"/blog/{slug}/\">\n"
        f"          <div class=\"date\">{today}<span class=\"read\">≈ {read_min} min read</span></div>\n"
        f"          <div class=\"body\">\n"
        f"            <h3>{_html_escape(h1)}</h3>\n"
        f"            <p>{_html_escape(desc)}</p>\n"
        f"            <span class=\"arrow\">Read post →</span>\n"
        f"          </div>\n"
        f"        </a>\n"
    )
    # insert after the post-list opening div
    pattern = r"(<div class=\"post-list\">)\s*"
    new_text, n = re.subn(pattern, r"\1\n" + card, text, count=1)
    if n == 0:
        _log("WARN: could not find <div class=\"post-list\"> — appending at end")
        new_text = text  # leave alone; better than corrupting
        return False
    idx.write_text(new_text, encoding="utf-8")
    _log(f"blog index updated: {slug} card inserted")
    return True


def _update_sitemap(post: dict) -> bool:
    """Insert a new <url> entry for the post just before </urlset>."""
    if not SITEMAP_PATH.exists():
        _log(f"ERROR: sitemap missing {SITEMAP_PATH}")
        return False
    text = SITEMAP_PATH.read_text(encoding="utf-8")
    slug = post["slug"]
    loc = f"https://catalystedgescanner.com/blog/{slug}/"
    if loc in text:
        _log(f"sitemap already lists {loc}")
        return True
    today = _today()
    entry = (
        f"  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>weekly</changefreq>\n"
        f"    <priority>0.8</priority>\n"
        f"  </url>\n"
    )
    new_text = text.replace("</urlset>", entry + "</urlset>")
    if new_text == text:
        _log("ERROR: failed to insert sitemap entry (no </urlset>)")
        return False
    SITEMAP_PATH.write_text(new_text, encoding="utf-8")
    _log(f"sitemap updated: {slug}")
    return True


def _scp_index(dry: bool) -> None:
    if dry:
        _log("DRY-RUN: would scp updated /docs/blog/index.html and /docs/sitemap.xml")
        return
    for src, remote in [
        (DOCS_BLOG / "index.html", "cerebro:/opt/catalyst/docs/blog/index.html"),
        (SITEMAP_PATH, "cerebro:/opt/catalyst/docs/sitemap.xml"),
    ]:
        if src.exists():
            try:
                subprocess.run(
                    ["scp", "-o", "StrictHostKeyChecking=no", str(src), remote],
                    check=False, timeout=60,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                _log(f"scp helper: {src.name} -> {remote}")
            except Exception as e:
                _log(f"scp helper ERROR for {src.name}: {e}")


def _publish(post: dict, queue: dict, dry: bool) -> bool:
    slug = post["slug"]
    ok_index = _update_blog_index(post)
    ok_site = _update_sitemap(post)
    ok_scp = _scp_post(slug, dry)
    if ok_scp and ok_index and ok_site:
        _scp_index(dry)
        post["state"] = "published"
        post["published_at"] = _today()
        _write_queue(queue)
        _log(f"PUBLISHED slug={slug}")
        if not dry:
            try:
                subprocess.run(
                    ["python3", str(ROOT / "indexnow_ping.py"),
                     "--slug", slug, "--sitemap"],
                    check=False, timeout=30,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                _log(f"indexnow ping submitted for {slug}")
            except Exception as e:
                _log(f"indexnow ping skipped: {e}")
        return True
    _log(f"PUBLISH FAILED slug={slug} idx={ok_index} site={ok_site} scp={ok_scp}")
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--next-drafted", action="store_true",
                        help="publish the most recently drafted post")
    parser.add_argument("--slug", help="publish a specific slug")
    parser.add_argument("--dry-run", action="store_true",
                        help="skip scp; only update local files + queue")
    args = parser.parse_args(argv)

    queue = _read_queue()
    posts = queue.get("posts", [])
    if args.slug:
        for p in posts:
            if p.get("slug") == args.slug:
                return 0 if _publish(p, queue, args.dry_run) else 2
        _log(f"ERROR: slug not found {args.slug}")
        return 2
    if args.next_drafted:
        candidates = [p for p in posts if p.get("state") == "drafted"]
        if not candidates:
            _log("no drafted posts to publish")
            return 1
        # most recently drafted = highest drafted_at
        candidates.sort(key=lambda p: p.get("drafted_at", ""), reverse=True)
        nxt = candidates[0]
        return 0 if _publish(nxt, queue, args.dry_run) else 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
