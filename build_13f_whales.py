#!/usr/bin/env python3
"""build_13f_whales.py — EDGAR 13F institutional holdings (quarterly).

13F-HR filings (due 45d after quarter-end) show the holdings of every
institution with >$100M under management. Tracking changes = following
the whales (Berkshire, Soros, Scion Capital, etc.).

Source: EDGAR RSS getcurrent for 13F-HR + selected manager CIKs.
Output: form_13f_latest.csv
Columns: manager_cik, manager_name, filed_date, period, filing_url
"""
from __future__ import annotations
import csv
import re
import urllib.request
from pathlib import Path
import os

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "form_13f_latest.csv"

UA = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 (opensource@example.com)")

# Public feed of most-recent 13F filings
FEED = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
    "&type=13F-HR&company=&dateb=&owner=include&count=100&output=atom"
)

# High-signal managers worth always watching by CIK.
WATCHED_MANAGERS = {
    "0001067983": "Berkshire Hathaway",
    "0001603339": "Scion Capital (Burry)",
    "0001167483": "Renaissance Technologies",
    "0001350694": "Bridgewater Associates",
    "0001350309": "Soros Fund Management",
    "0000895421": "Citadel Advisors",
    "0001336528": "Point72",
    "0001037389": "Appaloosa",
    "0001048580": "Duquesne",
    "0001061165": "Pershing Square",
    "0001061768": "Greenlight Capital",
    "0001423053": "Baupost Group",
    "0001079114": "Third Point",
    "0001061768": "Greenlight",
    "0001166559": "Icahn Capital",
    "0001336528": "Point72",
    "0001631335": "Millennium Management",
    "0001040273": "Tiger Global",
    "0001103804": "Viking Global",
    "0001535472": "Coatue",
    "0001037389": "Appaloosa",
}

ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
LINK_RE = re.compile(r'<link[^>]+href="([^"]+)"')
UPDATED_RE = re.compile(r"<updated>(.*?)</updated>", re.DOTALL)


def fetch(url: str, timeout: int = 20) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"13f: {e}")
        return None


def main():
    body = fetch(FEED)
    rows = []
    if not body:
        with OUT_CSV.open("w", newline="") as f:
            csv.DictWriter(
                f, fieldnames=["manager_cik", "manager_name", "filed_date", "period", "filing_url", "watched"]
            ).writeheader()
        print("form_13f: feed empty")
        return
    for entry in ENTRY_RE.findall(body):
        t = TITLE_RE.search(entry)
        l = LINK_RE.search(entry)
        u = UPDATED_RE.search(entry)
        if not (t and l):
            continue
        title = t.group(1).strip()
        link = l.group(1).strip()
        updated = (u.group(1).strip()[:10] if u else "")
        # Title: "13F-HR - Firm Name (0001234567) (Filer)"
        m = re.match(r"^13F-HR\s*-\s*(.*?)\s*\((\d{10})\)", title)
        if not m:
            continue
        name = m.group(1).strip()
        cik = m.group(2)
        period = ""
        prm = re.search(r"period of report[^0-9]*(\d{4}-\d{2}-\d{2})", entry, re.I)
        if prm:
            period = prm.group(1)
        rows.append({
            "manager_cik": cik,
            "manager_name": name[:120],
            "filed_date": updated,
            "period": period,
            "filing_url": link,
            "watched": "1" if cik in WATCHED_MANAGERS else "",
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["manager_cik", "manager_name", "filed_date", "period", "filing_url", "watched"],
        )
        w.writeheader()
        w.writerows(rows)
    watched = sum(1 for r in rows if r["watched"])
    print(f"form_13f_latest: {len(rows)} filings ({watched} watched) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
