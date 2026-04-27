#!/usr/bin/env python3
"""build_nhc_tropical.py — NOAA NHC Atlantic tropical cyclones RSS.

Active Atlantic-basin storms (named tropical storms, hurricanes,
post-tropical systems being tracked). Off-season (Dec–Apr typical)
the feed returns ~2 items which are info/maintenance messages.
In-season (Jun–Nov) each active storm has:
  - Forecast advisory (position, pressure, intensity, 5-day cone)
  - Public advisory (narrative warnings)
  - Discussion (meteorologist outlook)
  - Wind speed probabilities

Signal for trading (insurance-complex bias):
- Cat-3+ US-landfall 5-day cone forming → short ALL/TRV/CB/HIG,
  long GNRC (generators) / HD/LOW (restock) / WY (lumber).
- Cat-4/5 landfall produces 10-15% 2-week drawdown across the
  insurance complex historically.
- Named storm in GoM / basin → long XOM/CVX/SLB (price spike on
  rig evacuation) + COP (offshore exposure).
- Tropical storm within 48h of landfall = short-term cruise-line
  cancellation risk (CCL/RCL/NCLH).

Companion to build_hurricane_radar.py which reads the NHC
CurrentStorms.json (active + both basins). RSS feed is more
granular per-storm advisory stream.

Source: www.nhc.noaa.gov/index-at.xml (Atlantic basin; no key).
Alternate basin: index-ep.xml (East Pacific).

Output: nhc_tropical.csv
Columns: storm_id, title, advisory_type, pub_date, link,
         summary, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nhc_tropical.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL_AT = "https://www.nhc.noaa.gov/index-at.xml"
URL_EP = "https://www.nhc.noaa.gov/index-ep.xml"


def _adv_type(title: str) -> str:
    """Classify RSS title into advisory category."""
    t = title.lower()
    if "forecast advisory" in t:
        return "FORECAST"
    if "public advisory" in t:
        return "PUBLIC"
    if "discussion" in t:
        return "DISCUSSION"
    if "wind speed prob" in t:
        return "WIND_PROB"
    if "outlook" in t:
        return "OUTLOOK"
    if "summary" in t:
        return "SUMMARY"
    return "OTHER"


def _extract_storm_id(title: str, link: str) -> str:
    """Best-effort pull of storm name from advisory title."""
    # Pattern: "Hurricane HELENE Forecast Advisory Number 12"
    m = re.search(
        r"(?:Tropical Storm|Hurricane|Post-Tropical|Tropical Depression|"
        r"Subtropical Storm|Potential Tropical Cyclone) "
        r"([A-Z][A-Z\-]+)",
        title,
    )
    if m:
        return m.group(1)
    return ""


def fetch(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
    except Exception as e:
        print(f"nhc_tropical fetch {url}: {e}")
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        # Flatten HTML-ish description
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:240]
        items.append({
            "title": title, "link": link,
            "pub": pub, "desc": desc,
        })
    return items


def main() -> None:
    rows: list[dict] = []
    for basin_url, basin in ((URL_AT, "AT"), (URL_EP, "EP")):
        items = fetch(basin_url)
        for it in items:
            # Filter: only storm-specific items, not maintenance.
            adv = _adv_type(it["title"])
            storm = _extract_storm_id(it["title"], it["link"])
            if adv == "OTHER" and not storm:
                # Skip routine maintenance / season outlook messages
                # unless they're tagged as explicit outlook.
                if "outlook" not in it["title"].lower():
                    continue
            rows.append({
                "basin": basin,
                "storm_id": storm,
                "title": it["title"][:140],
                "advisory_type": adv,
                "pub_date": it["pub"],
                "link": it["link"],
                "summary": it["desc"],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nhc_tropical: no advisories, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
            return
        # Off-season, write empty-header CSV.

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["basin", "storm_id", "title", "advisory_type",
                  "pub_date", "link", "summary", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    storms = {r["storm_id"] for r in rows if r["storm_id"]}
    print(f"nhc_tropical: {len(rows)} advisories, "
          f"{len(storms)} named systems "
          f"(AT+EP basins) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
