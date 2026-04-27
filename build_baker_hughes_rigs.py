#!/usr/bin/env python3
"""build_baker_hughes_rigs.py — Baker Hughes weekly US + Canada rig count.

Rising oil rigs -> supply rising -> crude selloff path. Falling rigs ->
XLE/XOM/CVX/EOG rally (producers tightening). Count proxies future
production 6-9 months out. Historic Friday 1pm ET print.

Source: https://rigcount.bakerhughes.com/rss.xml (press-release ATOM
feed). Each weekly title has format:
  "Baker Hughes Rig Count: U.S. -2 to 543 Canada -5 to 130"

Prior implementation used FRED IPG211111CN (industrial-production
proxy, not actual rig count) which was useless as a weekly signal.

Output: baker_hughes_rigs.csv
Columns: date, us_rigs, us_change, canada_rigs, canada_change,
         intl_rigs, intl_change, release_title, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "baker_hughes_rigs.csv"
FEED_URL = "https://rigcount.bakerhughes.com/rss.xml"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# "U.S. -2 to 543"  or  "U.S. +5 to 548"
US_RX = re.compile(r"U\.S\.\s*([+\-]?\d+)\s+to\s+([\d,]+)", re.I)
CA_RX = re.compile(r"Canada\s*([+\-]?\d+)\s+to\s+([\d,]+)", re.I)
# "International -54 to 1,058"
INTL_RX = re.compile(r"International\s*([+\-]?\d+)\s+to\s+([\d,]+)", re.I)


def to_int(s: str) -> int | None:
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_pubdate(raw: str) -> str:
    # "Thu, 16 Apr 2026 12:42:53 +0000" -> "2026-04-16"
    try:
        d = dt.datetime.strptime(raw[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        return d.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def fetch_feed() -> list[dict]:
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8", errors="ignore")
    root = ET.fromstring(body)
    rows: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        date = parse_pubdate(pub)
        if not date or "Rig Count" not in title:
            continue
        us_m = US_RX.search(title)
        ca_m = CA_RX.search(title)
        intl_m = INTL_RX.search(title)
        if not (us_m or intl_m):
            continue
        rows.append({
            "date": date,
            "us_rigs": to_int(us_m.group(2)) if us_m else "",
            "us_change": to_int(us_m.group(1)) if us_m else "",
            "canada_rigs": to_int(ca_m.group(2)) if ca_m else "",
            "canada_change": to_int(ca_m.group(1)) if ca_m else "",
            "intl_rigs": to_int(intl_m.group(2)) if intl_m else "",
            "intl_change": to_int(intl_m.group(1)) if intl_m else "",
            "release_title": title,
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def main() -> None:
    try:
        rows = fetch_feed()
    except Exception as e:
        print(f"baker_hughes: fetch failed: {e}")
        rows = []
    # Datacenter IPs (droplet) get 403 from Akamai. Preserve any existing
    # CSV (rsynced from WSL) rather than clobbering it with empty.
    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"baker_hughes: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "us_rigs", "us_change",
                        "canada_rigs", "canada_change",
                        "intl_rigs", "intl_change",
                        "release_title", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"baker_hughes: {len(rows)} releases | latest "
          f"{latest.get('date','?')} US={latest.get('us_rigs','?')} "
          f"({latest.get('us_change','?')}) "
          f"CA={latest.get('canada_rigs','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
