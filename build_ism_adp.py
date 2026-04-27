#!/usr/bin/env python3
"""build_ism_adp.py — ISM, ADP employment, Conference Board release schedule.

ISM Manufacturing/Services PMI (1st/3rd business day), ADP (first Wed of
month) and Conference Board Consumer Confidence/LEI are scheduled prints
that move broad market sentiment.

Output: ism_adp.csv
Columns: release, release_date, tag, url
"""
from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ism_adp.csv"


def first_business_day(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    while d.weekday() > 4:
        d += dt.timedelta(days=1)
    return d


def nth_business_day(year: int, month: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    k = 0
    while True:
        if d.weekday() <= 4:
            k += 1
            if k == n:
                return d
        d += dt.timedelta(days=1)


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


def main():
    today = dt.date.today()
    rows: list[dict] = []
    # Cover next 120 days
    for off in range(0, 5):
        year = today.year + ((today.month - 1 + off) // 12)
        month = ((today.month - 1 + off) % 12) + 1
        # ISM Manufacturing — first business day
        rows.append({
            "release": "ISM Manufacturing PMI",
            "release_date": first_business_day(year, month).strftime("%Y-%m-%d"),
            "tag": "ISM_MFG",
            "url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/",
        })
        # ISM Services — 3rd business day
        rows.append({
            "release": "ISM Services PMI",
            "release_date": nth_business_day(year, month, 3).strftime("%Y-%m-%d"),
            "tag": "ISM_SVC",
            "url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/services/",
        })
        # ADP NFP — first Wednesday
        adp = nth_weekday(year, month, 2, 1)  # Wed = 2
        rows.append({
            "release": "ADP Employment Report",
            "release_date": adp.strftime("%Y-%m-%d"),
            "tag": "ADP_NFP",
            "url": "https://adpemploymentreport.com/",
        })
        # Conference Board Consumer Confidence — last Tuesday
        cci = last_weekday(year, month, 1)  # Tuesday
        rows.append({
            "release": "Consumer Confidence (Conference Board)",
            "release_date": cci.strftime("%Y-%m-%d"),
            "tag": "CB_CONFIDENCE",
            "url": "https://www.conference-board.org/topics/consumer-confidence",
        })
        # Conference Board LEI — third Thursday
        lei = nth_weekday(year, month, 3, 3)
        rows.append({
            "release": "Conference Board Leading Economic Index",
            "release_date": lei.strftime("%Y-%m-%d"),
            "tag": "CB_LEI",
            "url": "https://www.conference-board.org/topics/us-leading-indicators",
        })
    rows = [r for r in rows if r["release_date"] >= today.strftime("%Y-%m-%d")]
    rows.sort(key=lambda r: r["release_date"])
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["release", "release_date", "tag", "url"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"ism_adp: {len(rows)} scheduled releases -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
