#!/usr/bin/env python3
"""build_bea_news.py — US BEA (Bureau of Economic Analysis) master news RSS.

Source: apps.bea.gov/rss/rss.xml (RSS 2.0 custom-schema with embedded
<data><main><current><percentChange>/<rateChange>/<infoDate>/<previous>
elements, ~30-release rolling, free, no key). Distinct from
build_bea_trade.py (International Transactions-specific). This is the
master release calendar covering: GDP (Advance/Second/Third estimates +
revisions), Personal Income and Outlays (PCE deflator — Fed's preferred
inflation gauge), Corporate Profits, Industry GDP, State/Regional GDP,
Balance of Payments, Direct Investment (FDI), International Services.

Highest-signal US macro prints: PCE Core m/m drives Fed rate path
(TLT/IEF/TBT), GDP Advance drives equity-risk-on (SPY/QQQ/IWM), Corporate
Profits drives SPX EPS valuation anchor, Personal Income drives consumer
discretionary (XLY/AMZN/TGT/WMT), Regional GDP picks state-level winners
(Texas energy → XLE, California tech → XLK, Florida real estate → XHB).

Taxonomy (priority-ordered, first-match-wins):
  gdp / pce_inflation / corporate_profits / trade / regional /
  industry / services / direct_investment / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://apps.bea.gov/rss/rss.xml"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "bea_news.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary", "pct_change", "info_date"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pce_inflation", re.compile(r"\b(Personal Income and Outlays|PCE|personal consumption expenditure|personal saving rate|disposable personal income|DPI)\b", re.I)),
    ("corporate_profits", re.compile(r"\b(Corporate Profits|after[- ]tax profits|profits from current production|book profits|NIPA profits)\b", re.I)),
    ("gdp", re.compile(r"\b(GDP|Gross Domestic Product|advance estimate|second estimate|third estimate|annual update|comprehensive update|real GDP|nominal GDP|GDP growth|GDP by industry|GDP by state)\b", re.I)),
    ("regional", re.compile(r"\b(State GDP|State Personal Income|Regional GDP|Regional Personal Income|Local Area Personal Income|metropolitan area|MSA|county personal income|State Quarterly Personal Income)\b", re.I)),
    ("trade", re.compile(r"\b(International Transactions|Balance of Payments|BOP|current account|trade balance|goods and services|U\.S\. International Trade in Goods|international trade deficit|trade surplus|exports|imports)\b", re.I)),
    ("services", re.compile(r"\b(International Services|trade in services|services exports|services imports|cross[- ]border services|digital services trade)\b", re.I)),
    ("direct_investment", re.compile(r"\b(Direct Investment|FDI|foreign direct investment|Direct Investment Position|Activities of U\.S\. Affiliates|Activities of Multinational Enterprises|MNE|affiliate data)\b", re.I)),
    ("industry", re.compile(r"\b(Industry|GDP by Industry|Industry Economic Accounts|KLEMS|industry value added|sector output|manufacturing GDP|services GDP)\b", re.I)),
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


def _extract_current_data(block: str) -> tuple[str, str]:
    """Pull <current><percentChange> and <infoDate> from BEA custom schema."""
    pct = ""
    info = ""
    current_m = re.search(r"<current>(.*?)</current>", block, re.S)
    if current_m:
        pct_m = re.search(r"<percentChange>([^<]*)</percentChange>", current_m.group(1))
        if pct_m:
            pct = pct_m.group(1).strip()
        info_m = re.search(r"<infoDate>([^<]*)</infoDate>", current_m.group(1))
        if info_m:
            info = info_m.group(1).strip()
    return pct, info


def _fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    rows: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        filed = _parse_pub(_clean(date_m.group(1))) if date_m else None
        summary = _clean(desc_m.group(1)) if desc_m else ""
        pct, info_date = _extract_current_data(block)

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
                "pct_change": pct[:20],
                "info_date": info_date[:40],
            }
        )
    rows.sort(key=lambda r: r["filed_utc"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[bea_news] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[bea_news] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[bea_news] no items parsed")
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
    print(f"[bea_news] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
