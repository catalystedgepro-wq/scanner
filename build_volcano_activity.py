#!/usr/bin/env python3
"""build_volcano_activity.py - Smithsonian/USGS Weekly Volcanic Activity Report.

Weekly aviation + insurance + commodity tape. Ash-cloud groundings hit
airlines (UAL AAL DAL LUV JBLU ALK), sulfur-dioxide releases move agri
(NTR MOS CF), Indonesian/Philippine/Japanese eruptions hit palm-oil
shippers + semi fabs (TSM), and large-magnitude events hit reinsurers
(RE RNR AXS AIG HIG AFG TRV). No existing volcano_ or smithsonian_ file
in inventory (grep-confirmed).

7-kind priority-ordered classifier on title + description:
- eruption    : New/Renewed Eruption, erupting, explosion, lava, pyroclastic
- alert       : Alert/Aviation Color Code raised (Orange/Red, level 3/4)
- ash_plume   : ash plume, VAAC advisory, gas emissions, SO2
- new_unrest  : New Unrest / New Activity marker
- ongoing     : Ongoing Activity / Continuing Activity / baseline tape
- seismic     : seismicity / earthquake swarm / tremor
- press       : fallback

Title format: "{Volcano} ({Country}) - Report for {date range} - {Status}"
georss:point "{lat} {lon}" captured for GIS sympathy joins.

Source: volcano.si.edu/news/WeeklyVolcanoRSS.xml (RSS 2.0, 20-item
weekly, updated by 2300 UTC every Thursday, free, no key).
Output: volcano_activity.csv
Columns: filed, kind, volcano, country, status, lat, lon, title, url, captured_at
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "volcano_activity.csv"
FEED = "https://volcano.si.edu/news/WeeklyVolcanoRSS.xml"
UA = "CatalystEdge/1.0 (opensource@example.com)"

KIND_RULES: list[tuple[str, list[str]]] = [
    ("eruption",   ["new eruption", "renewed eruption", "erupting",
                    "eruption continued", "explosion", "explosions",
                    "lava flow", "lava fountain", "pyroclastic",
                    "vulcanian", "strombolian", "subplinian", "plinian",
                    "effusive", "dome collapse"]),
    ("alert",      ["aviation color code orange", "aviation color code red",
                    "alert level was raised", "alert level raised",
                    "volcanic alert level was raised",
                    "level 3", "level 4", "orange alert", "red alert"]),
    ("ash_plume",  ["ash plume", "ash emission", "ash-and-gas",
                    "ash cloud", "vaac", "darwin vaac", "tokyo vaac",
                    "wellington vaac", "anchorage vaac", "washington vaac",
                    "gas plume", "so2", "sulfur dioxide", "steam plume",
                    "ashfall"]),
    ("new_unrest", ["new unrest", "new activity/unrest", "new activity"]),
    ("ongoing",    ["ongoing activity", "continuing activity",
                    "continuing unrest", "ongoing unrest"]),
    ("seismic",    ["seismic swarm", "earthquake swarm", "seismicity",
                    "tremor", "low-magnitude seismic", "vt earthquake",
                    "volcano-tectonic", "long-period event"]),
]

STATUS_RE = re.compile(r" - ([^-]+)$")
HEADER_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*-")
POINT_RE = re.compile(r"<georss:point>\s*([-\d.]+)\s+([-\d.]+)\s*</georss:point>")


def classify(title: str, description: str) -> str:
    hay = " " + (title + " " + description).lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _strip_html(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw))


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"volcano_activity fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        desc = re.search(r"<description>(.*?)</description>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        try:
            filed = parsedate_to_datetime(d.group(1).strip()).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
        url = _strip_cdata(l.group(1)).strip()
        description = _strip_html(_strip_cdata(desc.group(1))) if desc else ""

        volcano = country = status = ""
        hdr = HEADER_RE.match(title)
        if hdr:
            volcano = hdr.group(1).strip()
            country = hdr.group(2).strip()
        tail = STATUS_RE.search(title)
        if tail:
            status = tail.group(1).strip()

        lat = lon = ""
        pt = POINT_RE.search(chunk)
        if pt:
            lat = pt.group(1)
            lon = pt.group(2)

        items.append({
            "filed": filed,
            "kind": classify(title, description),
            "volcano": volcano,
            "country": country,
            "status": status,
            "lat": lat,
            "lon": lon,
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"volcano_activity: no rows; preserved {OUT_CSV.name}")
        return

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat()
    fields = ["filed", "kind", "volcano", "country", "status",
              "lat", "lon", "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in items:
            row["captured_at"] = now
            writer.writerow(row)

    tally: dict[str, int] = {}
    for row in items:
        tally[row["kind"]] = tally.get(row["kind"], 0) + 1
    summary = " ".join(f"{k}={v}" for k, v in sorted(
        tally.items(), key=lambda kv: -kv[1]))
    print(f"volcano_activity: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
