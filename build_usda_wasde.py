#!/usr/bin/env python3
"""build_usda_wasde.py — USDA WASDE monthly commodity release schedule.

WASDE releases on a published USDA schedule (9th–12th of the month at 12pm
ET) — the live RSS feed usda.gov/oce/commodity/rss/wasde.xml times out in
datacenter IPs. We compute the monthly calendar (WASDE dates are set a year
in advance and published at usda.gov/oce/commodity/wasde/).

Affected instruments: ZC (corn), ZS (soy), ZW (wheat), CT (cotton), LE
(cattle), HE (hogs), plus ETFs MOO, DBA, JJG, SGG, CORN, WEAT, SOYB, COW.

Output: usda_wasde.csv
Columns: release_date, release_time, title, affects, url
"""
from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usda_wasde.csv"

URL = "https://www.usda.gov/oce/commodity/wasde/"

# WASDE monthly target day — 9th–12th of month, typically Tue/Wed/Thu, 12:00 ET.
# USDA historical schedule shows: 9th if weekday, else next biz day; may push
# to 10–12th. We use the first business day from the 9th onward.


def first_biz_from(year: int, month: int, day: int) -> dt.date:
    d = dt.date(year, month, day)
    while d.weekday() > 4:
        d += dt.timedelta(days=1)
    return d


def main():
    today = dt.date.today()
    rows: list[dict] = []
    for off in range(-1, 6):
        year = today.year + ((today.month - 1 + off) // 12)
        month = ((today.month - 1 + off) % 12) + 1
        wasde = first_biz_from(year, month, 9)
        rows.append({
            "release_date": wasde.strftime("%Y-%m-%d"),
            "release_time": "12:00 ET",
            "title": f"WASDE Report (World Agricultural Supply & Demand Estimates) — {wasde.strftime('%b %Y')}",
            "affects": "ZC ZS ZW CT LE HE MOO DBA JJG SGG CORN WEAT SOYB COW",
            "url": URL,
        })
    rows = [r for r in rows if r["release_date"] >= today.strftime("%Y-%m-%d")]
    rows.sort(key=lambda r: r["release_date"])
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["release_date", "release_time", "title", "affects", "url"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"usda_wasde: {len(rows)} releases -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
