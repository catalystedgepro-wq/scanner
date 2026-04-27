#!/usr/bin/env python3
"""build_sitemap.py — walk docs/ for index.html files and emit sitemap.xml.

Output: /home/operator/.openclaw/workspace/docs/sitemap.xml

Skips:
  - /docs/data/         (JSON dumps, not HTML)
  - /docs/lib/          (shared JS/CSS, not pages)
  - /docs/embed/dcf-top/ (iframed widget — gallery /embed/ is included)
  - /docs/cerebro-landing/ (subdomain landing)
  - /docs/agency/       (separate domain)
  - /docs/api/          (API runtime, not static page)
  - hidden dirs starting with .

Priority + changefreq heuristics:
  / (root)               → 1.0  weekly
  /scanner/, /pricing/,  → 0.9  daily
    /trust/, /dcf/,
    /international/,
    /cross-border/
  blog post deeps        → 0.7  monthly
  data feeds (rss.xml)   → 0.6  daily
  everything else        → 0.5  weekly
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

DOCS = Path("/home/operator/.openclaw/workspace/docs")
OUT = DOCS / "sitemap.xml"
SITE = "https://catalystedgescanner.com"

SKIP_DIRS = {
    "data", "lib", "cerebro-landing", "agency", "api",
    "embed/dcf-top",  # widget itself; gallery /embed/ still included
}

HIGH_PRIORITY = {
    "scanner", "pricing", "trust", "dcf", "international",
    "cross-border", "benchmarks", "alerts",
}


def is_skipped(rel_dir: str) -> bool:
    if not rel_dir:
        return False
    parts = rel_dir.split("/")
    # Hidden dirs
    if any(p.startswith(".") for p in parts):
        return True
    # Top-level skips
    if parts[0] in SKIP_DIRS:
        return True
    # Nested skip patterns
    if "/".join(parts[:2]) in SKIP_DIRS:
        return True
    return False


def priority_for(rel_dir: str) -> tuple[float, str]:
    """Return (priority, changefreq) for a sitemap URL."""
    if rel_dir == "":
        return 1.0, "weekly"
    parts = rel_dir.split("/")
    top = parts[0]
    if top in HIGH_PRIORITY:
        return 0.9, "daily"
    if top == "blog" and len(parts) >= 2:
        return 0.7, "monthly"
    if top == "blog":
        return 0.8, "weekly"
    return 0.5, "weekly"


def fmt_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def collect_urls() -> list[tuple[str, str, float, str]]:
    """Returns list of (loc, lastmod, priority, changefreq)."""
    urls: list[tuple[str, str, float, str]] = []
    for index in sorted(DOCS.rglob("index.html")):
        rel_dir = str(index.parent.relative_to(DOCS))
        if rel_dir == ".":
            rel_dir = ""
        if is_skipped(rel_dir):
            continue
        loc = SITE + "/" + (rel_dir + "/" if rel_dir else "")
        lastmod = fmt_date(index.stat().st_mtime)
        priority, changefreq = priority_for(rel_dir)
        urls.append((loc, lastmod, priority, changefreq))

    # Add the RSS feed as a discoverable URL (sitemap.org allows non-HTML refs)
    rss = DOCS / "blog/rss.xml"
    if rss.exists():
        urls.append((
            SITE + "/blog/rss.xml",
            fmt_date(rss.stat().st_mtime),
            0.6,
            "daily",
        ))
    return urls


def render(urls: list[tuple[str, str, float, str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod, priority, changefreq in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority:.1f}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not DOCS.is_dir():
        print(f"ABORT: {DOCS} not found", file=sys.stderr)
        return 1
    urls = collect_urls()
    OUT.write_text(render(urls), encoding="utf-8")
    print(f"sitemap: {len(urls)} urls → {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
