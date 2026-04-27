#!/usr/bin/env python3
"""build_ecb_press.py — Spoke 406.

European Central Bank press releases + speeches + meeting accounts.
Distinct from build_ecb_fx.py (FX reference rates) and
build_ecb_monetary.py (BSI + yield curve) — this captures the
communication channel: rate decisions, meeting accounts, exec-board
speeches, digital-euro updates, CES inflation-expectations survey.

Lagarde + Lane + Schnabel speeches move EURUSD ±30-80bps intraday and
reshape Bund curve. ECB MP decisions are the #2 global rate anchor
after the Fed and drive SX5E, DAX, CAC, FTSE, US-listed EU ADRs
(ASML, NVO, SAP, AZN, BUD, UL, MC.PA, OR.PA) + EU banks (BNP, SAN,
DBK, ING, UBS).

stdlib only.
"""
from __future__ import annotations

import csv
import html
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED_URL = "https://www.ecb.europa.eu/rss/press.html"
UA = "Mozilla/5.0 CatalystEdge/1.0 (opensource@example.com)"
OUT = Path(__file__).resolve().parent / "ecb_press.csv"

ITEM_RE = re.compile(r"<item\b[^>]*>(.*?)</item>", re.S)

def _t(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return html.unescape((m.group(1) if m else "")).strip()

# Priority-ordered — first match wins
_RULES: list[tuple[str, re.Pattern]] = [
    ("mp_decision",    re.compile(r"\b(Monetary policy decisions|ECB.*rate|interest rate decision|Governing Council.*rate|deposit facility rate|MRO|main refinancing)\b", re.I)),
    ("mp_account",     re.compile(r"\bMeeting of \d+[-–]\d+ (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.I)),
    ("mp_statement",   re.compile(r"\b(monetary policy statement|press conference|Lagarde.*press conference)\b", re.I)),
    ("speech_lagarde", re.compile(r"\bChristine Lagarde:", re.I)),
    ("speech_lane",    re.compile(r"\bPhilip R?\.? Lane:", re.I)),
    ("speech_schnabel",re.compile(r"\bIsabel Schnabel:", re.I)),
    ("speech_cipollone",re.compile(r"\bPiero Cipollone:", re.I)),
    ("speech_guindos", re.compile(r"\bLuis de Guindos:", re.I)),
    ("speech_board",   re.compile(r"\b(Elderson|Buch|Tuominen|McCaul):", re.I)),
    ("digital_euro",   re.compile(r"\b(digital euro|central bank digital currency|CBDC)\b", re.I)),
    ("ces",            re.compile(r"\b(Consumer Expectations Survey|CES.*results|ECB Survey of Professional Forecasters|SPF)\b", re.I)),
    ("payments",       re.compile(r"\b(payments infrastructure|TARGET2|T2S|TIPS|Eurosystem.*payments|SEPA|instant payments)\b", re.I)),
    ("banking",        re.compile(r"\b(Banking Union|SSM|Single Supervisory|bank competitiveness|supervisory priorities|stress test|SREP)\b", re.I)),
    ("economic",       re.compile(r"\b(euro area economy|Economic Bulletin|economic outlook|inflation outlook|growth forecast)\b", re.I)),
    ("sustainability", re.compile(r"\b(climate|green bond|sustainability|transition risk)\b", re.I)),
    ("imf_imfc",       re.compile(r"\b(IMFC Statement|IMF meeting|G7|G20)\b", re.I)),
    ("market_ops",     re.compile(r"\b(tender|auction|liquidity providing|refinancing operation|LTRO|TLTRO|PELTRO)\b", re.I)),
]

def classify(title: str) -> str:
    for kind, rx in _RULES:
        if rx.search(title):
            return kind
    return "press"

def parse_date(s: str) -> str:
    if not s:
        return ""
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""

def fetch() -> list[dict]:
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        body = r.read().decode("utf-8-sig", "ignore")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []
    for block in ITEM_RE.findall(body):
        title = _t(block, "title")
        if not title:
            continue
        rows.append({
            "filed":       parse_date(_t(block, "pubDate")),
            "kind":        classify(title),
            "title":       title[:240],
            "url":         _t(block, "link"),
            "captured_at": now,
        })
    return rows

def main() -> int:
    try:
        rows = fetch()
    except Exception as exc:
        print(f"ecb_press: fetch failed: {exc}", file=sys.stderr)
        return 1

    fields = ["filed", "kind", "title", "url", "captured_at"]

    if not rows and OUT.exists() and OUT.stat().st_size > 200:
        print("ecb_press: empty fetch; preserving last-good CSV", file=sys.stderr)
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
    print(f"ecb_press: {len(rows)} items | {summary}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
