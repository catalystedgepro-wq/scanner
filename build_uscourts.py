#!/usr/bin/env python3
"""build_uscourts.py — US Courts (AOUSC) Judiciary News RSS.

Source: uscourts.gov/news/rss (RSS 2.0, ~10-item rolling, free, no key). Distinct
from build_courtlistener_recap.py (PACER case-level tracker) — this is the
Administrative Office of the US Courts official announcements feed. High-signal
macro catalyst: bankruptcy-filings-up prints drive credit-cycle positioning
(COF/SYF/DFS card issuers, ALLY auto lender, KBH mortgage, CRE REITs), judiciary
funding gaps trigger federal-shutdown tape, Chief Justice Year-End Report sets
judicial policy agenda, case-management modernization drives legal-tech (TYL/OTEX/TRI),
courthouse real-property authority moves federal-lease REITs.

Non-standard pubDate: feed uses "2026-03-10 12:00:00" (no TZ, no RFC-2822).
Parser tries parsedate_to_datetime() first, falls back to strptime naive-UTC.

Taxonomy (priority-ordered, first-match-wins):
  bankruptcy / funding / tech_modernization / real_property / policy /
  workload / personnel / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://www.uscourts.gov/news/rss"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "uscourts.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bankruptcy", re.compile(r"\b(bankruptcy|Chapter 7|Chapter 11|Chapter 13|Chapter 15|Subchapter V|trustee|debtor|insolvency|liquidation|reorganization|creditor|BAPCPA)\b", re.I)),
    ("funding", re.compile(r"\b(funding|appropriation|lapse|shutdown|continuing resolution|\bCR\b|fee balance|court fee|limited operations|paid operations|budget crisis|fiscal cliff)\b", re.I)),
    ("tech_modernization", re.compile(r"\b(case management|CM/ECF|PACER|modernization|modernize|accelerated|technology|digital|electronic filing|case file|court technology|cyber|information system)\b", re.I)),
    ("real_property", re.compile(r"\b(courthouse|real property|facilities|\bGSA\b|lease|building|space planning|courtroom|court security|CSO|physical infrastructure)\b", re.I)),
    ("policy", re.compile(r"\b(Judicial Conference|Chief Justice|Year-End Report|rules amendment|Rules of|policy statement|Administrative Office|AOUSC|Judicial Council|Criminal Justice Act)\b", re.I)),
    ("workload", re.compile(r"\b(filings|caseload|civil filing|criminal filing|appeal|docket|pending case|disposition|statistics|workload|judgeship|vacancy|weighted filings)\b", re.I)),
    ("personnel", re.compile(r"\b(Judge [A-Z]|nomination|confirmation|retirement|senior status|Devitt Award|distinguished service|chief district|chief circuit|magistrate judge|bankruptcy judge|clerk of court)\b", re.I)),
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
    # Try RFC-2822 first
    try:
        parsed = parsedate_to_datetime(cleaned)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    # Fall back to uscourts's "YYYY-MM-DD HH:MM:SS" (naive UTC)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(cleaned, fmt).replace(tzinfo=dt.timezone.utc)
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


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
        print(f"[uscourts] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[uscourts] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[uscourts] no items parsed")
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
    print(f"[uscourts] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
