#!/usr/bin/env python3
"""build_cma_uk.py — UK Competition & Markets Authority announcements.

The UK CMA publishes an Atom feed of merger inquiries, subsidy referrals,
market investigations, and regulatory rulings. Cross-border M&A
announcements here lead SEC 8-K follow-up by 1-2 weeks on UK-listed
or dual-listed names (BP, SHEL, HSBC, GSK, AZN, UL).

Economic readthrough:
- Phase 2 merger inquiry opened -> deal-break risk, spread-widening.
- Phase 2 inquiry closed w/ clearance -> spread-tightening, takeout
  confirmation for US ADR holders.
- Subsidy referral -> state-aid headwind for UK-listed or UK-subsidiary
  US firms (auto, pharma, power).
- Market investigation (CMA8-category) -> sector-wide regulatory risk.

Source: UK Gov Atom feed:
https://www.gov.uk/government/organisations/competition-and-markets-authority.atom

Output: cma_uk.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cma_uk.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www.gov.uk/government/organisations/"
       "competition-and-markets-authority.atom")

ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
UPDATED_RE = re.compile(r"<updated>(.*?)</updated>", re.S)
LINK_RE = re.compile(r'<link[^/]*?href="([^"]+)"', re.S)
SUMMARY_RE = re.compile(r"<summary[^>]*>(.*?)</summary>", re.S)

KIND_MAP = [
    ("merger", re.compile(r"merger|acquisition", re.I)),
    ("subsidy", re.compile(r"subsidy|state aid|state-aid", re.I)),
    ("market_study", re.compile(r"market study|market investigation", re.I)),
    ("enforcement", re.compile(r"enforcement|penalty|fine", re.I)),
    ("consultation", re.compile(r"consultation|call for", re.I)),
    ("decision", re.compile(r"decision|ruling|order", re.I)),
]


def _classify(title: str) -> str:
    for k, rx in KIND_MAP:
        if rx.search(title):
            return k
    return "other"


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#39;", "'", s)
    return s.strip()


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"cma_uk: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cma_uk: keeping {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for ent in ENTRY_RE.findall(txt):
        ti = TITLE_RE.search(ent)
        up = UPDATED_RE.search(ent)
        li = LINK_RE.search(ent)
        sm = SUMMARY_RE.search(ent)
        title = _clean(ti.group(1)) if ti else ""
        if not title:
            continue
        updated = _clean(up.group(1))[:10] if up else ""
        link = _clean(li.group(1)) if li else ""
        summary = _clean(sm.group(1))[:200] if sm else ""
        rows.append({
            "date": updated,
            "kind": _classify(title),
            "title": title[:140],
            "summary": summary,
            "url": link,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cma_uk: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["date"], reverse=True)
    fieldnames = ["date", "kind", "title", "summary", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    mergers = [r for r in rows if r["kind"] == "merger"]
    mg_s = " | ".join(r["title"][:50] for r in mergers[:3])
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(),
                                                 key=lambda x: -x[1]))
    print(f"cma_uk: {len(rows)} entries | {kb} | "
          f"mergers: [{mg_s}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
