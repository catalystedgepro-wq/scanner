#!/usr/bin/env python3
"""build_congress_bills.py — US Congress bills tape.

Merged spoke pulling two Congress.gov RSS feeds:
  1. presented-to-president.xml  — bills passed both chambers, sent to POTUS
  2. most-viewed-bills.xml       — weekly top-10 most-viewed bills on congress.gov

Both feeds are tiny (1-3KB) but high-signal: bills landing on the President's
desk are ~48h from signature or veto, and most-viewed bills reveal which
legislative proposals are capturing attention ahead of floor action. Both
materially move sector rotation:
  - FISA/intel bills → defense-intel (CRWD PANW LDOS LMT)
  - BLM/land-withdrawal bills → natgas/mining rotation
  - Reconciliation/appropriations → treasury yields, defense, healthcare
  - Obesity/healthcare bills → GLP-1/pharma (NVO LLY)
  - Tax/regulatory reform → broad market multiple

Output: congress_bills_latest.csv
Schema: filed_utc, source, kind, bill_id, title, link, summary

Python stdlib only. Browser UA. Degraded-run guard preserves last-good CSV.
"""

from __future__ import annotations

import csv
import html
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS: list[tuple[str, str]] = [
    ("bills_to_potus", "https://www.congress.gov/rss/presented-to-president.xml"),
    ("most_viewed",    "https://www.congress.gov/rss/most-viewed-bills.xml"),
]

OUT = Path(__file__).resolve().parent / "congress_bills_latest.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("defense_intel",   ("fisa", "intelligence", "intel ", "national security", "counterterror",
                         "surveillance", "defense", "armed forces", "military", "cyber")),
    ("healthcare",      ("obesity", "medicare", "medicaid", "health", "drug pricing", "pharma",
                         "hospital", "medical", "mental health", "opioid", "vaccine")),
    ("immigration",     ("immigration", "border", "dignidad", "dignity act", "asylum",
                         "naturalization", "save act", "visa", "refugee")),
    ("impeachment",     ("impeach", "impeaching")),
    ("energy_land",     ("blm", "bureau of land management", "withdrawal", "public land",
                         "drilling", "pipeline", "fracking", "mining", "natural gas",
                         "oil and gas", "offshore")),
    ("fiscal",          ("reconciliation", "appropriations", "continuing resolution",
                         "budget", "debt limit", "debt ceiling", "spending")),
    ("tax_reform",      ("tax ", "revenue", "irs ", "taxation")),
    ("financial",       ("banking", "securities", "financial", "sec ", "cfpb",
                         "credit union", "fintech", "crypto", "stablecoin")),
    ("trade_tariff",    ("tariff", "trade act", "customs", "import", "export control",
                         "sanctions", "section 301")),
    ("small_business",  ("small business", "sba ", "sbir", "startup", "entrepreneur")),
    ("regulatory",      ("regulatory reform", "regulation", "deregulat", "cra ",
                         "disapproval", "congressional review act")),
    ("tech_ai",         ("artificial intelligence", "ai act", "algorithm", "deepfake",
                         "section 230", "platform", "big tech")),
    ("infrastructure",  ("infrastructure", "highway", "transit", "bridge", "airport",
                         "faa", "dot ", "transportation")),
    ("agriculture",     ("farm bill", "agriculture", "usda", "snap ", "food stamp",
                         "crop insurance")),
    ("press",           ()),
]


def classify(text: str) -> str:
    low = text.lower()
    for kind, needles in KINDS:
        if not needles:
            continue
        if any(n in low for n in needles):
            return kind
    return "press"


