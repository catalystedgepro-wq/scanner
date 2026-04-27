#!/usr/bin/env python3
"""build_fred_blog.py — FRED Blog data-commentary firehose.

Source: fredblog.stlouisfed.org/feed/ (WordPress RSS 2.0 hourly, free, no key,
standard schema with dc:creator + category + content:encoded).

Distinct from `build_stlouisfed.py` (news.research.stlouisfed.org/feed/ =
press + speeches + FRED announcements). FRED Blog = data-visualization
commentary surfacing new-series adoption + macro-data interpretation +
recession-indicator walk-throughs + labor-market dashboards + inflation
decomposition. Hourly build cadence, StL Fed staff economists authorship.

Signal class: **FRED data-curation commentary tape** — 70% of FRED Blog
posts telegraph new data series being added to FRED within 1-4 weeks +
explain methodology behind series revisions + flag regime-change signals
(Sahm Rule crosses, yield-curve inversions, CPI basket revisions). Every
labor/housing/recession-indicator post directly cites series ingested by
`build_fred_macro.py` / `build_nfci.py` / `build_gdpnow.py` / `build_leading_index.py`.

Taxonomy (priority-ordered, first-match-wins):
  recession_indicator / labor_market / inflation / housing / monetary_policy /
  retail_consumer / banking_finance / commodities / international / manufacturing /
  demographics / crypto / data_methodology / fiscal / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://fredblog.stlouisfed.org/feed/"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "fred_blog.csv"
FIELDS = ["filed_utc", "kind", "creator", "title", "link", "summary", "categories"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("recession_indicator", re.compile(r"\b(recession|Sahm Rule|yield curve|inversion|NBER|leading index|LEI|NFCI|business cycle|contraction)\b", re.I)),
    ("labor_market", re.compile(r"\b(unemployment|payroll|employment|JOLTS|job opening|quit rate|labor force|participation|wage|earnings|initial claims|continuing claims|nonfarm)\b", re.I)),
    ("inflation", re.compile(r"\b(inflation|CPI|PCE|core inflation|headline|disinflation|sticky|trimmed mean|median CPI|price level|deflator|shelter)\b", re.I)),
    ("housing", re.compile(r"\b(housing|home price|HPI|mortgage|starts|permits|pending|existing home|new home|rent|shelter|homeowner|foreclosure|affordability)\b", re.I)),
    ("monetary_policy", re.compile(r"\b(monetary policy|Federal Reserve|FOMC|fed funds|policy rate|balance sheet|QT|QE|reserves|SOFR|discount rate)\b", re.I)),
    ("retail_consumer", re.compile(r"\b(retail sales|consumer|CARTS|MRTS|personal consumption|consumer spending|disposable income|saving rate|food service|e-commerce)\b", re.I)),
    ("banking_finance", re.compile(r"\b(bank|loan|credit|deposit|lending|spread|bond|yield|term premium|delinquency|charge-off|financial conditions|systemic)\b", re.I)),
    ("commodities", re.compile(r"\b(oil|crude|natural gas|commodity|gold|copper|wheat|corn|agricultural|energy price|WTI|Brent)\b", re.I)),
    ("international", re.compile(r"\b(international|global|trade|exchange rate|foreign|BRIC|OECD|G7|G20|tariff|export|import|current account|dollar index|DXY)\b", re.I)),
    ("manufacturing", re.compile(r"\b(manufacturing|ISM|PMI|industrial production|capacity utilization|factory|durable goods|new orders|shipments)\b", re.I)),
    ("demographics", re.compile(r"\b(population|demographic|aging|birth|immigration|migration|household formation|census|cohort|generation)\b", re.I)),
    ("crypto", re.compile(r"\b(cryptocurrency|bitcoin|blockchain|digital asset|stablecoin|CBDC|digital currency)\b", re.I)),
    ("data_methodology", re.compile(r"\b(revision|methodology|seasonally adjusted|SAAR|benchmark|rebasing|index weights|chaining|new series|advance data|preliminary)\b", re.I)),
    ("fiscal", re.compile(r"\b(fiscal|deficit|debt|government spending|treasury|tax|budget|CBO|entitlement|Medicare|Social Security)\b", re.I)),
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

        cats = [_clean(c) for c in re.findall(r"<category[^>]*>(.*?)</category>", block, re.S)]
        categories = "|".join(c for c in cats if c)

        if not title:
            continue

        rows.append(
            {
                "filed_utc": filed_utc,
                "kind": _classify(title, summary, categories),
                "creator": creator[:80],
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
        print(f"[fred_blog] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[fred_blog] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[fred_blog] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    kind_counts: dict[str, int] = {}
    for row in rows:
        kind_counts[row["kind"]] = kind_counts.get(row["kind"], 0) + 1
    kind_tally = " ".join(f"{k}={v}" for k, v in sorted(kind_counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[fred_blog] wrote {OUT.name} items={len(rows)} | kinds {kind_tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
