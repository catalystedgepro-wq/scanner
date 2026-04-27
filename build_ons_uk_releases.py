#!/usr/bin/env python3
"""Office for National Statistics (ONS) UK Release Calendar spoke.

Pulls the rolling release calendar RSS from ons.gov.uk — primary UK macro
data releases (GDP / CPI / labour market / retail sales / trade / public
finances / business stats / population / housing / wellbeing). Distinct
from build_boe_news.py (monetary policy) — this is the UK equivalent of
the US Census/BEA/BLS primary-data-release tape.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "https://www.ons.gov.uk/releasecalendar?rss"
OUT = Path(__file__).resolve().parent / "ons_uk_releases.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("gdp", ("gdp", "gross domestic product", "economic output")),
    ("inflation", ("cpi", "consumer prices", "inflation", "rpi", "ppi", "producer prices", "price index")),
    ("labour_market", ("employment", "unemployment", "labour market", "earnings", "vacancies", "payrolled", "claimant", "wage")),
    ("retail_sales", ("retail sales", "retail trade", "consumer spending")),
    ("trade", ("trade", "import", "export", "balance of payments", "current account")),
    ("public_finances", ("public sector finances", "public sector borrowing", "government debt", "fiscal", "public finance")),
    ("housing", ("house price", "housing", "rental", "private rent", "property")),
    ("population", ("population", "births", "deaths", "families", "households", "census", "migration", "marriage")),
    ("business_stats", ("business", "insolvency", "productivity", "turnover", "research and development", "r&d", "innovation")),
    ("wellbeing", ("wellbeing", "social trends", "public opinion", "life satisfaction", "happiness", "opinions")),
    ("energy", ("energy", "electricity", "gas consumption", "emissions", "environment")),
    ("press", ()),
]


def classify(text: str) -> str:
    low = text.lower()
    for kind, needles in KINDS:
        if not needles:
            continue
        if any(n in low for n in needles):
            return kind
    return "press"


def strip_tags(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(" ".join(s.split())).strip()


def parse_pubdate(raw: str) -> str:
    if not raw:
        return ""
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_items(body: str) -> list[dict]:
    rows: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        def pick(tag: str) -> str:
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return strip_tags(m.group(1)) if m else ""

        title = pick("title")
        link = pick("link")
        desc = pick("description")
        pub = pick("pubDate")
        if not title:
            continue
        kind = classify(f"{title} {desc}")
        rows.append(
            {
                "filed_utc": parse_pubdate(pub),
                "kind": kind,
                "title": title,
                "link": link,
                "summary": desc,
            }
        )
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > 200:
        print(f"[ons_uk] degraded fetch — preserving last-good {OUT.name}", file=sys.stderr)
        return
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["filed_utc", "kind", "title", "link", "summary"])
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    try:
        body = fetch(FEED)
    except Exception as exc:
        print(f"[ons_uk] fetch failed: {exc}", file=sys.stderr)
        return 1
    rows = parse_items(body)
    write_csv(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(f"[ons_uk] {len(rows)} releases | kinds {breakdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
