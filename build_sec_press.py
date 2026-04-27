#!/usr/bin/env python3
"""build_sec_press.py — SEC press releases RSS.

The SEC publishes all official announcements via press release RSS.
Signal: enforcement settlements, rulemaking, exemptive orders, and
commissioner speeches move the regulatory landscape for any ticker
under investigation — and for entire categories (crypto, PE funds,
family offices, SPACs).

Economic readthrough:
- Enforcement settlement -> binary risk removed for accused filer.
- Proposed rule change -> long-tail sector impact (audit trail, PFOF,
  best-ex, Rule 10b5-1, T+1 settlement).
- Exemptive order -> regulatory path unlocked (cross-margining,
  Rule 144 amendment, BDC rule).
- Staff guidance / no-action -> de facto safe harbor for class of
  transactions.

Source: https://www.sec.gov/news/pressreleases.rss

Output: sec_press.csv — last 25 press items (typical RSS window).
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_press.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.sec.gov/news/pressreleases.rss"

ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
PUB_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
LINK_RE = re.compile(r"<link>(.*?)</link>", re.S)
DESC_RE = re.compile(r"<description>(.*?)</description>", re.S)

KIND_MAP = [
    ("enforcement", re.compile(r"charge|fraud|settlement|penalty|"
                                r"manipul|scheme|insider trading|"
                                r"cease.and.desist|litigat", re.I)),
    ("rulemaking", re.compile(r"proposed rule|final rule|"
                               r"rule change|adopts rule|amend", re.I)),
    ("exemptive", re.compile(r"exempt|no.action|waiv", re.I)),
    ("guidance", re.compile(r"guidance|staff bulletin|"
                             r"concept release|interpret", re.I)),
    ("personnel", re.compile(r"appoint|named|director|counsel|"
                              r"chief|nomin|chairman", re.I)),
    ("advisory", re.compile(r"advisory committee|public comment|"
                             r"roundtable", re.I)),
]


def _classify(title: str, desc: str) -> str:
    blob = f"{title} {desc}"
    for kind, rx in KIND_MAP:
        if rx.search(blob):
            return kind
    return "other"


def _clean(s: str) -> str:
    s = s or ""
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _parse_date(s: str) -> str:
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{1,2} \w+ \d{4})", s)
    if m:
        try:
            return dt.datetime.strptime(m.group(1),
                                         "%d %b %Y").date().isoformat()
        except ValueError:
            pass
    return s[:10]


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"sec_press: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_press: keeping {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for it in ITEM_RE.findall(txt):
        t = TITLE_RE.search(it)
        p = PUB_RE.search(it)
        l = LINK_RE.search(it)
        d = DESC_RE.search(it)
        title = _clean(t.group(1)) if t else ""
        if not title:
            continue
        desc = _clean(d.group(1))[:200] if d else ""
        date = _parse_date(p.group(1)) if p else ""
        link = _clean(l.group(1)) if l else ""
        rows.append({
            "date": date,
            "kind": _classify(title, desc),
            "title": title[:180],
            "summary": desc,
            "url": link,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_press: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["date"], reverse=True)
    fieldnames = ["date", "kind", "title", "summary", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(),
                                                 key=lambda x: -x[1]))
    enf = [r for r in rows if r["kind"] == "enforcement"][:3]
    es = " | ".join(r["title"][:50] for r in enf)
    print(f"sec_press: {len(rows)} items | {kb} | enf=[{es}] "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
