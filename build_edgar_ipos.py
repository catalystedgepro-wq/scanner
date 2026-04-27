#!/usr/bin/env python3
"""build_edgar_ipos.py — S-1, 424B prospectus, IPO pipeline (EDGAR RSS).

IPO pipeline tracks new issuers entering public market. S-1 filing =
intent to IPO (usually 3-6mo ahead of pricing). 424B4 = pricing
finalized. Flags new names underwriters will pump (GS, MS, JPM hot).

Source: EDGAR getcurrent for S-1, 424B4, F-1.
Output: edgar_ipos.csv
Columns: cik, company, form, filed_at, description, link, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "edgar_ipos.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["S-1", "S-1/A", "424B4", "F-1", "F-1/A", "S-11", "424B2"]


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
        print(f"ipo {form}: {e}")
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
        out.append({
            "cik": cik,
            "company": title.split(" - ")[-1].strip() if " - " in title else title,
            "form": form,
            "filed_at": updated,
            "description": summary[:140],
            "link": link,
        })
    return out


import urllib.parse  # noqa: E402


def main() -> None:
    all_rows: list[dict] = []
    for f in FORMS:
        all_rows.extend(fetch_form(f))
    # dedupe by cik+form
    seen: set[str] = set()
    rows: list[dict] = []
    for r in all_rows:
        k = f"{r['cik']}:{r['form']}:{r['filed_at']}"
        if k in seen:
            continue
        seen.add(k)
        rows.append(r)
    rows.sort(key=lambda r: r.get("filed_at", ""), reverse=True)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "cik", "company", "form", "filed_at",
                "description", "link", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"edgar_ipos: {len(rows)} filings | latest "
          f"{latest.get('form','?')} {latest.get('company','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
