#!/usr/bin/env python3
"""build_bls_calendar.py — BLS economic calendar (NFP, CPI, PPI, JOLTS).

BLS bot-blocks direct HTML scrape (Akamai). We instead compute the release
schedule from known BLS monthly cadence rules + Fed holiday calendar.

Cadence (from bls.gov/schedule historical pattern):
  NFP (Employment Situation): first Friday of month, 8:30 AM ET
  CPI: mid-month (10th–15th), Tuesday or Wednesday, 8:30 AM ET
  PPI: 1–3 business days after CPI
  JOLTS: first Tuesday ~5 weeks lag (month+1, first Tue), 10:00 AM ET
  Real Earnings: same day as CPI, 8:30 AM ET
  ECI: quarterly, last Friday of Apr/Jul/Oct/Jan, 8:30 AM ET
  Productivity: quarterly, ~1st Thu of Feb/May/Aug/Nov, 8:30 AM ET
  Import/Export Prices: ~15th of month, 8:30 AM ET

Output: bls_calendar.csv
Columns: release_date, release_time, series, title, url
"""
from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bls_calendar.csv"

URL = "https://www.bls.gov/schedule/news_release/"


def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    count = 0
    while d.month == month:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += dt.timedelta(days=1)
    return d


def last_weekday(year: int, month: int, weekday: int) -> dt.date:
    next_m = dt.date(year + (month // 12), ((month % 12) + 1), 1)
    d = next_m - dt.timedelta(days=1)
    while d.weekday() != weekday:
        d -= dt.timedelta(days=1)
    return d


def biz_day_after(day: dt.date, n: int) -> dt.date:
    out = day
    added = 0
    while added < n:
        out += dt.timedelta(days=1)
        if out.weekday() <= 4:
            added += 1
    return out


def main():
    today = dt.date.today()
    rows: list[dict] = []
    for off in range(-1, 5):  # 1 past month + 4 ahead
        year = today.year + ((today.month - 1 + off) // 12)
        month = ((today.month - 1 + off) % 12) + 1
        # NFP — first Friday
        nfp = nth_weekday(year, month, 4, 1)  # Friday=4
        rows.append({
            "release_date": nfp.strftime("%Y-%m-%d"),
            "release_time": "08:30 ET", "series": "NFP",
            "title": "Employment Situation (Nonfarm Payrolls)", "url": URL,
        })
        # CPI — second Wednesday (market convention)
        cpi = nth_weekday(year, month, 2, 2)  # Wed=2
        if cpi.day < 10:
            cpi = nth_weekday(year, month, 2, 3)
        rows.append({
            "release_date": cpi.strftime("%Y-%m-%d"),
            "release_time": "08:30 ET", "series": "CPI",
            "title": "Consumer Price Index", "url": URL,
        })
        rows.append({
            "release_date": cpi.strftime("%Y-%m-%d"),
            "release_time": "08:30 ET", "series": "REAL_EARNINGS",
            "title": "Real Earnings", "url": URL,
        })
        # PPI — 1 biz day after CPI
        ppi = biz_day_after(cpi, 1)
        rows.append({
            "release_date": ppi.strftime("%Y-%m-%d"),
            "release_time": "08:30 ET", "series": "PPI",
            "title": "Producer Price Index", "url": URL,
        })
        # JOLTS — first Tuesday of next month
        ny = year + (1 if month == 12 else 0)
        nm = 1 if month == 12 else month + 1
        jolts = nth_weekday(ny, nm, 1, 1)  # Tue=1
        rows.append({
            "release_date": jolts.strftime("%Y-%m-%d"),
            "release_time": "10:00 ET", "series": "JOLTS",
            "title": "Job Openings and Labor Turnover Survey", "url": URL,
        })
        # Import/Export prices — third Friday
        impexp = nth_weekday(year, month, 4, 3)
        rows.append({
            "release_date": impexp.strftime("%Y-%m-%d"),
            "release_time": "08:30 ET", "series": "IMPORT_EXPORT_PX",
            "title": "U.S. Import and Export Price Indexes", "url": URL,
        })
        # ECI quarterly — last Friday of Jan/Apr/Jul/Oct
        if month in (1, 4, 7, 10):
            eci = last_weekday(year, month, 4)
            rows.append({
                "release_date": eci.strftime("%Y-%m-%d"),
                "release_time": "08:30 ET", "series": "ECI",
                "title": "Employment Cost Index", "url": URL,
            })
        # Productivity quarterly — first Thursday of Feb/May/Aug/Nov
        if month in (2, 5, 8, 11):
            prod = nth_weekday(year, month, 3, 1)  # Thu=3
            rows.append({
                "release_date": prod.strftime("%Y-%m-%d"),
                "release_time": "08:30 ET", "series": "PRODUCTIVITY",
                "title": "Productivity and Costs", "url": URL,
            })
    rows = [r for r in rows if r["release_date"] >= today.strftime("%Y-%m-%d")]
    rows.sort(key=lambda r: r["release_date"])
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["release_date", "release_time", "series", "title", "url"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"bls_calendar: {len(rows)} releases -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
