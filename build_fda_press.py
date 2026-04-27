#!/usr/bin/env python3
"""build_fda_press.py — FDA official press release RSS.

FDA press releases cover approvals, denials, recalls, CRL delays,
guidance docs, and enforcement. Signal: direct binary events for
biotech/pharma — always precede or accompany ticker-level 8-K.

Economic readthrough:
- Approval announcement -> bullish pharma sponsor (AZN, PFE, MRK).
- CRL / rejection -> bearish sponsor, bullish competitors.
- Draft guidance -> sector shift (gene therapy, CRISPR basket,
  digital health).
- Recall -> class-wide scrutiny (MDT, BSX, SYK).
- Priority voucher award -> monetizable (~$100M transferable asset).

Source: https://www.fda.gov/about-fda/contact-fda/stay-informed/
  rss-feeds/press-releases/rss.xml
Output: fda_press.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_press.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://www.fda.gov/about-fda/contact-fda/stay-informed/"
       "rss-feeds/press-releases/rss.xml")

ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
PUB_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
LINK_RE = re.compile(r"<link>(.*?)</link>", re.S)
DESC_RE = re.compile(r"<description>(.*?)</description>", re.S)

KIND_MAP = [
    ("approval", re.compile(r"approv|authoriz|cleared|clear", re.I)),
    ("denial", re.compile(r"denied|rejects?|reject|complete response|crl",
                           re.I)),
    ("recall", re.compile(r"recall|withdraw|safety alert", re.I)),
    ("warning", re.compile(r"warning letter|import alert", re.I)),
    ("guidance", re.compile(r"guidance|draft", re.I)),
    ("voucher", re.compile(r"voucher|priority review voucher|prv", re.I)),
    ("user_fee", re.compile(r"pdufa|user fee|prescription drug user", re.I)),
    ("enforcement", re.compile(r"enforcement|penalty|seizure", re.I)),
]


def _classify(title: str, desc: str) -> str:
    blob = f"{title} {desc}"
    for kind, rx in KIND_MAP:
        if rx.search(blob):
            return kind
    return "other"


def _clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _pd(s: str) -> str:
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z",
                "%a, %d %b %Y %H:%M:%S %z"):
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
        print(f"fda_press: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_press: keeping {OUT_CSV.name}")
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
        date = _pd(p.group(1)) if p else ""
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
            print(f"fda_press: no rows, keeping {OUT_CSV.name}")
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
    app = [r for r in rows if r["kind"] == "approval"][:3]
    ap_s = " | ".join(r["title"][:50] for r in app)
    print(f"fda_press: {len(rows)} items | {kb} | apps=[{ap_s}] "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
