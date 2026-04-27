#!/usr/bin/env python3
"""build_cbo_fiscal.py - Congressional Budget Office publications feed.

CBO is the nonpartisan federal agency that scores bill costs, projects
budget baselines, and produces the 10-year fiscal outlook that drives
Treasury debt issuance assumptions. Its tape feeds:
- Treasury yields (fiscal-deficit premium, debt-ceiling projection)
- defense primes (NOC LMT RTX GD LHX) on DoD authorization scores
- healthcare (UNH HUM CNC CVS HCA) on Medicare/Medicaid cost estimates
- infrastructure (CAT DE URI VMC MLM) on appropriations scoring
- tax policy (IRS-exposed issuers) on receipts-side scoring
- entitlements (Social Security trust fund projection => life insurers)

No existing `cbo_`, `congressional_budget_`, or `bill_score_` spoke.

8-kind priority-ordered classifier on title + description:
- budget_baseline      : baseline projection, 10-year outlook, long-term
- economic_outlook     : economic forecast, GDP/CPI/unemployment projection
- monthly_budget       : monthly budget review, MBR, receipts/outlays/deficit
- bill_score           : H.R./S. bill cost estimate ("As ordered reported")
- suspension_rules     : weekly suspension-of-rules aggregator
- testimony            : Director testimony before Budget/Appropriations
- working_paper        : CBO working papers, technical reports, methodology
- press                : fallback

Source: cbo.gov/publications-rss.xml (RSS 2.0). Output: cbo_fiscal.csv
Columns: filed, kind, title, url, captured_at
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cbo_fiscal.csv"
FEED = "https://www.cbo.gov/publications/all/rss.xml"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("budget_baseline",   ["budget and economic outlook", "baseline budget",
                           "baseline projection", "10-year outlook",
                           "long-term budget outlook", "budget outlook",
                           "fiscal outlook", "baseline projections"]),
    ("economic_outlook",  ["economic outlook", "economic forecast",
                           "economic projection", "economic assumptions",
                           "gdp projection", "inflation projection",
                           "unemployment projection"]),
    ("monthly_budget",    ["monthly budget review", "monthly budget",
                           " mbr ", "fiscal year receipts", "fiscal year outlays"]),
    ("bill_score",        ["as ordered reported", "cost estimate",
                           "as reported by the", "as introduced",
                           " h.r. ", " h.r.", " s. ", "senate bill",
                           "house bill"]),
    ("suspension_rules",  ["suspension of the rules",
                           "legislation considered under suspension",
                           "under suspension of rules"]),
    ("testimony",         ["testimony", "house appropriations",
                           "senate appropriations", "house budget committee",
                           "senate budget committee", "ways and means",
                           "senate finance", "congressional hearing",
                           "director swagel", "statement of"]),
    ("working_paper",     ["working paper", "technical paper",
                           "methodology", "technical report",
                           "analytical methods"]),
]


def classify(blob: str) -> str:
    hay = " " + blob.lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _strip_tags(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", no_tags).strip()


def _parse_pub(raw: str) -> str | None:
    try:
        parsed = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"cbo_fiscal fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        desc = re.search(r"<description>(.*?)</description>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        filed = _parse_pub(_strip_cdata(d.group(1)))
        if not filed:
            continue
        url = _strip_cdata(l.group(1)).strip()
        description = ""
        if desc:
            description = _strip_tags(html.unescape(_strip_cdata(desc.group(1))))
            description = description[:2000]
        items.append({
            "filed": filed,
            "kind": classify(title + " " + description),
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"cbo_fiscal: no rows; preserved {OUT_CSV.name}")
        return

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat()
    fields = ["filed", "kind", "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in items:
            row["captured_at"] = now
            writer.writerow(row)

    tally: dict[str, int] = {}
    for row in items:
        tally[row["kind"]] = tally.get(row["kind"], 0) + 1
    summary = " ".join(f"{k}={v}" for k, v in sorted(
        tally.items(), key=lambda kv: -kv[1]))
    print(f"cbo_fiscal: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
