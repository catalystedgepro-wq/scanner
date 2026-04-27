#!/usr/bin/env python3
"""build_census_news.py — US Census Bureau press-release firehose.

Source: census.gov/newsroom/press-releases.xml (RSS 2.0 custom schema with
empty link/guid elements — title + description + pubDate are the payload).

Census Bureau is the **primary-data-release tape** for US population,
business formation, retail trade (MRTS), wholesale (MWTS), manufacturing
(M3), international trade (FT900/FT920), construction spending, housing
starts/completions, new home sales, American Community Survey (ACS),
Household Pulse Survey, Small Business Pulse Survey, Business Trends and
Outlook Survey (BTOS), Business Formation Statistics (BFS), Business
Dynamics Statistics (BDS), State/Local Government Finance, Quarterly
Summary of State and Local Tax Revenue (QTAX).

Every Census release moves TLT/TBT ±5-30bps + SPY/QQQ/IWM ±0.3-1.5% on
advance monthly retail/housing/trade prints, and directly feeds
`build_fred_macro.py` + `build_leading_index.py` + `build_gdpnow.py` via
the FRED ingestion pipeline within 2-48h of publication.

Distinct from `build_bea_news.py` (BEA GDP/PCE/Personal Income/Corporate
Profits) and `build_fed_register.py` (agency rulemaking) — Census owns
the decennial + ongoing demographic + business survey tape.

Taxonomy (priority-ordered, first-match-wins):
  population / business_stats / employment / retail_wholesale / housing /
  trade / state_local / income_poverty / tech / health / education /
  construction / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://www.census.gov/newsroom/press-releases.xml"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "census_news.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("population", re.compile(r"\b(population|demographic|2020 Census|age|sex|race|ethnicity|birth|fertility|migration|household|name)\b", re.I)),
    ("business_stats", re.compile(r"\b(Business Trends|Business Outlook|BTOS|Business Formation|BFS|Business Dynamics|BDS|Small Business Pulse|economic census)\b", re.I)),
    ("employment", re.compile(r"\b(employment|payroll|QCEW|CES|workforce|job|labor|occupation)\b", re.I)),
    ("retail_wholesale", re.compile(r"\b(retail|wholesale|MRTS|MWTS|Monthly Retail|Monthly Wholesale|Advance Monthly|e-commerce|merchant)\b", re.I)),
    ("housing", re.compile(r"\b(housing|home price|home sale|housing start|housing completion|new residential|building permit|vacancy|American Housing Survey|AHS)\b", re.I)),
    ("trade", re.compile(r"\b(international trade|FT900|FT920|exports|imports|trade balance|trade deficit|goods and services)\b", re.I)),
    ("state_local", re.compile(r"\b(state government|local government|state and local|tax collection|QTAX|SLG|government finance|public employment)\b", re.I)),
    ("income_poverty", re.compile(r"\b(income|poverty|SAIPE|ACS|American Community Survey|SNAP|food stamp|Medicaid|Supplemental)\b", re.I)),
    ("tech", re.compile(r"\b(digital|broadband|computer|internet|technology|ICT|information technology|Current Population Survey Computer)\b", re.I)),
    ("health", re.compile(r"\b(health insurance|SAHIE|Medicare|Medicaid|uninsured|health coverage)\b", re.I)),
    ("education", re.compile(r"\b(education|school|college|enrollment|degree|literacy|graduation)\b", re.I)),
    ("construction", re.compile(r"\b(construction|construction spending|value of construction|VIP|put in place)\b", re.I)),
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


def _classify(title: str, summary: str) -> str:
    hay = f"{title} {summary}"
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

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        summary = _clean(desc_m.group(1)) if desc_m else ""
        filed_utc = _parse_pubdate(_clean(pub_m.group(1)) if pub_m else "")

        if not title:
            continue

        if not link:
            link = "https://www.census.gov/newsroom/press-releases.html"

        rows.append(
            {
                "filed_utc": filed_utc,
                "kind": _classify(title, summary),
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
            }
        )

    rows.sort(key=lambda r: r["filed_utc"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[census_news] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[census_news] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[census_news] no items parsed")
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
    print(f"[census_news] wrote {OUT.name} items={len(rows)} | kinds {kind_tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
