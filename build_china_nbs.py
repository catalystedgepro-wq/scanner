#!/usr/bin/env python3
"""build_china_nbs.py - China National Bureau of Statistics press releases.

China is the #2 global GDP — drives CNY/CNH, iron ore, copper, crude,
iShares MSCI China (MCHI/FXI/YINN/YANG/CQQQ), and all US-listed
Chinese ADRs (BABA JD PDD BIDU NIO XPEV LI NTES TME TAL BILI IQ NIU
VIPS TCOM). No existing `china_`, `nbs_`, or `stats_cn_` build_*.py
in inventory — massive macro gap.

NBS English feed publishes 4 blockbuster monthly releases (IP, FAI,
real-estate dev, retail sales) — low item density but maximum signal
concentration. These 4 releases are the core of any China macro
model and move Chinese ADRs ±3-8% same-session on beat/miss.

8-kind priority-ordered classifier on title:
- industrial_production : Industrial Production / Value Added
- retail_sales          : Total Retail Sales of Consumer Goods
- fixed_investment      : Investment in Fixed Assets, FAI
- real_estate           : Investment in Real Estate Development
- cpi                   : Consumer Price Index, CPI
- ppi                   : Producer Price Index, PPI
- gdp                   : Gross Domestic Product, GDP
- press                 : fallback

Source: stats.gov.cn/english/PressRelease/rss.xml (RSS 2.0).
pubDate format `YYYY-MM-DD HH:MM:SS` Beijing time (CST=UTC+8),
converted to UTC. Output: china_nbs.csv
Columns: filed, kind, title, url, captured_at
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "china_nbs.csv"
FEED = "https://www.stats.gov.cn/english/PressRelease/rss.xml"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CST = dt.timezone(dt.timedelta(hours=8))

KIND_RULES: list[tuple[str, list[str]]] = [
    ("industrial_production", ["industrial production", "value added of industrial",
                               "industrial output", "industrial enterprises"]),
    ("retail_sales",          ["retail sales", "consumer goods"]),
    ("fixed_investment",      ["fixed assets", "fixed-asset investment",
                               "fai ", "fixed asset investment"]),
    ("real_estate",           ["real estate", "real-estate", "property"]),
    ("cpi",                   ["consumer price", " cpi ", "cpi ", "consumer-price"]),
    ("ppi",                   ["producer price", " ppi ", "ppi ", "producer-price"]),
    ("gdp",                   ["gross domestic product", " gdp ", "gdp "]),
]


def classify(title: str) -> str:
    hay = " " + title.lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _parse_cst(raw: str) -> str | None:
    raw = raw.strip()
    try:
        naive = dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=CST).astimezone(
        dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"china_nbs fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        filed = _parse_cst(_strip_cdata(d.group(1)))
        if not filed:
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
        print(f"china_nbs: no rows; preserved {OUT_CSV.name}")
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
    print(f"china_nbs: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
