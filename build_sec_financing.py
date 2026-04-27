#!/usr/bin/env python3
"""build_sec_financing.py — SEC capital-raise / dilution tape.

6 full-text queries on 8-K filings covering capital-structure events:
- ATM offering / at-the-market offering — slow-drip dilution; historical
  Tsiliyannis-Yao 2022 study shows -2-4% day-one, -8-15% over 60 days.
- PIPE financing — private-investment-in-public-equity; warrant-attached
  dilution, classic squeeze-unwind catalyst.
- Private placement — institutional raise, usually at a discount.
- Convertible notes — debt with equity kicker; hedge-fund arb desks
  gamma-short underlying.
- Rights offering — shareholder-pro-rata; dilutive when discounted.
- Accelerated share repurchase — big-cap buyback variant, bullish
  (signals mgmt sees undervaluation, forced buying via bank).

Economic readthrough:
- Dilution bears (ATM/PIPE/private placement/convertible) = supply
  overhang, often triggered at retail enthusiasm peaks.
- Buyback bulls (accelerated repurchase) = mgmt-conviction bid + bank
  forward-accelerated floor.
- Best-alpha sub-universe: biotech + small-cap tech where 50%+ of
  market cap can be added in one PIPE.

Source: efts.sec.gov/LATEST/search-index (quote() pattern)
Output: sec_financing.csv

Lookback: 30 days (capital actions are time-sensitive).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_financing.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "atm_offering": '"at-the-market offering"',
    "pipe_financing": '"PIPE financing"',
    "private_placement": '"private placement"',
    "convertible_notes": '"convertible notes"',
    "rights_offering": '"rights offering"',
    "accel_buyback": '"accelerated share repurchase"',
}

# Per-query volume caps: bearish-dilution kinds publish huge tape; stay
# focused on the freshest 150 each to keep CSV under 5 MB.
LIMITS = {
    "atm_offering": 150,
    "pipe_financing": 120,
    "private_placement": 250,
    "convertible_notes": 200,
    "rights_offering": 80,
    "accel_buyback": 50,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=30)).isoformat()
    d_to = today.isoformat()
    qq = urllib.parse.quote(query)
    forms = urllib.parse.quote("8-K")
    url = (f"https://efts.sec.gov/LATEST/search-index?q={qq}"
           f"&dateRange=custom&startdt={d_from}&enddt={d_to}"
           f"&forms={forms}&from=0&size={min(limit, 100)}")
    out: list[dict] = []
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"sec_financing: {kind} fetch failed: {e}")
        return out
    for h in d.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        names_list = src.get("display_names") or []
        names_str = " ".join(names_list)
        m = TICKER_RE.search(names_str)
        ticker = m.group(1) if m else ""
        out.append({
            "kind": kind,
            "ticker": ticker,
            "name": (names_list[0] if names_list else "")[:80],
            "form": src.get("form", ""),
            "filed": src.get("file_date", ""),
            "period": src.get("period_ending", ""),
            "accession": h.get("_id", ""),
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    counts: dict[str, int] = {}

    for kind, query in QUERIES.items():
        limit = LIMITS.get(kind, 100)
        batch = _fetch(kind, query, limit)
        counts[kind] = len(batch)
        rows.extend(batch)
        time.sleep(0.4)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_financing: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["filed"], r["kind"]), reverse=True)

    fieldnames = ["kind", "ticker", "name", "form", "filed", "period",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # 7-day tickers
    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    top_tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:20]]
    cb = " ".join(f"{k}={v}" for k, v in counts.items())
    print(f"sec_financing: {len(rows)} rows | {cb} | "
          f"last7d={len(recent)} [{' '.join(top_tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
