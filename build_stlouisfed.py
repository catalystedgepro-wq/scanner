#!/usr/bin/env python3
"""build_stlouisfed.py — St. Louis Fed Economic Research News firehose.

Source: news.research.stlouisfed.org/feed/ (WordPress 6.8.3 RSS 2.0 hourly
update, 10-item rolling, free, no key, standard schema with <dc:creator>
+ <category> taxonomy).

8th District = Arkansas + southern Illinois + southern Indiana + Kentucky
+ Mississippi + Missouri + western Tennessee. President **Alberto Musalem**
(since April 2024) is a **2025 + 2028 FOMC voter** — centrist-to-hawkish
framework, signature focus on services-inflation persistence + supply-side
disinflation. 4th FOMC-voter-intelligence spoke after Boston/SF/Dallas.

Unique signal: FRED Announcements tape — every "FRED Adds X" item
telegraphs new data source ingestion affecting rates, credit, banking,
housing pipelines. High value for own-spoke feedback loop.

Taxonomy (priority-ordered, first-match-wins):
  fred_announcement / speech / working_paper / economic_synopses /
  regional_economist / monetary_policy / banking_finance / employment /
  regional_economy / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://news.research.stlouisfed.org/feed/"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "stlouisfed.csv"
FIELDS = ["filed_utc", "kind", "creator", "title", "link", "summary", "categories"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fred_announcement", re.compile(r"\b(FRED adds|FRED announcement|FRED expand|adds.*data|adds.*series|new release|ALFRED|GeoFRED|FRED Blog)\b", re.I)),
    ("speech", re.compile(r"\b(speech|remarks|Musalem|president's|keynote|commencement|address|testimony|address)\b", re.I)),
    ("working_paper", re.compile(r"\b(working paper|WP-\d+|staff paper|Research Division)\b", re.I)),
    ("economic_synopses", re.compile(r"\b(Economic Synopses|Synopses)\b", re.I)),
    ("regional_economist", re.compile(r"\b(Regional Economist|Eighth District|8th District)\b", re.I)),
    ("monetary_policy", re.compile(r"\b(monetary policy|Fed funds|FOMC|inflation target|Taylor rule|Phillips curve|rate cut|rate hike|interest rate|QE|QT|r-star|neutral rate|forward guidance)\b", re.I)),
    ("banking_finance", re.compile(r"\b(bank|credit|financial stability|mortgage|lending|insurance|pension|asset pricing|yield curve|credit spread|stress test)\b", re.I)),
    ("employment", re.compile(r"\b(employment|labor market|JOLTS|payrolls|unemployment|wages?|workforce|job|participation)\b", re.I)),
    ("regional_economy", re.compile(r"\b(regional|district|Arkansas|Illinois|Indiana|Kentucky|Mississippi|Missouri|Tennessee|St\.? Louis|Memphis|Louisville)\b", re.I)),
)


def _clean(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<!\[CDATA\[|\]\]>", "", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_pubdate(raw: str) -> str:
    if not raw:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        parsed = parsedate_to_datetime(raw.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_categories(block: str) -> str:
    cats = re.findall(r"<category[^>]*><!\[CDATA\[(.*?)\]\]></category>", block, re.S)
    if not cats:
        cats = re.findall(r"<category[^>]*>([^<]+)</category>", block, re.S)
    return ";".join(c.strip() for c in cats if c.strip())


def _classify(title: str, summary: str, categories: str) -> str:
    hay = f"{title} {summary} {categories}"
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(hay):
            return kind
    return "press"


def _fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    rows: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)
        pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        creator_m = re.search(r"<dc:creator>(.*?)</dc:creator>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        summary = _clean(desc_m.group(1)) if desc_m else ""
        filed_utc = _parse_pubdate(_clean(pub_m.group(1)) if pub_m else "")
        creator = _clean(creator_m.group(1)) if creator_m else ""
        categories = _extract_categories(block)

        if not title:
            continue

        rows.append(
            {
                "filed_utc": filed_utc,
                "kind": _classify(title, summary, categories),
                "creator": creator[:120],
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
                "categories": categories[:240],
            }
        )

    rows.sort(key=lambda r: r["filed_utc"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[stlouisfed] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[stlouisfed] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[stlouisfed] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    tally = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[stlouisfed] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
