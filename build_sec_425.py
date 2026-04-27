#!/usr/bin/env python3
"""build_sec_425.py — SEC Form 425 real-time merger/acquisition feed.

Form 425 is a prospectus/proxy filing required for business combinations
(mergers, acquisitions, spin-offs). The "getcurrent" EDGAR feed surfaces
live deal-announcement paperwork minutes after filing. This is a
front-run candidate for:
- Deal arbitrage trades (merger-arb spreads)
- Target repricing vs acquirer
- Competing bid speculation
- Busted-deal breaks when terms / material changes are amended

Form 425 adds coverage that the 8-K catalyst sweep misses when the
announcement comes as a straight S-4 / proxy supplement first.

Source: www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=425

Output: sec_425.csv
Columns: filer_cik, filer_name, form, filed_date, url, title,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_425.csv"

UA = "CatalystEdge/1.0 opensource@example.com"
URL = ("https://www.sec.gov/cgi-bin/browse-edgar?"
       "action=getcurrent&type=425&company=&dateb=&owner=include&"
       "count=40&output=atom")

NS = {"a": "http://www.w3.org/2005/Atom"}
CIK_URL_RE = re.compile(r"/data/(\d+)/", re.IGNORECASE)
CIK_TITLE_RE = re.compile(r"\((\d{5,10})\)")
NAME_RE = re.compile(r"-\s*(.+?)\s*\(\d+\)")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"sec_425: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_425: keeping existing {OUT_CSV.name}")
        return

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"sec_425 parse: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_425: keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    for entry in root.findall("a:entry", NS):
        title = (entry.findtext("a:title", default="", namespaces=NS)
                 or "").strip()
        updated = (entry.findtext("a:updated", default="",
                                  namespaces=NS) or "")[:10]
        summary = (entry.findtext("a:summary", default="",
                                  namespaces=NS) or "")
        link_el = entry.find("a:link", NS)
        href = link_el.get("href") if link_el is not None else ""
        cik_match = CIK_TITLE_RE.search(title) or CIK_URL_RE.search(href or "")
        cik = cik_match.group(1).zfill(10) if cik_match else ""
        name_match = NAME_RE.search(title)
        name = name_match.group(1) if name_match else title
        _ = summary  # retained for future; not currently needed
        rows.append({
            "filer_cik": cik,
            "filer_name": name[:96],
            "form": "425",
            "filed_date": updated,
            "url": (href or "")[:200],
            "title": title[:160],
            "captured_at": now,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_425: empty, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed_date"], reverse=True)

    fieldnames = ["filer_cik", "filer_name", "form", "filed_date",
                  "url", "title", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    with_cik = sum(1 for r in rows if r["filer_cik"])
    latest = rows[0]["filed_date"] if rows else "?"
    print(f"sec_425: {len(rows)} merger prospectuses | with_cik="
          f"{with_cik} | latest {latest} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
