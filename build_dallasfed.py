#!/usr/bin/env python3
"""build_dallasfed.py — Dallas Fed 4-feed merge firehose.

Source: dallasfed.org/rss/{dallasfed,releases,speeches,updates}.xml (RSS 2.0,
CST timezone, ~50 items per feed, free, no key).

11th District = Texas + northern Louisiana + southern New Mexico. Dominates
US energy sector (XLE majors, Permian E&P, Gulf refiners, LNG export). FOMC
voter Lorie Logan is Dallas Fed president — hawkish framework setter.

Signal drivers:
  - Dallas Fed Energy Survey (quarterly) = ONLY Fed-produced crude + natgas
    producer-sentiment index → moves XLE/XOP/OIH/VLO/EOG/PXD/FANG ±1-3%
  - Texas Business Outlook Surveys (monthly manufacturing/service/retail)
  - Texas Employment Forecast (monthly) = leading indicator for US payrolls
  - Lorie Logan speeches → TLT/TBT Fed-path ±30-100bps on hawkish-tilt
  - 11th District Beige Book inputs → SPY/QQQ pre-FOMC positioning
  - SW border / Mexico trade exposure → USMCA policy signal unique to Dallas

Taxonomy (priority-ordered, first-match-wins):
  beige_book / speech / energy / texas_econ / mexico_border /
  regional_economy / banking / research / press
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
    ("dallasfed", "https://www.dallasfed.org/rss/dallasfed.xml"),
    ("releases", "https://www.dallasfed.org/rss/releases.xml"),
    ("speeches", "https://www.dallasfed.org/rss/speeches.xml"),
    ("updates", "https://www.dallasfed.org/rss/updates.xml"),
)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "dallasfed.csv"
FIELDS = ["filed_utc", "source", "kind", "title", "link", "summary"]

CST = dt.timezone(dt.timedelta(hours=-6))

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("beige_book", re.compile(r"\b(beige book|eleventh district|11th district)\b", re.I)),
    ("speech", re.compile(r"\b(speech|remarks|Logan|president's|keynote|commencement|address)\b", re.I)),
    ("energy", re.compile(r"\b(energy survey|oil|crude|natural gas|natgas|Permian|LNG|refinery|drilling|rig count|petroleum|upstream|midstream|shale|WTI)\b", re.I)),
    ("texas_econ", re.compile(r"\b(Texas|employment forecast|business outlook|manufacturing outlook|service sector|retail outlook|economic indicator|Texas Business)\b", re.I)),
    ("mexico_border", re.compile(r"\b(Mexico|border|SW border|El Paso|Laredo|maquiladora|USMCA|cross-border|Rio Grande)\b", re.I)),
    ("regional_economy", re.compile(r"\b(regional|district|Louisiana|New Mexico|Houston|Dallas|Austin|San Antonio|Fort Worth)\b", re.I)),
    ("banking", re.compile(r"\b(bank|supervision|community bank|banking condition|financial institution|SOFR|discount window)\b", re.I)),
    ("research", re.compile(r"\b(research|working paper|Economic Letter|Staff Paper|staff report|data brief|chart|study)\b", re.I)),
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
        raw = raw.strip()
        # CST isn't RFC-2822 — substitute numeric offset.
        patched = re.sub(r"\bCST\b", "-0600", raw)
        patched = re.sub(r"\bCDT\b", "-0500", patched)
        parsed = parsedate_to_datetime(patched)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CST)
        return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify(title: str, summary: str) -> str:
    hay = f"{title} {summary}"
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(hay):
            return kind
    return "press"


def _fetch_feed(source: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    rows: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)
        pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        summary = _clean(desc_m.group(1)) if desc_m else ""
        filed_utc = _parse_pubdate(_clean(pub_m.group(1)) if pub_m else "")

        if not title:
            continue

        rows.append(
            {
                "filed_utc": filed_utc,
                "source": source,
                "kind": _classify(title, summary),
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
            }
        )
    return rows


def _fetch() -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for source, url in FEEDS:
        try:
            rows = _fetch_feed(source, url)
        except Exception as exc:
            print(f"[dallasfed] {source} fetch failed: {exc}")
            continue
        for row in rows:
            key = row["link"] or row["title"]
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    merged.sort(key=lambda r: r["filed_utc"], reverse=True)
    return merged


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[dallasfed] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[dallasfed] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[dallasfed] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    src_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for row in rows:
        src_counts[row["source"]] = src_counts.get(row["source"], 0) + 1
        kind_counts[row["kind"]] = kind_counts.get(row["kind"], 0) + 1
    src_tally = " ".join(f"src={k}={v}" for k, v in sorted(src_counts.items(), key=lambda x: (-x[1], x[0])))
    kind_tally = " ".join(f"{k}={v}" for k, v in sorted(kind_counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[dallasfed] wrote {OUT.name} items={len(rows)} {src_tally} | kinds {kind_tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
