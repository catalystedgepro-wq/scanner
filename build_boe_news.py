#!/usr/bin/env python3
"""build_boe_news.py — Bank of England news + publications 2-feed merge.

Source: bankofengland.co.uk/rss/{news,publications} (RSS 2.0, BST timezone
+0100/+0000, free, no key, standard schema).

BoE MPC has 9 voting members (vs FOMC rotation): Governor Bailey, Deputy
Governors Lombardelli (monetary) / Ramsden (markets) / Breeden (financial
stability), Chief Economist Pill, + 4 external members. Every MPC speech
drives GBPUSD ±30-150bps + UK gilt 10y ±5-25bps + FTSE100 ±0.5-2%.

BoE is the **G7 central-bank coverage gap** — paired with existing
`build_boe_rates.py` (IADB numeric series) this gives BoE policy/speech
tape + rate tape; alongside `build_ecb_policy.py` (EU) + `build_boj_japan.py`
(Japan) + `build_boc_canada.py` (Canada) + `build_fed_speeches.py` (US) the
G7 CB speech/policy-tape coverage becomes complete.

Companion spoke to `build_boe_rates.py`:
- boe_rates.py = IADB numeric (Bank Rate, SONIA, 10y gilt)
- boe_news.py  = speeches, MPC minutes, FSR, CP, PRA supervisory

Taxonomy (priority-ordered, first-match-wins):
  mpc / fpc / speech / pra_supervision / financial_stability / resolution /
  fx_operations / weekly_report / consultation / working_paper /
  payments / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEEDS: tuple[tuple[str, str], ...] = (
    ("news", "https://www.bankofengland.co.uk/rss/news"),
    ("publications", "https://www.bankofengland.co.uk/rss/publications"),
)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "boe_news.csv"
FIELDS = ["filed_utc", "source", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mpc", re.compile(r"\b(MPC|Monetary Policy Committee|Monetary Policy Report|MPR|Bank Rate|policy rate|rate decision|monetary policy summary)\b", re.I)),
    ("fpc", re.compile(r"\b(FPC|Financial Policy Committee|counter[- ]cyclical|CCyB|systemic risk buffer)\b", re.I)),
    ("speech", re.compile(r"\b(speech|remarks|Bailey|Lombardelli|Ramsden|Breeden|Pill|Greene|Dhingra|Mann|Taylor|keynote|commencement|address|lecture|testimony)\b", re.I)),
    ("pra_supervision", re.compile(r"\b(PRA|Prudential Regulation|supervisory statement|SS \d+|CP \d+|policy statement|PS \d+|insurer|Solvency II|capital requirement|ICAAP|SREP|banking act)\b", re.I)),
    ("financial_stability", re.compile(r"\b(Financial Stability Report|FSR|stress test|systemic|leverage ratio|macroprudential|NBFI|hedge fund|money market fund)\b", re.I)),
    ("resolution", re.compile(r"\b(resolution|bail[- ]in|MREL|RRD|gone concern|bank failure|Silicon Valley Bank|Credit Suisse|special resolution regime|SRR)\b", re.I)),
    ("fx_operations", re.compile(r"\b(FXJSC|foreign exchange|FX|sterling|GBP|SONIA|overnight|repo|standing facility|reserve)\b", re.I)),
    ("weekly_report", re.compile(r"\b(Weekly Report|weekly balance sheet|bank return|balance sheet)\b", re.I)),
    ("consultation", re.compile(r"\b(consultation paper|CP|discussion paper|DP|call for (evidence|input)|DP \d+|near-final)\b", re.I)),
    ("working_paper", re.compile(r"\b(working paper|staff working|technical paper|research paper|staff paper)\b", re.I)),
    ("payments", re.compile(r"\b(CHAPS|RTGS|digital pound|CBDC|payment system|omnibus account|synchronisation|payment infrastructure)\b", re.I)),
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


def _fetch_feed(source: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
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

        rows.append(
            {
                "filed_utc": filed_utc,
                "source": source,
                "kind": _classify(title, summary),
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
            }
        )
    return rows


def _fetch() -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for source, url in FEEDS:
        try:
            rows = _fetch_feed(source, url)
        except Exception as exc:
            print(f"[boe_news] {source} fetch failed: {exc}")
            continue
        for row in rows:
            key = row["link"] or row["title"]
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    merged.sort(key=lambda r: r["filed_utc"], reverse=True)
    return merged


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[boe_news] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[boe_news] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[boe_news] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    src_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for row in rows:
        src_counts[row["source"]] = src_counts.get(row["source"], 0) + 1
        kind_counts[row["kind"]] = kind_counts.get(row["kind"], 0) + 1
    src_tally = " ".join(f"src={k}={v}" for k, v in sorted(src_counts.items(), key=lambda x: (-x[1], x[0])))
    kind_tally = " ".join(f"{k}={v}" for k, v in sorted(kind_counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[boe_news] wrote {OUT.name} items={len(rows)} {src_tally} | kinds {kind_tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
