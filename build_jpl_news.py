#!/usr/bin/env python3
"""build_jpl_news.py — NASA JPL news + mission updates.

Deep-space and Earth-observation mission catalysts from JPL. Drives:
- LMT (Mars sample return, Psyche partner)
- NOC (James Webb prime)
- BA (SLS, Orion)
- LHX (Europa Clipper electronics)
- RKLB (Psyche launch services, lunar lander)
- MAXR (interplanetary imaging supplier)
- Mission-dependent contractors (CW, HON, LDOS)

Complements build_spaceflight_news (industry press) with NASA primary-
source mission progress / launch delays / science results that pre-
empt press cycle.

Source: www.jpl.nasa.gov/feeds/news/ (RSS).
Output: jpl_news.csv
Columns: title, link, category, pub_date, summary, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "jpl_news.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.jpl.nasa.gov/feeds/news/"

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL | re.IGNORECASE)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
LINK_RE = re.compile(r"<link>(.*?)</link>", re.DOTALL | re.IGNORECASE)
DESC_RE = re.compile(r"<description>(.*?)</description>",
                     re.DOTALL | re.IGNORECASE)
PUB_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL | re.IGNORECASE)
CAT_RE = re.compile(r"<category>(.*?)</category>", re.DOTALL | re.IGNORECASE)


def _strip(s: str) -> str:
    if not s:
        return ""
    return WS_RE.sub(" ", TAG_RE.sub(" ", s)).strip()


def _first(pat: re.Pattern, block: str) -> str:
    m = pat.search(block)
    return m.group(1) if m else ""


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"jpl_news: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"jpl_news: keeping existing {OUT_CSV.name}")
        return

    items = ITEM_RE.findall(body)
    if not items:
        print(f"jpl_news: no <item> blocks")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"jpl_news: keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for block in items[:80]:
        title = _strip(_first(TITLE_RE, block))[:200]
        link = _strip(_first(LINK_RE, block))[:220]
        pub = _strip(_first(PUB_RE, block))[:31]
        desc = _strip(_first(DESC_RE, block))[:260]
        cats = [_strip(c) for c in CAT_RE.findall(block)]
        cat_str = "|".join(c for c in cats if c)[:80]
        if not title:
            continue
        rows.append({
            "title": title,
            "link": link,
            "category": cat_str,
            "pub_date": pub,
            "summary": desc,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"jpl_news: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["title", "link", "category", "pub_date", "summary",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    cats_hist: dict[str, int] = {}
    for r in rows:
        for c in (r["category"] or "").split("|"):
            if c:
                cats_hist[c] = cats_hist.get(c, 0) + 1
    top = sorted(cats_hist.items(), key=lambda kv: -kv[1])[:3]
    top_str = " ".join(f"{k}={v}" for k, v in top) or "(no categories)"
    print(f"jpl_news: {len(rows)} items | {top_str} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
