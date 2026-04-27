#!/usr/bin/env python3
"""build_fed_press.py — Federal Reserve Board press releases (all).

Direct-from-source Fed announcements covering:
- Monetary Policy: FOMC statements, discount rate minutes, Powell
  testimony schedule → 10y/TLT/SPY primary drivers.
- Enforcement Actions: cease-and-desist against named banks (JPM, BAC,
  WFC subsidiaries, regional holding cos) → -3% to -15% one-day move
  in named ticker.
- Orders on Banking Applications: bank M&A + holding-company formation
  approvals → deal-close catalyst for announced combinations (KRE
  constituents).
- Supervisory Letters: SR letter changes = stress-test regime shifts
  (CCAR impact on capital returns).

Source: federalreserve.gov/feeds/press_all.xml (RSS, no key, no auth).
Rolling ~90 items. Parsed with stdlib xml.etree, no third-party
dependencies.

Output: fed_press.csv
Columns: pub_date, category, title, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fed_press.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.federalreserve.gov/feeds/press_all.xml"


def fetch() -> bytes:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read()
    except Exception as e:
        print(f"fed_press: {e}")
        return b""


def parse(xml_bytes: bytes) -> list[dict]:
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"fed_press parse: {e}")
        return []
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        category = (item.findtext("category") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        # Normalize pubDate "Thu, 16 Apr 2026 15:00:00 GMT" → ISO
        pub_iso = pub_raw
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z",
                    "%a, %d %b %Y %H:%M:%S GMT"):
            try:
                d = dt.datetime.strptime(pub_raw, fmt)
                pub_iso = d.strftime("%Y-%m-%dT%H:%M:%SZ")
                break
            except ValueError:
                continue
        if not title:
            continue
        items.append({
            "pub_date": pub_iso,
            "category": category,
            "title": title[:180],
            "url": link,
        })
    return items


def main() -> None:
    data = parse(fetch())
    if not data and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"fed_press: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    data.sort(key=lambda r: r["pub_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in data:
        r["captured_at"] = now

    fieldnames = ["pub_date", "category", "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(data)

    if data:
        cats: dict[str, int] = {}
        for r in data:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        cat_str = " | ".join(f"{k}={v}" for k, v in
                             sorted(cats.items(),
                                    key=lambda x: -x[1])[:4])
        latest = data[0]
        print(f"fed_press: {len(data)} releases | {cat_str} | latest "
              f"{latest['pub_date'][:10]} {latest['category']}: "
              f"{latest['title'][:60]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
