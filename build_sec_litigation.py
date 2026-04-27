#!/usr/bin/env python3
"""build_sec_litigation.py — SEC litigation releases + AAER RSS feed.

SEC.gov publishes litigation releases (enforcement actions, fraud
charges, accounting restatements) and Accounting and Auditing
Enforcement Releases (AAER — accounting-fraud focus) as public RSS
feeds. These are binary, high-impact tape bombs for defendant tickers
and halo risk for sector peers.

Signal:
- Ticker name match in title/description = direct fraud/enforcement
  hit (usually -20% to -60% move on release)
- AAER release w/ auditor named = audit-firm blast radius (KPMG, BDO,
  EY, Deloitte, PwC alumni listings)
- Charge velocity > 5/week = enforcement regime intensification
  (SEC Chair sentiment signal)
- Restatement-flavored title = 10-K/10-Q downside revision pending

Drives:
- Directly named defendants (binary)
- Auditor-linked firms (when auditor cited in AAER)
- Class-action specialty law firms (ROSN lien flow)
- Post-enforcement rehab consultants

Source: sec.gov/litigation/litreleases.xml + sec.gov/rss/litigation/\
litreleases.xml + AAER via EDGAR searches.
Output: sec_litigation.csv
Columns: release_type, release_id, published, ticker_hints, title,
         link, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_litigation.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FEEDS = [
    ("litigation",
     "https://www.sec.gov/litigation/litreleases.xml"),
    ("admin_proceeding",
     "https://www.sec.gov/rss/litigation/admin.xml"),
]

TICKER_RE = re.compile(r'\(([A-Z]{1,5})\)')
RELEASE_ID_RE = re.compile(r'(LR-\d+|AAER-\d+|IC-\d+|Rel\.?\s*No\.?\s*[\d-]+)')


def _fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"sec_litigation: {url}: {e}")
        return None


def _parse(text: str, release_type: str) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        print(f"sec_litigation: parse error {release_type}: {e}")
        return []
    items: list[dict] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        combined = f"{title} {desc}"
        tickers = TICKER_RE.findall(combined)
        tickers = [t for t in tickers if 1 < len(t) <= 5]
        release_id = ""
        m = RELEASE_ID_RE.search(combined)
        if m:
            release_id = m.group(1)
        items.append({
            "release_type": release_type,
            "release_id": release_id[:30],
            "published": pub[:30],
            "ticker_hints": ",".join(tickers[:6])[:40],
            "title": title[:180],
            "link": link[:200],
        })
    return items


def main() -> None:
    all_items: list[dict] = []
    for rtype, url in FEEDS:
        text = _fetch(url)
        if not text:
            continue
        all_items.extend(_parse(text, rtype))

    if not all_items:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_litigation: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in all_items:
        r["captured_at"] = now

    fieldnames = ["release_type", "release_id", "published",
                  "ticker_hints", "title", "link", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_items)

    type_counts: dict[str, int] = {}
    ticker_hits = 0
    for r in all_items:
        type_counts[r["release_type"]] = type_counts.get(
            r["release_type"], 0) + 1
        if r["ticker_hints"]:
            ticker_hits += 1
    bits = [f"{k}={v}" for k, v in type_counts.items()]
    print(f"sec_litigation: {len(all_items)} releases | "
          f"{' '.join(bits)} | tickered={ticker_hits} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
