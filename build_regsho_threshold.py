#!/usr/bin/env python3
"""build_regsho_threshold.py — FINRA Reg SHO daily threshold securities list.

Reg SHO threshold = stocks with persistent fails-to-deliver (5+ consecutive days
with >=10k shares failing and >=0.5% of outstanding). This is the TRUE
squeeze-candidate list — FTDs mean shorts can't find shares to cover.

Output: regsho_threshold.csv
Columns: ticker, exchange, security_name, trade_date, market_category
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "regsho_threshold.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URLS = {
    "NASDAQ": "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{date}.txt",
    "NYSE":   "https://www.nyse.com/api/regulatory/threshold-securities/download?selectedDate={date}",
}


def fetch(url: str, timeout: int = 20) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/plain,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"regsho: {url[:80]}... -> {e}")
        return None


def try_dates(n: int = 5):
    today = dt.date.today()
    for d in range(n):
        dd = today - dt.timedelta(days=d)
        if dd.weekday() > 4:  # skip weekends
            continue
        yield dd


def main():
    rows: list[dict] = []
    for d in try_dates(7):
        ymd = d.strftime("%Y%m%d")
        dash = d.strftime("%Y-%m-%d")
        # NASDAQ .txt format: pipe-delimited, header row
        nasdaq = fetch(URLS["NASDAQ"].format(date=ymd))
        if nasdaq and "Symbol" in nasdaq.split("\n", 1)[0]:
            lines = nasdaq.splitlines()
            headers = [h.strip() for h in lines[0].split("|")]
            try:
                sym_i = headers.index("Symbol")
                name_i = headers.index("Security Name") if "Security Name" in headers else None
                mc_i = headers.index("Market Category") if "Market Category" in headers else None
            except ValueError:
                sym_i = 1
                name_i = mc_i = None
            for ln in lines[1:]:
                if not ln.strip() or ln.startswith("File Creation Date"):
                    continue
                parts = [p.strip() for p in ln.split("|")]
                if len(parts) > sym_i and parts[sym_i]:
                    rows.append({
                        "ticker": parts[sym_i].upper(),
                        "exchange": "NASDAQ",
                        "security_name": parts[name_i] if name_i is not None and name_i < len(parts) else "",
                        "trade_date": dash,
                        "market_category": parts[mc_i] if mc_i is not None and mc_i < len(parts) else "",
                    })
            if rows:
                break
    # Dedupe
    seen = set()
    dedup = []
    for r in rows:
        key = (r["ticker"], r["exchange"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "exchange", "security_name", "trade_date", "market_category"])
        w.writeheader()
        w.writerows(dedup)
    print(f"regsho_threshold: {len(dedup)} tickers -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
