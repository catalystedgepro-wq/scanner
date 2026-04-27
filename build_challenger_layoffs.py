#!/usr/bin/env python3
"""build_challenger_layoffs.py — Challenger, Gray & Christmas monthly layoffs.

Challenger Report publishes announced layoffs by sector 1st Thursday of
each month. Leads BLS data by ~30 days. Tech cut announcements hit META,
MSFT, GOOGL, AMZN, CRM proxies; energy cuts → XOM; retail cuts → TGT, M.

Source: Original at challengergray.com is paywalled. Use FRED proxy
(CHALL series if available) OR scrape their monthly press release page.

Output: challenger_layoffs.csv
Columns: month, total_cuts, top_sector, sector_cuts, ytd_total, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "challenger_layoffs.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://www.challengergray.com/blog/category/job-cut-report/"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"challenger: {e}")
        return ""


def main() -> None:
    html = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # Look for patterns like "January 2026: X job cuts" or "March 2026 Job Cut Report"
    monthly_posts = re.findall(
        r"(?:<h\d[^>]*>)?([A-Z][a-z]+\s+20\d{2})[^<]*?Job\s+Cut[^<]*?(?:</h\d>)?"
        r"(?:.{0,800})?(?:([\d,]+)\s+(?:planned\s+)?(?:job\s+)?cuts?)?",
        html[:60000],
        re.I | re.S,
    )
    for mo, cuts in monthly_posts[:12]:
        rows.append({
            "month": mo,
            "total_cuts": (cuts or "").replace(",", ""),
            "top_sector": "",
            "sector_cuts": "",
            "ytd_total": "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "total_cuts", "top_sector",
                "sector_cuts", "ytd_total", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"challenger_layoffs: {len(rows)} months -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
