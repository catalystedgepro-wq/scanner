#!/usr/bin/env python3
"""build_sec_schedules.py — SEC Schedule 13D/G/TO filings live feed.

Schedule filings surface ownership concentration and tender activity:
- SC 13D: active stake ≥5% with intent to influence (activist signal)
- SC 13G: passive stake ≥5% (index/whale flagging, less urgent)
- SC 13D/A: amendment to an active stake
- SC TO-I / SC TO-T: tender offers (issuer or third-party)
- SC 14D9: target board's recommendation to a tender

These drive:
- Short-term squeezes when 13D filed near the borrow squeeze zone
- Deal-arb trades on TO-I / TO-T announcements
- Target-repricing on SC 14D9 (recommend / reject / withdraw)

Source: www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC

Output: sec_schedules.csv
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
OUT_CSV = ROOT / "sec_schedules.csv"

UA = "CatalystEdge/1.0 opensource@example.com"
URL = ("https://www.sec.gov/cgi-bin/browse-edgar?"
       "action=getcurrent&type=SC&company=&dateb=&owner=include&"
       "count=100&output=atom")

NS = {"a": "http://www.w3.org/2005/Atom"}
CIK_URL_RE = re.compile(r"/data/(\d+)/", re.IGNORECASE)
CIK_TITLE_RE = re.compile(r"\((\d{5,10})\)")
NAME_RE = re.compile(r"-\s*(.+?)\s*\(\d+\)")
FORM_PREFIX_RE = re.compile(
    r"^(SCHEDULE\s+13[DG](?:/A)?|SC\s+13[DG](?:/A)?|"
    r"SC\s+TO-[ITC](?:/A)?|SC\s+14D9(?:/A)?|"
    r"SC\s+14F1(?:/A)?|SC\s+13E[3GF](?:/A)?|SCHEDULE\s+14[A-Z](?:/A)?)",
    re.IGNORECASE)


def _subform(title: str) -> str:
    m = FORM_PREFIX_RE.match(title.strip())
    if m:
        raw = m.group(1).upper().replace("SCHEDULE ", "SC ")
        return raw[:14]
    return title.split(" - ", 1)[0][:14].upper()


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"sec_schedules: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_schedules: keeping existing {OUT_CSV.name}")
        return

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"sec_schedules parse: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_schedules: keeping existing {OUT_CSV.name}")
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
        _ = summary
        rows.append({
            "filer_cik": cik,
            "filer_name": name[:96],
            "sub_form": _subform(title),
            "filed_date": updated,
            "url": (href or "")[:200],
            "title": title[:160],
            "captured_at": now,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_schedules: empty, keeping existing {OUT_CSV.name}")
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
    breakdown = " ".join(f"{k}={v}" for k, v in
                         sorted(per_form.items(), key=lambda kv: -kv[1])[:6])
    print(f"sec_schedules: {len(rows)} filings | {breakdown} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
