#!/usr/bin/env python3
"""build_aisi_steel.py - American Iron and Steel Institute press RSS.

US steel industry tape: weekly raw steel production, monthly shipments,
SIMA imports, Section 232 tariff policy. Drives X, NUE, STLD, CLF, RS,
MT, CMC, ZEUS, USAP, NWPX. Not on FRED, not in any existing spoke
(checked: no aisi_/steel_ build_*.py files).

7-kind priority-ordered classifier:
- production   : "raw steel production", weekly capacity utilization
- shipments    : "steel shipments", monthly percentage change
- imports      : SIMA imports data (Steel Import Monitoring & Analysis)
- tariffs      : Section 232 / tariff policy
- trade        : WTO / trade remedy / antidumping / countervailing
- policy       : regulatory / legislative / administration
- press        : fallback

Source: steel.org/feed/ (WordPress RSS 2.0, 10-item rolling, free).
Output: aisi_steel.csv
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
OUT_CSV = ROOT / "aisi_steel.csv"
FEED = "https://www.steel.org/feed/"
UA = "CatalystEdge/1.0 (opensource@example.com)"

KIND_RULES: list[tuple[str, list[str]]] = [
    ("production", ["raw steel production", "capacity utilization",
                    "production up", "production down"]),
    ("shipments",  ["steel shipments", "shipments up", "shipments down"]),
    ("imports",    ["sima imports", "steel imports", "import permit",
                    "import data"]),
    ("tariffs",    ["section 232", "tariff", "tariffs"]),
    ("trade",      ["antidumping", "countervailing", "wto", "trade remedy",
                    "trade petition", "commerce department"]),
    ("policy",     ["legislation", "congress", "regulatory", "administration",
                    "rulemaking", "comment", "testimony"]),
]


def classify(title: str) -> str:
    lower = title.lower()
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in lower:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"aisi_steel fetch: {exc}")
        return []

    items = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        try:
            filed = parsedate_to_datetime(d.group(1).strip()).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
        url = _strip_cdata(l.group(1)).strip()
        items.append({
            "filed": filed,
            "kind": classify(title),
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"aisi_steel: no rows; preserved {OUT_CSV.name}")
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
    print(f"aisi_steel: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
