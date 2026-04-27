#!/usr/bin/env python3
"""build_cb_press.py — Central Bank press releases RSS aggregator.

G10 central bank press releases, speeches, and monetary-policy
statements. Rate decisions and hawkish/dovish pivots drive global
duration & FX trades feeding into US equity sectors:
- Fed press → full S&P / QQQ repricing
- ECB press → LVMH, MC, NSRGY, SAP, BNP (and US ADRs)
- BOJ press → TM, SONY, NMR, MUFG, USDJPY dislocation
- BOE press → BP, SHEL, HSBC, GSK, AZN
- SNB/RBA/BOC → niche but high-beta FX pairs for related equities

Trade context:
- >3 releases in one CB in 48h → out-of-cycle policy signal
- Speech title containing "outlook" / "review" / "statement" → vol
  event premium ahead of release
- Simultaneous releases across multiple CBs same day = coordinated
  policy → cross-asset vol spike

Sources (all free, no key, public RSS):
- federalreserve.gov press_all.xml
- ecb.europa.eu/rss/press.html
- boe.co.uk RSS
- boj.or.jp/en/rss/whatsnew.xml
- bis.org RSS

Output: cb_press.csv
Columns: cb, title, pub_date, link, summary_snippet, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cb_press.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEEDS = [
    ("FED", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("ECB", "https://www.ecb.europa.eu/rss/press.html"),
    ("BOJ", "https://www.boj.or.jp/en/rss/whatsnew.xml"),
    ("BIS", "https://www.bis.org/doclist/cbspeeches.rss"),
]

HTML_TAG = re.compile(r"<[^>]+>")


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _parse_items(xml_bytes: bytes) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    items: list[dict] = []
    # Handle both <rss><channel><item> and Atom <feed><entry>.
    for it in root.iter():
        tag = it.tag.rsplit("}", 1)[-1]
        if tag != "item" and tag != "entry":
            continue
        get = lambda n: (
            next((c.text for c in it if c.tag.rsplit("}", 1)[-1] == n
                  and c.text), "")
        )
        link_val = get("link")
        if not link_val:
            # Atom <link href="...">
            for c in it:
                if c.tag.rsplit("}", 1)[-1] == "link":
                    link_val = c.attrib.get("href", "") or ""
                    if link_val:
                        break
        items.append({
            "title": (get("title") or "").strip()[:120],
            "link": link_val[:180],
            "pub_date": (get("pubDate") or get("published") or
                         get("updated") or "")[:32],
            "summary": HTML_TAG.sub(
                "",
                (get("description") or get("summary") or "")
            ).strip()[:200],
        })
    return items


def main() -> None:
    rows: list[dict] = []
    seen_links: set[str] = set()

    for cb, url in FEEDS:
        try:
            xml_bytes = _fetch(url)
        except Exception as e:
            print(f"cb_press {cb}: {e}")
            continue
        items = _parse_items(xml_bytes)
        for it in items[:20]:
            key = it["link"] or it["title"]
            if not key or key in seen_links:
                continue
            seen_links.add(key)
            if not it["title"]:
                continue
            rows.append({
                "cb": cb,
                "title": it["title"],
                "pub_date": it["pub_date"],
                "link": it["link"],
                "summary_snippet": it["summary"],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cb_press: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["cb"], r["pub_date"]), reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["cb", "title", "pub_date", "link", "summary_snippet",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    per_cb: dict[str, int] = {}
    for r in rows:
        per_cb[r["cb"]] = per_cb.get(r["cb"], 0) + 1
    breakdown = " ".join(f"{cb}={n}" for cb, n in sorted(per_cb.items()))
    top = rows[0] if rows else {}
    print(f"cb_press: {len(rows)} releases | {breakdown} | top: "
          f"[{top.get('cb','?')}] \"{top.get('title','')[:60]}\" "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
