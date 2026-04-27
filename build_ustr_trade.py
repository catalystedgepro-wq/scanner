#!/usr/bin/env python3
"""build_ustr_trade.py - US Trade Representative press feed.

USTR is the Cabinet-level office that executes US trade policy —
tariffs (Section 301/232/122), free trade agreements, WTO disputes,
USMCA labor enforcement (RRM), and Special 301 IP watchlist. Its
tape drives the entire US supply-chain:
- steel/alum (X NUE CLF STLD RS CMC MT) on 232 tariffs
- autos (F GM STLA TSLA) on USMCA + EU/Japan/Korea deals
- semis (INTC AMAT LRCX KLAC NVDA AMD) on 301 China + CHIPS Act
- ag (ADM BG AGCO CTVA NTR MOS) on reciprocal + geographical indications
- pharma (PFE MRK LLY BMY) on FDA mutual-recognition + IP protection
- ocean shipping (MATX ZIM) on trade-deficit + tariff-induced re-routing

No existing `ustr_`, `trade_rep_`, or `section_301_` build_*.py — gap.

10-kind priority-ordered classifier on title + description:
- section_301 : 301 investigation, China tech transfer, forced tech
- section_232 : 232 tariff, steel, aluminum, national security
- section_122 : 122, temporary tariff, IEEPA, reciprocal tariff
- usmca       : USMCA, rapid response, Mexico, Canada labor, RRM
- reciprocal  : Agreement on Reciprocal Trade, new trade deal
- wto         : WTO, dispute settlement, Appellate Body
- ip          : Special 301, intellectual property, IP enforcement, notorious markets
- fta         : free trade agreement, bilateral, market access
- testimony   : Senate, House, committee, hearing, nominee, confirmation
- press       : fallback

Source: ustr.gov/rss.xml (RSS 2.0). Output: ustr_trade.csv
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
OUT_CSV = ROOT / "ustr_trade.csv"
FEED = "https://www.ustr.gov/rss.xml"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("section_301", ["section 301", "301 investigation", "301 tariff",
                     "forced technology transfer", "china 301",
                     "unfair trade practices"]),
    ("section_232", ["section 232", "232 tariff", "steel tariff",
                     "aluminum tariff", "aluminium tariff",
                     "national security tariff"]),
    ("section_122", ["section 122", "ieepa", "reciprocal tariff",
                     "temporary tariff", "emergency tariff",
                     "trade act of 1974"]),
    ("usmca",       ["usmca", "rapid response labor", "rapid response mechanism",
                     " rrm ", "facility-specific rapid response",
                     "labor rights mexico", "u.s.-mexico-canada"]),
    ("reciprocal",  ["reciprocal trade agreement", "agreement on reciprocal",
                     "new trade agreement", "trade deal",
                     "bilateral deal"]),
    ("wto",         [" wto ", "world trade organization", "appellate body",
                     "dispute settlement body", "wto panel",
                     "wto case"]),
    ("ip",          ["special 301", "notorious markets",
                     "intellectual property", "ip enforcement",
                     "copyright piracy", "trade secret",
                     "patent enforcement"]),
    ("fta",         ["free trade agreement", "market access", "tariff reduction",
                     "bilateral trade", "cptpp", "nafta", "tpp",
                     "geographical indication"]),
    ("testimony",   ["senate finance", "house ways and means",
                     "house appropriations", "senate appropriations",
                     "congressional hearing", "confirmation hearing",
                     "opening statement", "nominee", " testimony "]),
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
        print(f"ustr_trade fetch: {exc}")
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
        print(f"ustr_trade: no rows; preserved {OUT_CSV.name}")
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
    print(f"ustr_trade: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
