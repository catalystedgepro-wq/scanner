#!/usr/bin/env python3
"""build_nasa_news.py — NASA main-site news firehose (distinct from JPL).

Source: https://www.nasa.gov/feed/ (RSS 2.0, WordPress-generated, hourly updates).
Fills the NASA press/mission-news gap distinct from JPL (build_jpl_news.py) and
the numeric NEO/EONET/FIRMS/POWER science endpoints. Drives aerospace exposure:
BA LMT NOC RTX GD LHX HWM SPR TDG HEI (primes + suppliers), commercial-space
RKLB ASTR PL SPCE LUNR BKSY IRDM MAXR (launch + EO + comms), and CSDA-vendor
on-ramps (Satellogic SATL, MDA.TO, Planet PL, BlackSky BKSY).

Taxonomy (priority-ordered, first-match-wins):
  earth_science / human_spaceflight / commercial / science_mission /
  technology / exploration / partnership / award / policy / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://www.nasa.gov/feed/"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "nasa_news.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("human_spaceflight", re.compile(r"\b(ISS|International Space Station|Artemis|crew(?:ed)?|astronaut|EVA|spacewalk|Dragon|Cygnus|Starliner)\b", re.I)),
    ("commercial", re.compile(r"\b(commercial(?: crew| partner| lunar| space)?|CCP|CLPS|CSDA|on[- ]ramp|vendor|SpaceX|Blue Origin|Northrop|Boeing|Sierra Space|Axiom|Intuitive Machines|Firefly|Rocket Lab|Satellogic|MDA Space|Planet|BlackSky|Maxar)\b", re.I)),
    ("science_mission", re.compile(r"\b(JPL|Webb|JWST|Hubble|HST|Mars|Perseverance|Curiosity|Europa|Clipper|Voyager|Cassini|Juno|Parker|Dragonfly|TESS|Swift|Chandra|Nancy Grace Roman|asteroid|comet|exoplanet)\b", re.I)),
    ("earth_science", re.compile(r"\b(Earth[- ]obser|CSDA|remote sensing|satellite imagery|MODIS|Landsat|SAR|synthetic aperture|radiometric|geodetic|PACE|SWOT|GRACE|ICESat|NISAR|climate|wildfire|hurricane|flood|drought|sea level)\b", re.I)),
    ("exploration", re.compile(r"\b(Moon|lunar|Gateway|HLS|SLS|Orion|deep space|Mars mission|Phobos|Demos|interstellar|outer planets)\b", re.I)),
    ("technology", re.compile(r"\b(tech(?:nology)? demo|innovation challenge|SBIR|STTR|CubeSat|laser comm|nuclear (?:thermal|electric)|in[- ]space manufacturing|ISRU|3D print|additive manufacturing|tipping[- ]point)\b", re.I)),
    ("partnership", re.compile(r"\b(memorandum of understanding|MOU|Space Act Agreement|reimbursable|cooperative|collaborat|international partner|bilateral|ESA|JAXA|CSA|ISRO|DLR|CNES|UAE Space)\b", re.I)),
    ("award", re.compile(r"\b(selects|selected|awards?|contract award|task order|delivery order|firm[- ]fixed[- ]price|cost[- ]plus|modification|millions?|billions?)\b", re.I)),
    ("policy", re.compile(r"\b(Administrator|Deputy Administrator|Associate Administrator|Congressional|House|Senate|budget|appropriation|testimony|hearing|Executive Order|strategic plan|Authorization Act)\b", re.I)),
)


def _clean(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<!\[CDATA\[|\]\]>", "", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_pub(raw: str) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw.strip())
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify(title: str, summary: str) -> str:
    hay = f"{title} {summary}"
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(hay):
            return kind
    return "press"


def _fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    rows: list[dict] = []
    for block in re.findall(r"<item>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        filed = _parse_pub(_clean(date_m.group(1))) if date_m else None
        summary = _clean(desc_m.group(1)) if desc_m else ""

        if not title:
            continue
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append(
            {
                "filed_utc": filed,
                "kind": _classify(title, summary),
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
            }
        )
    rows.sort(key=lambda r: r["filed_utc"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[nasa_news] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[nasa_news] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[nasa_news] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    tally = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[nasa_news] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
