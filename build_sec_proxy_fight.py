#!/usr/bin/env python3
"""build_sec_proxy_fight.py — SEC DEFA14A + PRE 14A live proxy feed.

Proxy-fight / contested-election paperwork:
- PRE 14A (preliminary proxy statement) — first filing when a proxy
  vote is being prepared; often the first public signal an activist
  slate or special vote is coming.
- DEFA14A (definitive additional proxy materials) — mid-campaign
  letters, "fight letters", supplemental slides; often hostile vs.
  existing board.

Both are material news for the target's equity:
- Activist stake reveal (starboard, elliott, trian pattern)
- Hostile board challenge / director nominee slate
- Merger vote supplements (amended deal terms)
- Say-on-pay battles that spill into governance headlines

Source: SEC EDGAR getcurrent feed for each type.

Output: sec_proxy_fight.csv
Columns: filer_cik, filer_name, sub_form, filed_date, url, title,
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
OUT_CSV = ROOT / "sec_proxy_fight.csv"

UA = "CatalystEdge/1.0 opensource@example.com"
NS = {"a": "http://www.w3.org/2005/Atom"}
CIK_URL_RE = re.compile(r"/data/(\d+)/", re.IGNORECASE)
CIK_TITLE_RE = re.compile(r"\((\d{5,10})\)")
NAME_RE = re.compile(r"-\s*(.+?)\s*\(\d+\)")

FORMS = [
    ("DEFA14A",
     "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&"
     "type=DEFA14A&company=&dateb=&owner=include&count=60&output=atom"),
    ("PRE 14A",
     "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&"
     "type=PRE+14A&company=&dateb=&owner=include&count=60&output=atom"),
]


def _fetch(url: str) -> ET.Element | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
        return ET.fromstring(body)
    except Exception as e:
        print(f"sec_proxy_fight {url[-40:]}: {e}")
        return None


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    for sub, url in FORMS:
        root = _fetch(url)
        if root is None:
            continue
        for entry in root.findall("a:entry", NS):
            title = (entry.findtext("a:title", default="",
                                    namespaces=NS) or "").strip()
            updated = (entry.findtext("a:updated", default="",
                                      namespaces=NS) or "")[:10]
            link_el = entry.find("a:link", NS)
            href = link_el.get("href") if link_el is not None else ""
            cik_match = (CIK_TITLE_RE.search(title) or
                         CIK_URL_RE.search(href or ""))
            cik = cik_match.group(1).zfill(10) if cik_match else ""
            name_match = NAME_RE.search(title)
            name = name_match.group(1) if name_match else title
            rows.append({
                "filer_cik": cik,
                "filer_name": name[:96],
                "sub_form": sub,
                "filed_date": updated,
                "url": (href or "")[:200],
                "title": title[:160],
                "captured_at": now,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_proxy_fight: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed_date"], reverse=True)

    fieldnames = ["filer_cik", "filer_name", "sub_form", "filed_date",
                  "url", "title", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    per_form: dict[str, int] = {}
    for r in rows:
        per_form[r["sub_form"]] = per_form.get(r["sub_form"], 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(per_form.items()))
    print(f"sec_proxy_fight: {len(rows)} proxy filings | {breakdown} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
