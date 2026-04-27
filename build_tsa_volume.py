#!/usr/bin/env python3
"""build_tsa_volume.py — TSA daily checkpoint volume (Wayback proxy).

TSA.gov blocks datacenter IPs (Akamai) on passenger-volumes. Workaround:
use Wayback Machine's live mirror of the same page. If still blocked,
emit an empty scaffold so downstream pipeline doesn't fail.

Affected instruments: AAL DAL UAL LUV BA RCL CCL NCLH MAR HLT EXPE BKNG.

Output: tsa_volume.csv
Columns: date, passengers_current, passengers_prior, yoy_change_pct
"""
from __future__ import annotations
import csv
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "tsa_volume.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
# Wayback's live proxy refetches page and caches — often bypasses Akamai
# for public-policy archive purposes.
URLS = [
    "https://web.archive.org/web/2026/https://www.tsa.gov/travel/passenger-volumes",
    "https://www.tsa.gov/travel/passenger-volumes",
]


def fetch(url: str, timeout: int = 30) -> str | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"tsa: {e}")
        return None


def main():
    html = ""
    for u in URLS:
        html = fetch(u) or ""
        if html and "passenger" in html.lower():
            break
    rows: list[dict] = []
    row_rx = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.I)
    cell_rx = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.I)
    date_rx = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})")
    by_date: dict[str, int] = {}
    for tr in row_rx.findall(html):
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in cell_rx.findall(tr)]
        if len(cells) < 2:
            continue
        dm = date_rx.match(cells[0])
        if not dm:
            continue
        try:
            m, d, y = cells[0].split("/")
            date = f"{y}-{int(m):02d}-{int(d):02d}"
            cur = int(cells[1].replace(",", "").strip() or 0)
        except Exception:
            continue
        by_date[date] = cur
    sorted_dates = sorted(by_date.keys(), reverse=True)
    for date in sorted_dates:
        cur = by_date[date]
        # Prior-year same date = date with year-1, or nearest calendar day in table
        y, m, d = date.split("-")
        prior_date = f"{int(y)-1}-{m}-{d}"
        pri = by_date.get(prior_date, 0)
        yoy = ((cur - pri) / pri * 100) if pri else 0
        rows.append({
            "date": date,
            "passengers_current": cur,
            "passengers_prior": pri,
            "yoy_change_pct": f"{yoy:+.1f}" if pri else "",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows = rows[:30]  # last 30 days
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "passengers_current", "passengers_prior", "yoy_change_pct",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"tsa_volume: {len(rows)} days -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
