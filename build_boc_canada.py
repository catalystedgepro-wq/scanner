#!/usr/bin/env python3
"""build_boc_canada.py — Spoke 405.

Bank of Canada press releases — CB-Wiki RSS-CB 1.2 RDF feed. Captures:
- Fixed Announcement Date (FAD) policy-rate decisions (8 per year)
- Governing Council appointments / departures
- Retail-payments compliance orders (CRPO supervisor actions)
- Surveys (Business Outlook / Senior Loan Officer)
- Speeches, research papers, banknote announcements

CAD is a petro-currency tied to WTI/WCS; BoC FAD rate decisions move
USDCAD ±50-120bps intraday and pass through to XEG.TO / XOP / oil majors
(CNQ, SU, CVE, IMO) and US-listed Canadian cross-listings (BNS, TD, RY,
ENB, TRP). BoC is also one of the most hawkish-to-dovish pivot tells
among G10 central banks.

stdlib only.
"""
from __future__ import annotations

import csv
import html
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FEED_URL = "https://www.bankofcanada.ca/content_type/press-releases/feed/"
UA = "Mozilla/5.0 CatalystEdge/1.0 (opensource@example.com)"
OUT = Path(__file__).resolve().parent / "boc_canada.csv"

# RDF uses <item rdf:about="...">...</item> — same close tag
ITEM_RE = re.compile(r'<item\b[^>]*>(.*?)</item>', re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
LINK_RE  = re.compile(r"<link>(.*?)</link>", re.S)
DESC_RE  = re.compile(r"<description>(.*?)</description>", re.S)
DATE_RE  = re.compile(r"<dc:date>(.*?)</dc:date>", re.S)
CBTYPE_RE = re.compile(r'<rdf:type rdf:resource="[^"]*#(\w+)"', re.S)
OCCUR_RE  = re.compile(r"<cb:occurrenceDate>(.*?)</cb:occurrenceDate>", re.S)
RATE_RE   = re.compile(r"(?:target for the overnight rate|policy rate|Bank Rate)[^\d]{0,50}(\d{1,2}(?:[¼½¾]|\.\d{1,2}))\s*(?:%|percent)?", re.I)
RATE_FRAC = {"¼": 0.25, "½": 0.50, "¾": 0.75, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}

# Priority-ordered classifier — first match wins
_RULES: list[tuple[str, re.Pattern]] = [
    ("fad",          re.compile(r"\b(maintains policy rate|raises policy rate|lowers policy rate|increases policy rate|reduces policy rate|Bank of Canada (raises|lowers|maintains|cuts|hikes)|target for the overnight rate|fad-press-release|Fixed Announcement Date)\b", re.I)),
    ("mpr",          re.compile(r"\b(Monetary Policy Report)\b", re.I)),
    ("governance",   re.compile(r"\b(Governing Council|Deputy Governor|appointment|resignation|retirement|Governor Macklem|new Governor)\b", re.I)),
    ("compliance",   re.compile(r"\b(compliance order|retail payment|PSP registration|supervisory action|RPAA)\b", re.I)),
    ("survey",       re.compile(r"\b(Business Outlook Survey|Senior Loan Officer|Canadian Survey of Consumer Expectations|Market Participants Survey|BOS)\b", re.I)),
    ("markets",      re.compile(r"\b(open market operation|auction result|term repo|Standing Liquidity|government securities auction|bond buyback)\b", re.I)),
    ("banknotes",    re.compile(r"\b(banknote|bank note|new \$\d+|polymer note|currency design)\b", re.I)),
    ("speech",       re.compile(r"\b(speech|remarks|keynote|address) by\b", re.I)),
    ("research",     re.compile(r"\b(Staff Analytical Note|Staff Working Paper|Staff Discussion Paper|Financial System Review|BoC Review|Research Paper)\b", re.I)),
    ("triennial",    re.compile(r"\b(Triennial Central Bank Survey|BIS Triennial)\b", re.I)),
    ("challenge",    re.compile(r"\b(Governors' Challenge|economics competition)\b", re.I)),
]

def classify(title: str, cb_type: str) -> str:
    for kind, rx in _RULES:
        if rx.search(title):
            return kind
    # CB-Wiki type fallback
    t = cb_type.lower() if cb_type else ""
    if t in ("interestratedecision", "monetarypolicy"):
        return "fad"
    if t == "speech":
        return "speech"
    if t == "exchangerate":
        return "markets"
    if t == "statisticalrelease":
        return "markets"
    return "press"

def extract_rate(desc: str) -> str:
    desc = html.unescape(desc or "")
    m = RATE_RE.search(desc)
    if not m:
        return ""
    tok = m.group(1)
    # Handle unicode fractions: "2¼" -> 2.25
    if any(c in tok for c in "¼½¾⅛⅜⅝⅞"):
        base = re.sub(r"[¼½¾⅛⅜⅝⅞]", "", tok)
        frac = next((RATE_FRAC[c] for c in tok if c in RATE_FRAC), 0.0)
        try:
            return f"{float(base) + frac:.2f}"
        except ValueError:
            return ""
    try:
        return f"{float(tok):.2f}"
    except ValueError:
        return ""

def norm_date(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000").replace(":00+00:00", "+0000"), fmt)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    # ISO with colon in offset
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return s[:10]

def fetch() -> list[dict]:
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        body = r.read().decode("utf-8-sig", "ignore")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []
    for block in ITEM_RE.findall(body):
        title = html.unescape((TITLE_RE.search(block).group(1) if TITLE_RE.search(block) else "")).strip()
        if not title:
            continue
        link = (LINK_RE.search(block).group(1) if LINK_RE.search(block) else "").strip()
        desc = (DESC_RE.search(block).group(1) if DESC_RE.search(block) else "").strip()
        dt_src = (DATE_RE.search(block).group(1) if DATE_RE.search(block) else "")
        occ_src = (OCCUR_RE.search(block).group(1) if OCCUR_RE.search(block) else "")
        cb_type = (CBTYPE_RE.search(block).group(1) if CBTYPE_RE.search(block) else "")

        rows.append({
            "filed":       norm_date(dt_src),
            "occurs":      norm_date(occ_src),
            "kind":        classify(title, cb_type),
            "cb_type":     cb_type,
            "rate_pct":    extract_rate(desc),
            "title":       title[:240],
            "url":         link,
            "captured_at": now,
        })
    return rows

def main() -> int:
    try:
        rows = fetch()
    except Exception as exc:
        print(f"boc_canada: fetch failed: {exc}", file=sys.stderr)
        return 1

    fields = ["filed", "occurs", "kind", "cb_type", "rate_pct", "title", "url", "captured_at"]

    if not rows and OUT.exists() and OUT.stat().st_size > 200:
        print("boc_canada: empty fetch; preserving last-good CSV", file=sys.stderr)
        return 0

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["kind"]] = tally.get(r["kind"], 0) + 1
    summary = " ".join(f"{k}={v}" for k, v in sorted(tally.items(), key=lambda x: -x[1]))
    rate_rows = [r for r in rows if r["rate_pct"]]
    rate_line = f" | latest rate: {rate_rows[0]['rate_pct']}%" if rate_rows else ""
    print(f"boc_canada: {len(rows)} items | {summary}{rate_line}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
