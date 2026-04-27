#!/usr/bin/env python3
"""build_sec_form_d.py — SEC Form D private placements (EDGAR RSS).

Form D = private-market capital raise disclosure. Flags companies
raising pre-IPO money (small-cap bullish), or distressed public
issuers raising dilutive private placements (bearish for incumbents).
Captures PIPE (Private Investment Public Equity) activity.

Source: EDGAR getcurrent RSS atom, type=D.
Output: sec_form_d.csv
Columns: cik, ticker, company, accession, form, filed_at, description, captured_at
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
OUT_CSV = ROOT / "sec_form_d.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
    "&type=D&company=&dateb=&owner=include&count=200&action=getcurrent&output=atom"
)


def fetch_atom() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"sec_d: {e}")
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
        m2 = re.search(r"CIK=\s*(\d+)", link or "")
        if not cik and m2:
            cik = m2.group(1)
        acc = ""
        m3 = re.search(r"accession_number=([\d-]+)", link or "")
        if m3:
            acc = m3.group(1)
        out.append({
            "cik": cik,
            "ticker": "",
            "company": title.split(" - ")[-1].strip() if " - " in title else title,
            "accession": acc,
            "form": "D",
            "filed_at": updated,
            "description": summary[:140],
            "captured_at": "",
        })
    return out


def main() -> None:
    rows = fetch_atom()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "cik", "ticker", "company", "accession",
                "form", "filed_at", "description", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"sec_form_d: {len(rows)} filings | latest "
          f"{latest.get('filed_at','?')[:10]} {latest.get('company','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
