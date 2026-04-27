#!/usr/bin/env python3
"""build_bbc_business.py — BBC News Business RSS firehose.

Source: feeds.bbci.co.uk/news/business/rss.xml (RSS 2.0, ~15-item rolling,
free, no key, 15-min ttl). Distinct from existing spokes (no bbc_* spoke
exists). Global-business editorial tape drives FTSE/DAX/CAC/Nikkei intraday,
sets macro theme for US pre-market, captures central-bank commentary, M&A
deals, oil/energy, mortgage/housing, big-tech, and consumer-economy signals
unavailable in single-country statistical-agency feeds. Institutionally read
by buy-side across EU/UK timezones — moves sterling, euro, Brent.

Taxonomy (priority-ordered, first-match-wins):
  monetary_policy / energy / m_a / corp_earnings / banking / tech /
  labor / geopolitics / housing / macro_policy / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://feeds.bbci.co.uk/news/business/rss.xml"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "bbc_business.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("monetary_policy", re.compile(r"\b(Fed|Federal Reserve|ECB|European Central Bank|BoE|Bank of England|BoJ|Bank of Japan|PBoC|interest rate|rate cut|rate hike|rate rise|base rate|inflation|CPI|RPI|monetary policy|yield|gilts?|treasur(y|ies)|bond market|MPC|FOMC|Powell|Bailey|Lagarde)\b", re.I)),
    ("energy", re.compile(r"\b(oil|Brent|WTI|crude|OPEC|OPEC\+|gas price|natural gas|petrol|diesel|energy bill|power price|Shell|BP|TotalEnergies|Equinor|Saudi Aramco|Gazprom|Ofgem|price cap|refinery|Strait of Hormuz|pipeline|LNG|renewable|wind farm|solar farm|EDF|Centrica)\b", re.I)),
    ("m_a", re.compile(r"\b(merger|acquisition|takeover|takeover bid|buyout|bidder|buy out|bought by|to buy|acquire(?:d|s)?|deal worth|all-share|private equity|PE firm|KKR|Blackstone|Carlyle|Apollo|Bain Capital|CVC|antitrust|CMA block|divest|spin[- ]off|tie[- ]up)\b", re.I)),
    ("corp_earnings", re.compile(r"\b(profits? (?:up|down|rise|fall|slump|surge|jump)|results|full[- ]year|half[- ]year|quarterly|trading update|revenue|turnover|guidance|profit warning|sales grew|sales fell|outlook cut|outlook raised|earnings|dividend|share buyback|CEO|CFO|chief executive)\b", re.I)),
    ("banking", re.compile(r"\b(bank|lender|lending|mortgage|Barclays|HSBC|Lloyds|NatWest|Santander|JPMorgan|Goldman|Morgan Stanley|Citigroup|Deutsche Bank|UBS|Credit Suisse|BNP|Nationwide|Halifax|building society|fintech|credit card|credit union|FCA|PRA|stress test)\b", re.I)),
    ("tech", re.compile(r"\b(Apple|Google|Alphabet|Microsoft|Amazon|Meta|Facebook|Tesla|Nvidia|OpenAI|ChatGPT|AI|artificial intelligence|chip|semiconductor|TSMC|Samsung|cybersecurity|data breach|tech giant|big tech|Silicon Valley|startup|app store|streaming|Netflix|Disney\+|cloud comput)\b", re.I)),
    ("labor", re.compile(r"\b(unemployment|job(?:s|less)?|wage|pay rise|pay deal|pay cut|salary|workforce|layoff|redundancy|redundancies|hiring|recruit|minimum wage|living wage|strike|walkout|industrial action|union|trade union|staff cut|job cut)\b", re.I)),
    ("geopolitics", re.compile(r"\b(sanctions?|tariff|trade war|trade deal|Brexit|EU trade|WTO|China trade|Russia|Ukraine|Israel|Iran|Taiwan|export ban|embargo|customs|border check|supply chain|chip ban)\b", re.I)),
    ("housing", re.compile(r"\b(house price|housing market|property market|mortgage|rent(?:al|ing|s)|landlord|tenant|first[- ]time buyer|Nationwide HPI|Halifax HPI|Rightmove|Zoopla|stamp duty|planning|housebuilder|Barratt|Persimmon|Taylor Wimpey|council tax)\b", re.I)),
    ("macro_policy", re.compile(r"\b(Chancellor|Budget|Autumn Statement|Spring Statement|fiscal|Treasury|HMRC|tax|VAT|income tax|national insurance|public (?:spending|finances|debt)|OBR|Office for Budget|GDP|recession|economy grew|economy shrank|IMF forecast|OECD forecast)\b", re.I)),
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
    for block in re.findall(r"<item>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        filed = _parse_pub(_clean(date_m.group(1))) if date_m else None
        summary = _clean(desc_m.group(1)) if desc_m else ""

        if not title:
            continue
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append(
            {
                "filed_utc": filed,
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
        print(f"[bbc_business] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[bbc_business] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[bbc_business] no items parsed")
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
    print(f"[bbc_business] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
