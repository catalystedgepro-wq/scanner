#!/usr/bin/env python3
"""build_sffed.py — Federal Reserve Bank of San Francisco master feed.

Source: frbsf.org/feed/ (WordPress 6.9.4-generated RSS 2.0, hourly
updatePeriod, ~50-item rolling, includes dc:creator + categories +
content:encoded full-body). Covers 12th District (CA/OR/WA/NV/AZ/UT/
ID/AK/HI/Guam/American Samoa — largest Fed by GDP coverage ~21% US GDP).

President Mary C. Daly is 2024 FOMC rotating voter + 2027 voter; SF Fed
owns the tech-ecosystem research axis (AI productivity, fintech,
labor-supply demographics, immigration macro) given Silicon Valley
proximity. The SF Fed Blog (President's byline) + Economic Letter +
Working Paper Series are three highest-signal research channels in the
regional-Fed system after NY and Boston.

Taxonomy (priority-ordered, first-match-wins):
  speech / monetary_policy / research / tech_ai / labor /
  housing / payments_fintech / financial_stability /
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

FEED = "https://www.frbsf.org/feed/"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "sffed.csv"
FIELDS = ["filed_utc", "kind", "creator", "title", "link", "summary", "categories"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("speech", re.compile(r"\b(mary c\.? daly|daly remarks|president's speech|speech|remarks by|keynote|testimony|address|fireside chat)\b", re.I)),
    ("monetary_policy", re.compile(r"\b(monetary policy|FOMC|rate path|rate cut|rate hike|r-star|neutral rate|policy rule|Taylor rule|inflation target|2 percent target|dual mandate|yield curve|term premium)\b", re.I)),
    ("research", re.compile(r"\b(Economic Letter|Working Paper|SF Fed blog|research brief|staff report|research department|macro monitor|PCE nowcast|trend inflation)\b", re.I)),
    ("tech_ai", re.compile(r"\b(artificial intelligence|AI|machine learning|productivity|technology|tech sector|Silicon Valley|semiconductors|cloud|automation|generative)\b", re.I)),
    ("labor", re.compile(r"\b(labor market|employment|workforce|job|hiring|unemployment|immigration|wage|labor force|participation|hours worked|job openings)\b", re.I)),
    ("housing", re.compile(r"\b(housing|home sales|rent|mortgage|home prices|housing crisis|single[- ]family|shelter inflation)\b", re.I)),
    ("payments_fintech", re.compile(r"\b(stablecoin|tokenization|CBDC|FedNow|fed now|payment|fintech|digital currency|crypto|instant payment|blockchain)\b", re.I)),
    ("financial_stability", re.compile(r"\b(financial stability|private credit|private equity|bank stress|systemic|fraud|money market|concentration|shadow bank|leverage|runnable)\b", re.I)),
    ("regional_economy", re.compile(r"\b(12th District|twelfth district|California|Oregon|Washington|Nevada|Arizona|Utah|Idaho|Alaska|Hawaii|West Coast|Pacific|Beige Book)\b", re.I)),
)


def _clean(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<!\[CDATA\[|\]\]>", "", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_pub(raw: str) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw.strip())
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)
        creator_m = re.search(r"<dc:creator>(.*?)</dc:creator>", block, re.S)
        cat_matches = re.findall(r"<category[^>]*>(.*?)</category>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        filed = _parse_pub(_clean(date_m.group(1))) if date_m else None
        summary = _clean(desc_m.group(1)) if desc_m else ""
        creator = _clean(creator_m.group(1)) if creator_m else ""
        categories = " | ".join(_clean(c) for c in cat_matches if _clean(c))

        if not title:
            continue
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append(
            {
                "filed_utc": filed,
                "kind": _classify(title, summary, categories),
                "creator": creator[:40],
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
                "categories": categories[:200],
            }
        )
    rows.sort(key=lambda r: r["filed_utc"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[sffed] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[sffed] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[sffed] no items parsed")
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
    print(f"[sffed] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
