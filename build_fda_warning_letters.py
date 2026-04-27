#!/usr/bin/env python3
"""build_fda_warning_letters.py — Recent FDA warning letters (last 90 days).

FDA warning letters are prime catalysts — a letter to a pharma/biotech's
manufacturing facility can drop the stock 5–30% (historical: EBS, SUPN,
TEVA, EMER, GILD plants). Affects CMOs (CTLT, WST), medical devices (ISRG,
BSX), food/consumer (KO, PEP plants), dietary supplements.

Source: fda.gov/inspections-compliance-enforcement-and-criminal-investigations/
        compliance-actions-and-activities/warning-letters (scrape, free).

Output: fda_warning_letters.csv
Columns: issue_date, company, subject, office, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_warning_letters.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

URL = "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters"


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"fda_wl: {e}")
        return None


def parse(html: str) -> list[dict]:
    rows: list[dict] = []
    # Each warning letter row is a table <tr> with date, company, subject, office, etc.
    tr_rx = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.I)
    cell_rx = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.I)
    link_rx = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.I)
    date_rx = re.compile(r"(\d{2}/\d{2}/\d{4})")
    for tr in tr_rx.findall(html):
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in cell_rx.findall(tr)]
        if len(cells) < 4:
            continue
        # Find date
        issue = ""
        for c in cells:
            dm = date_rx.search(c)
            if dm:
                m, d, y = dm.group(1).split("/")
                issue = f"{y}-{int(m):02d}-{int(d):02d}"
                break
        if not issue:
            continue
        # URL from first anchor
        urlm = link_rx.search(tr)
        href = urlm.group(1) if urlm else ""
        if href.startswith("/"):
            href = "https://www.fda.gov" + href
        rows.append({
            "issue_date": issue,
            "company": cells[1] if len(cells) > 1 else "",
            "subject": (cells[2] if len(cells) > 2 else "")[:150],
            "office": cells[3] if len(cells) > 3 else "",
            "url": href,
        })
    rows.sort(key=lambda r: r["issue_date"], reverse=True)
    # Last 90 days
    cutoff = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    rows = [r for r in rows if r["issue_date"] >= cutoff][:80]
    return rows


def main() -> None:
    html = fetch(URL) or ""
    rows = parse(html)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "issue_date", "company", "subject", "office", "url",
                "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fda_warning_letters: {len(rows)} letters | latest "
          f"{latest.get('issue_date','?')} {latest.get('company','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
