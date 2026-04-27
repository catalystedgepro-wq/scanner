#!/usr/bin/env python3
"""build_boj_japan.py — Spoke 404.

Bank of Japan "What's New" RSS. Monetary-policy + stats + research tape
for the world's cheapest carry-trade funding currency. JPY moves drive
global risk assets; BoJ decisions on YCC, negative rates, JGB operations
feed directly into SPX + USDJPY + USTs.

Taxonomy (priority-ordered):
  mpm            Monetary Policy Meeting statement / minutes
  mpm_minutes    MPM minutes
  opinions       Summary of Opinions at MPM
  outlook        Outlook for Economic Activity and Prices
  regional       Regional Economic Report
  tankan         Tankan survey
  cgpi           Corporate Goods Price Index (PPI)
  money_stock    Money Stock / Monetary Base
  ops            Market Operations by the Bank
  accounts       BOJ Accounts / transactions w/ government
  balance_sheet  Current Account Balances / JGBs held
  speech         Speeches by Governor / Deputy
  review         BOJ Review / Working paper / Research paper
  press          Press releases / general news

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

FEED_URL = "https://www.boj.or.jp/en/rss/whatsnew.xml"
UA = "Mozilla/5.0 CatalystEdge/1.0 (opensource@example.com)"
OUT = Path(__file__).resolve().parent / "boj_japan.csv"

ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)

def _t(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return html.unescape((m.group(1) if m else "")).strip()

# Priority-ordered classifier
_RULES: list[tuple[str, re.Pattern]] = [
    ("mpm",           re.compile(r"\b(Monetary Policy Meeting|Statement on Monetary Policy|Guidelines for Monetary Market Operations)\b", re.I)),
    ("mpm_minutes",   re.compile(r"\b(Minutes of the Monetary Policy Meeting)\b", re.I)),
    ("opinions",      re.compile(r"\bSummary of Opinions\b", re.I)),
    ("outlook",       re.compile(r"\bOutlook for Economic Activity and Prices\b", re.I)),
    ("regional",      re.compile(r"\bRegional Economic Report\b", re.I)),
    ("tankan",        re.compile(r"\bTankan\b", re.I)),
    ("cgpi",          re.compile(r"\b(Corporate Goods Price Index|Producer Price Index|Services Producer Price)\b", re.I)),
    ("money_stock",   re.compile(r"\b(Money Stock|Monetary Base|Money Supply)\b", re.I)),
    ("ops",           re.compile(r"\b(Market Operations|Outright Purchases?|Loan Support Program|Funds-Supplying Operation)\b", re.I)),
    ("accounts",      re.compile(r"\b(Bank of Japan Accounts|Transactions with the Government)\b", re.I)),
    ("balance_sheet", re.compile(r"\b(Current Account Balances|Japanese Government Bonds Held|JGBs Held|Principal Figures|Fails)\b", re.I)),
    ("speech",        re.compile(r"\b(Speech|Remarks|Keynote) by\b", re.I)),
    ("review",        re.compile(r"\b(BOJ Review|Working Paper|Research Paper|Research Lab|Bank of Japan Working Paper)\b", re.I)),
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
        print(f"boj_japan: fetch failed: {exc}", file=sys.stderr)
        return 1

    fields = ["filed", "kind", "title", "url", "captured_at"]

    if not rows and OUT.exists() and OUT.stat().st_size > 200:
        print("boj_japan: empty fetch; preserving last-good CSV", file=sys.stderr)
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
    print(f"boj_japan: {len(rows)} items | {summary}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
