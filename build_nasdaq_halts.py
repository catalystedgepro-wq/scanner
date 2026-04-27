#!/usr/bin/env python3
"""build_nasdaq_halts.py — NASDAQ/FINRA trading halts feed.

NASDAQ publishes the full market-wide trading halt RSS: every halt
code (H10 news pending, LUDP volatility, SOS FINRA probe, T1-T12
operational, M-codes Reg SHO, etc.), with ticker, halt time, and
resume time (when known). Halts are binary catalyst events:

- H10 / T1 "news pending" halt = material news coming out within
  30 min. Post-halt move often 10-40%. Watch resume tape.
- LUDP "volatility halt" = 5-min automatic pause after 10%+ move.
  Continuation or fade setup depending on tape.
- SOS "FINRA probe" halts = regulatory cloud, hit hard (-30-70%
  on resume). Appears in warning signals.
- T12 resumption pending after merger/tender halt = M&A close;
  check recipient ticker gap.

Output (last 50 halts from RSS feed):
  symbol, issue_name, halt_date, halt_time, reason_code, reason,
  market_category, resumption_date, resumption_time, captured_at

Source: www.nasdaqtrader.com/rss.aspx?feed=tradehalts (RSS, no key,
free, live; backs all market-wide halts incl. OTC).

Signal for trading:
- "News Pending" halt = await resume; first 30s of resume tape
  forecasts full move. Position entry during halt window is
  asymmetric.
- Multiple halts same ticker in 1 session = sustained volatility;
  bid VXX/UVXY intraday.
- SOS halt = medium-term fade target; options put skew widens.
- Sector halt cluster (5+ in same GICS sub-industry) = news
  catalyst check; cross-reference news momentum feed.
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nasdaq_halts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"

# Parse namespace for ndaq:* elements.
NS = {"ndaq": "http://www.nasdaqtrader.com/"}

# Reason code glossary for trading context.
REASON_MAP = {
    "T1": "News Pending",
    "T2": "News Released",
    "T5": "Order Imbalance",
    "T6": "Equipment",
    "T8": "Exchange Filing",
    "T12": "Additional Info Requested",
    "H4": "Limit Up/Limit Down",
    "H9": "Non-Compliant",
    "H10": "SEC Trading Suspension",
    "H11": "Regulatory Concerns",
    "LUDP": "Volatility Trading Pause",
    "LUDS": "Volatility Straddle Condition",
    "MWC0": "Market-Wide Circuit Breaker",
    "MWC1": "MWCB Level 1",
    "MWC2": "MWCB Level 2",
    "MWC3": "MWCB Level 3",
    "MWCH": "MWCB Halt",
    "IPO1": "IPO Not Ready",
    "IPOQ": "IPO Quotation Period",
    "SOS": "FINRA Suspension",
    "P1": "Procedural",
    "P2": "Operational",
    "P3": "News Released",
}


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"nasdaq_halts: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasdaq_halts: keeping existing {OUT_CSV.name}")
        return

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"nasdaq_halts: parse error {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasdaq_halts: keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in root.iter("item"):
        def g(tag: str) -> str:
            el = item.find(f"ndaq:{tag}", NS)
            if el is not None and el.text:
                return el.text.strip()
            return ""
        sym = g("IssueSymbol")
        if not sym:
            continue
        code = g("ReasonCode")
        rows.append({
            "symbol": sym,
            "issue_name": g("IssueName")[:80],
            "halt_date": g("HaltDate"),
            "halt_time": g("HaltTime"),
            "reason_code": code,
            "reason": REASON_MAP.get(code, code) or "",
            "market_category": g("MarketCategory")[:20],
            "resumption_date": g("ResumptionDate"),
            "resumption_time": g("ResumptionTradeTime") or g("ResumptionQuoteTime"),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nasdaq_halts: no items, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort by halt_date + halt_time descending.
    def parse_dt(r: dict) -> str:
        return f"{r['halt_date']}T{r['halt_time']}"

    rows.sort(key=parse_dt, reverse=True)
    rows = rows[:50]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["symbol", "issue_name", "halt_date", "halt_time",
                  "reason_code", "reason", "market_category",
                  "resumption_date", "resumption_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Count by reason code for summary.
    from collections import Counter
    rc = Counter(r["reason_code"] for r in rows)
    top_rc = ", ".join(f"{k or '?'}={v}" for k, v in rc.most_common(3))
    pending = sum(1 for r in rows if not r["resumption_time"])
    print(f"nasdaq_halts: {len(rows)} halts ({pending} pending resume) "
          f"| {top_rc} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
