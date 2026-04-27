#!/usr/bin/env python3
"""build_wh_actions.py — White House Presidential Actions (RSS).

Executive Orders, Presidential Memoranda, Proclamations, and Permits —
the single highest-velocity policy catalyst feed for US equities.

Recent shocks that moved markets off this feed:
- Tariff actions on China imports → XRT/TGT/WMT/LOW rerate same-day
- Semiconductor export controls → NVDA/AMD/INTC/AMAT/LRCX -5% to -10%
- Immigration EOs → UBER/DASH/H1B-dependent tech labor supply
- Energy pipeline permits → WMB/ET/ENB/OKE/EPD beneficiaries
- Drug pricing EOs → PFE/LLY/MRK/JNJ -2% to -5% on signing
- Federal land mineral leases → oil/gas + lithium CTRA/OKE/LTHM
- Federal contractor rules → defense contracts pipeline (LMT/RTX/GD)

Signals:
- First 10-day avg per EO in new admin: 1.5-3× historical baseline
  (2017, 2021, 2025) = policy-shock cluster.
- Presidential Permits on pipelines = cross-border infra unlock (ENB).
- Proclamations on tariffs = fade Asia-exposed names 1-3 sessions.

Source: whitehouse.gov/presidential-actions/feed/ (RSS, no key).

Output: wh_actions.csv
Columns: pub_date, title, category, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import html
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "wh_actions.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.whitehouse.gov/presidential-actions/feed/"


def fetch() -> bytes:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read()
    except Exception as e:
        print(f"wh_actions: {e}")
        return b""


def parse(xml_bytes: bytes) -> list[dict]:
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"wh_actions parse: {e}")
        return []

    items = []
    for item in root.iter("item"):
        title = html.unescape(item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        # Categories may appear multiple times; capture the specific
        # sub-category (memorandum/proclamation) if present.
        cats = [html.unescape(c.text or "") for c in item.findall("category")]
        cats_clean = [c for c in cats if c and c != "Presidential Actions"]
        category = cats_clean[0] if cats_clean else (
            cats[0] if cats else "")
        pub_iso = pub_raw
        for fmt in ("%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                d = dt.datetime.strptime(pub_raw, fmt)
                pub_iso = d.astimezone(
                    dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                break
            except ValueError:
                continue
        if not title:
            continue
        items.append({
            "pub_date": pub_iso,
            "title": title[:200],
            "category": category[:60],
            "url": link,
        })
    return items


def main() -> None:
    rows = parse(fetch())
    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"wh_actions: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: r["pub_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["pub_date", "title", "category", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        cats: dict[str, int] = {}
        for r in rows:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        top_cats = " | ".join(f"{k}={v}" for k, v in
                              sorted(cats.items(),
                                     key=lambda x: -x[1])[:3])
        latest = rows[0]
        print(f"wh_actions: {len(rows)} items | {top_cats} | latest "
              f"{latest['pub_date'][:10]} {latest['category']}: "
              f"{latest['title'][:70]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
