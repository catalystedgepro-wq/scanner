#!/usr/bin/env python3
"""build_bostonfed.py — Federal Reserve Bank of Boston news+research+speeches.

Sources (3 RSS feeds merged):
  - news:     https://www.bostonfed.org/feeds/rss_news.xml
  - research: https://www.bostonfed.org/feeds/rss_research.xml
  - speeches: https://www.bostonfed.org/feeds/rss_speeches.xml

Each feed is RSS 2.0 minimal-schema: <item> contains <guid>, <link>,
<description /> (empty), <pubDate>. No <title> tag — title derived from
final URL path segment with dashes→spaces, title-cased.

President Susan M. Collins is FOMC rotating voter; Boston Fed publishes
First-District Beige Book input, runs the stablecoin/tokenization joint
conference with NY Fed, and houses the Supervisory Research and Analysis
group. Highest-signal regional Fed after NY/SF/Philly/Chicago.

Taxonomy (priority-ordered, first-match-wins):
  beige_book / speech / research / payments_fintech /
  financial_stability / housing / labor / regional_economy / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEEDS: tuple[tuple[str, str], ...] = (
    ("news", "https://www.bostonfed.org/feeds/rss_news.xml"),
    ("research", "https://www.bostonfed.org/feeds/rss_research.xml"),
    ("speeches", "https://www.bostonfed.org/feeds/rss_speeches.xml"),
)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "bostonfed.csv"
FIELDS = ["filed_utc", "source", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("beige_book", re.compile(r"\b(beige[- ]book|first district economic|first[- ]district)\b", re.I)),
    ("speech", re.compile(r"\b(susan collins|collins-remarks|fed-listens|speech|remarks|keynote|testimony|address)\b", re.I)),
    ("research", re.compile(r"\b(working[- ]paper|research[- ]paper|current policy perspectives|economic research conference|research department|supervisory research)\b", re.I)),
    ("payments_fintech", re.compile(r"\b(stablecoin|tokenization|cbdc|fedNow|fed[- ]now|payment|fintech|digital[- ]currency|crypto|instant[- ]payment)\b", re.I)),
    ("financial_stability", re.compile(r"\b(financial[- ]stability|private[- ]credit|private[- ]equity|tech[- ]service[- ]provider|bank[- ]stress|systemic|fraud|money[- ]market|stablecoin[- ]risk|concentration)\b", re.I)),
    ("housing", re.compile(r"\b(housing|home[- ]sales|rent|mortgage|home[- ]prices|housing[- ]crisis|single[- ]family)\b", re.I)),
    ("labor", re.compile(r"\b(labor|employment|workforce|job|hiring|unemployment|immigration|workers|workforce[- ]woes)\b", re.I)),
    ("regional_economy", re.compile(r"\b(new[- ]england|massachusetts|maine|vermont|new[- ]hampshire|rhode[- ]island|connecticut|boston|regional)\b", re.I)),
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


def _title_from_link(link: str) -> str:
    if not link:
        return ""
    slug = link.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.aspx?$|\.html?$", "", slug, flags=re.I)
    slug = slug.replace("-", " ").replace("_", " ")
    slug = re.sub(r"\s+", " ", slug).strip()
    if not slug:
        return ""
    return slug[:1].upper() + slug[1:]


def _classify(title: str, link: str) -> str:
    hay = f"{title} {link}"
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(hay):
            return kind
    return "press"


def _fetch_feed(source: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    out: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        desc_m = re.search(r"<description[^/>]*>(.*?)</description>", block, re.S)

        link = _clean(link_m.group(1)) if link_m else ""
        filed = _parse_pub(_clean(date_m.group(1))) if date_m else None
        summary = _clean(desc_m.group(1)) if desc_m else ""
        title = _title_from_link(link)

        if not link or not title:
            continue
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        out.append(
            {
                "filed_utc": filed,
                "source": source,
                "kind": _classify(title, link),
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
            }
        )
    return out


def _fetch_all() -> list[dict]:
    rows: list[dict] = []
    errors: list[str] = []
    for source, url in FEEDS:
        try:
            rows.extend(_fetch_feed(source, url))
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    if errors:
        print(f"[bostonfed] partial errors: {' | '.join(errors)}")
    seen: set[str] = set()
    dedup: list[dict] = []
    for row in rows:
        if row["link"] in seen:
            continue
        seen.add(row["link"])
        dedup.append(row)
    dedup.sort(key=lambda r: r["filed_utc"], reverse=True)
    return dedup


def main() -> int:
    try:
        rows = _fetch_all()
    except Exception as exc:
        print(f"[bostonfed] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[bostonfed] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[bostonfed] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    src_counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        src_counts[row["source"]] = src_counts.get(row["source"], 0) + 1
    tally = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])))
    src_tally = " ".join(f"{k}={v}" for k, v in sorted(src_counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[bostonfed] wrote {OUT.name} items={len(rows)} src={src_tally} kinds={tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