def clean(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[", "", text)
    text = re.sub(r"]]>", "", text)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def to_iso(pubdate: str) -> str:
    if not pubdate:
        return ""
    try:
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_field(item: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
    return clean(m.group(1)) if m else ""


def channel_pubdate(body: str) -> str:
    m = re.search(r"<channel[^>]*>(.*?)<item", body, re.S)
    if not m:
        return ""
    head = m.group(1)
    pub = parse_field(head, "pubDate")
    return pub


def parse_potus_items(body: str) -> list[dict]:
    rows: list[dict] = []
    channel_pub = channel_pubdate(body)
    for item in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        bill_id = parse_field(item, "title")
        link = parse_field(item, "link")
        summary = parse_field(item, "description")
        pub = parse_field(item, "pubDate") or channel_pub
        if not bill_id:
            continue
        kind = classify(f"{bill_id} {summary}")
        rows.append({
            "filed_utc": to_iso(pub),
            "source": "bills_to_potus",
            "kind": kind,
            "bill_id": bill_id,
            "title": summary[:200],
            "link": link,
            "summary": summary,
        })
    return rows


BILL_HREF = re.compile(
    r"<a\s+href=['\"](https://www\.congress\.gov/bill/[^'\"]+)['\"]>([^<]+)</a>"
    r"(?:\s*\[[^\]]+\])?\s*[-–]\s*([^<]+?)(?=</li|<li|$)",
    re.I | re.S,
)


def parse_most_viewed(body: str) -> list[dict]:
    rows: list[dict] = []
    channel_pub = channel_pubdate(body)
    for item in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        header = parse_field(item, "title")
        pub = parse_field(item, "pubDate") or channel_pub
        desc_raw_m = re.search(r"<description[^>]*>(.*?)</description>", item, re.S)
        if not desc_raw_m:
            continue
        desc_raw = re.sub(r"<!\[CDATA\[", "", desc_raw_m.group(1))
        desc_raw = re.sub(r"]]>", "", desc_raw)
        desc_raw = html.unescape(desc_raw)
        filed = to_iso(pub)
        for rank, match in enumerate(BILL_HREF.finditer(desc_raw), start=1):
            link, bill_id, title = match.group(1), match.group(2).strip(), match.group(3).strip()
            title = re.sub(r"\s+", " ", title).rstrip(" .,;")
            kind = classify(f"{bill_id} {title}")
            rows.append({
                "filed_utc": filed,
                "source": "most_viewed",
                "kind": kind,
                "bill_id": f"{bill_id} (rank {rank})",
                "title": title[:200],
                "link": link,
                "summary": f"{header}: {title}",
            })
    return rows


def write(rows: list[dict]) -> None:
    cols = ["filed_utc", "source", "kind", "bill_id", "title", "link", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def main() -> int:
    all_rows: list[dict] = []
    errors: list[str] = []
    for source, url in FEEDS:
        try:
            body = fetch(url)
            rows = parse_potus_items(body) if source == "bills_to_potus" else parse_most_viewed(body)
            all_rows.extend(rows)
            print(f"[congress_bills] {source}: {len(rows)} rows", file=sys.stderr)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            errors.append(f"{source}: {exc}")
            print(f"[congress_bills] {source} fetch failed: {exc}", file=sys.stderr)
            continue

    if not all_rows:
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[congress_bills] degraded run: preserving last-good CSV "
                  f"({OUT.stat().st_size}B); errors={errors}", file=sys.stderr)
            return 0
        print(f"[congress_bills] no rows and no last-good CSV; errors={errors}", file=sys.stderr)
        return 1

    all_rows.sort(key=lambda r: (r.get("filed_utc", ""), r.get("source", "")), reverse=True)
    write(all_rows)
    kinds: dict[str, int] = {}
    sources: dict[str, int] = {}
    for r in all_rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        sources[r["source"]] = sources.get(r["source"], 0) + 1
    kind_str = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1]))
    src_str = " ".join(f"{s}={v}" for s, v in sorted(sources.items(), key=lambda x: -x[1]))
    print(f"[congress_bills] wrote {len(all_rows)} rows -> {OUT.name} | "
          f"sources: {src_str} | kinds: {kind_str}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
