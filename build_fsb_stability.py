#!/usr/bin/env python3
"""build_fsb_stability.py - Financial Stability Board press releases.

The FSB (based at BIS Basel) is the G20-mandated coordinator of
global financial-system regulation. Its tape moves every big bank
(JPM BAC C WFC HSBC UBS DBK BNP SAN ICBC), all G-SIB-designated
entities, stablecoin issuers (USDC-USDT), and NBFI complex (hedge
funds, MMFs). No existing `fsb_`, `financial_stability_`, or
`g20_` build_*.py — gap.

8-kind priority-ordered classifier on title + summary:
- g20_letter   : Chair letter to G20, FMCBG
- nbfi         : NBFI, non-bank, money market fund, hedge fund, leverage
- crypto       : crypto-asset, stablecoin, digital asset, tokenization
- resilience   : operational resilience, cyber, third-party, outage
- climate      : climate, transition, green finance, sustainable, net zero
- xborder_pay  : cross-border payments, CPMI, payment roadmap
- annual_rep   : annual report, progress report, stocktake, assessment
- press        : fallback

Source: fsb.org/feed/ (RSS 2.0). Output: fsb_stability.csv
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
OUT_CSV = ROOT / "fsb_stability.csv"
FEED = "https://www.fsb.org/feed/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("g20_letter",  ["chair's letter to g20", "chair letter to g20",
                     "letter to g20", "g20 finance ministers",
                     "fmcbg", "g20 central bank governors"]),
    ("nbfi",        ["nbfi", "non-bank financial", "non-bank financial intermediation",
                     "money market fund", "mmf ", "hedge fund",
                     "leverage in nbfi", "liquidity mismatch"]),
    ("crypto",      ["crypto-asset", "crypto asset", "stablecoin",
                     "digital asset", "tokenization", "bitcoin",
                     "crypto ", "defi "]),
    ("resilience",  ["operational resilience", "cyber", "cybersecurity",
                     "third-party", "third party risk", "outage",
                     "ransomware", "critical third-party"]),
    ("climate",     ["climate", "transition plan", "green finance",
                     "sustainable finance", "net zero", "tcfd",
                     "physical risk"]),
    ("xborder_pay", ["cross-border payment", "cross border payment",
                     "cpmi", "payment roadmap", "payment system"]),
    ("annual_rep",  ["annual report", "progress report", "stocktake",
                     "assessment report", "thematic review",
                     "peer review"]),
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
        print(f"fsb_stability fetch: {exc}")
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
            description = html.unescape(_strip_cdata(desc.group(1)).strip())
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
        print(f"fsb_stability: no rows; preserved {OUT_CSV.name}")
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
    print(f"fsb_stability: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
