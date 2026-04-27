#!/usr/bin/env python3
"""
build_msrb_muni.py — Municipal Securities Rulemaking Board (MSRB) tape.

Source: https://www.msrb.org/rss.xml (RSS 2.0 w/ dc:creator)

MSRB is the SRO that writes rules for municipal-securities dealers, municipal
advisors, and EMMA continuing disclosure. Its rulemaking cycle moves the
muni-bond market directly: G-27 supervision, G-17 fair dealing, G-15 customer
confirms, G-23 financial advisors, G-37 political contributions, G-42 advisor
fiduciary duty.

Output: msrb_muni.csv — filed_utc, kind, title, link, creator, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

URL = "https://www.msrb.org/rss.xml"
OUT = pathlib.Path(__file__).resolve().parent / "msrb_muni.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered, first-match-wins. More-specific kinds before broader ones.
KIND_RULES = [
    ("rule_proposal",   re.compile(r"\b(draft amendment|proposed amendment|seeks comment|request for comment|notice of filing|proposed rule change|rfc|comment period|final day to comment|file\s+no\s+SR-MSRB)\b", re.I)),
    ("rulemaking",      re.compile(r"\bRule\s+[A-Z]-\d|\b(amend(ment|s)?|rulemaking|modernization|rule change|supplementary material)\b", re.I)),
    ("board_meeting",   re.compile(r"\b(quarterly board meeting|board meeting|strategic plan|board approves|discussion topics|board announces)\b", re.I)),
    ("annual_report",   re.compile(r"\b(annual report|audited financial statement|financial statements|fiscal year)\b", re.I)),
    ("emma_disclosure", re.compile(r"\b(emma|electronic municipal market access|continuing disclosure|material event|15c2-12|primary offering|official statement)\b", re.I)),
    ("enforcement",     re.compile(r"\b(fine|censure|suspension|bar|settlement|enforcement|compliance action|disciplinary|letter of acceptance|consent order)\b", re.I)),
    ("research",        re.compile(r"\b(research|study|market transparency|data report|statistics|trade activity|muni facts|fact book|market structure analysis)\b", re.I)),
    ("transparency",    re.compile(r"\b(transparency|market data|real-time transaction|rtrs|short-term|variable rate|price transparency|yield disclosure)\b", re.I)),
    ("advisor",         re.compile(r"\b(municipal advisor|MA rule|fiduciary duty|G-42|G-44|advisor qualification|advisor conduct)\b", re.I)),
    ("dealer",          re.compile(r"\b(dealer supervision|broker-dealer|G-27|G-17|G-15|G-23|underwriter|syndicate|customer confirm)\b", re.I)),
    ("update",          re.compile(r"\b(msrb update|newsletter|winter|spring|summer|fall|quarterly)\b", re.I)),
    ("conference",      re.compile(r"\b(conference|summit|symposium|workshop|annual meeting|webinar|roundtable)\b", re.I)),
    ("testimony",       re.compile(r"\b(testimony|congress|hearing|before the\b|sec|scotus)\b", re.I)),
    ("survey",          re.compile(r"\b(survey|feedback|questionnaire)\b", re.I)),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def unescape_clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def extract_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)
    return unescape_clean(m.group(1)) if m else ""


def to_iso_utc(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def classify(title: str, summary: str) -> str:
    hay = f"{title}  {summary}"
    for name, pat in KIND_RULES:
        if pat.search(hay):
            return name
    return "press"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        creator = extract_tag(raw, "dc:creator")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        # Drop survey/event noise at the description level to keep tape signal.
        kind = classify(title, summary)
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": title[:240],
            "link": link,
            "creator": creator,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"msrb_muni: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "kind", "title", "link", "creator", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"msrb_muni: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"msrb_muni: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
