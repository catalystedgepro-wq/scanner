#!/usr/bin/env python3
"""build_sec_13f.py — SEC 13F institutional holdings (EDGAR RSS).

13F filings (45 days post-quarter) = institutional portfolio reveals.
Buffett (Berkshire Hathaway 0001067983), Burry (Scion Capital),
Ackman (Pershing Square), Dalio (Bridgewater), Einhorn (Greenlight),
Cohen (Point72), Paulson (Paulson & Co), Tepper (Appaloosa), Simons
(Renaissance) moves = market-narrative anchors.

Source: EDGAR getcurrent type=13F-HR.
Output: sec_13f.csv
Columns: cik, company, form, filed_at, accession, description,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_13f.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["13F-HR", "13F-HR/A", "13F-NT"]

WATCHLIST_CIKS = {
    "0001067983": "Berkshire Hathaway (Buffett)",
    "0001649339": "Scion Asset (Burry)",
    "0001336528": "Pershing Square (Ackman)",
    "0001350694": "Bridgewater (Dalio)",
    "0001079114": "Greenlight Capital (Einhorn)",
    "0001603466": "Point72 (Cohen)",
    "0001035674": "Paulson & Co (Paulson)",
    "0001656456": "Appaloosa (Tepper)",
    "0001037389": "Renaissance Technologies",
    "0001061165": "Lone Pine Capital",
    "0001167483": "Viking Global",
    "0001418814": "Third Point (Loeb)",
    "0000844779": "Soros Fund Mgmt",
    "0001029160": "Citadel Advisors",
    "0001423053": "Millennium Management",
    "0001037372": "Two Sigma Investments",
    "0001350115": "ARK Investment Mgmt",
}


def fetch_form(form: str) -> list[dict]:
    url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        f"&type={urllib.parse.quote(form)}&company=&dateb="
        f"&owner=include&count=100&output=atom"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"13f {form}: {e}")
        return []
    try:
        root = ET.fromstring(txt)
    except Exception:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else ""
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        m = re.search(r"\((\d{10})\)", title)
        cik = m.group(1) if m else ""
        acc = ""
        m3 = re.search(r"accession_number=([\d-]+)", link or "")
        if m3:
            acc = m3.group(1)
        company_name = title.split(" - ")[-1].strip() if " - " in title else title
        watch = WATCHLIST_CIKS.get(cik, "")
        if watch:
            company_name = f"⭐ {watch}"
        out.append({
            "cik": cik,
            "company": company_name[:100],
            "form": form,
            "filed_at": updated,
            "accession": acc,
            "description": summary[:140],
        })
    return out


def main() -> None:
    all_rows: list[dict] = []
    for f in FORMS:
        all_rows.extend(fetch_form(f))
    seen: set[str] = set()
    rows: list[dict] = []
    for r in all_rows:
        k = f"{r['cik']}:{r['accession']}"
        if k in seen:
            continue
        seen.add(k)
        rows.append(r)
    # Sort watchlist first, then chronological
    rows.sort(key=lambda r: (
        0 if r["company"].startswith("⭐") else 1,
        -dt.datetime.strptime(r["filed_at"][:19], "%Y-%m-%dT%H:%M:%S").timestamp()
            if len(r.get("filed_at", "")) >= 19 else 0
    ))
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "cik", "company", "form", "filed_at",
                "accession", "description", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    watchlist_hits = sum(1 for r in rows if r["company"].startswith("⭐"))
    latest = rows[0] if rows else {}
    print(f"sec_13f: {len(rows)} filings | {watchlist_hits} watchlist | latest "
          f"{latest.get('company','?')[:40]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
