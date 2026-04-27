#!/usr/bin/env python3
"""build_space_force.py — US Space Force (USSF) news RSS.

Source: spaceforce.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=1060&max=10
(DotNetNuke-generated RSS 2.0, 10-item rolling, free, no key). Distinct from
build_dod_contracts.py (usaspending.gov contract awards, numeric), build_space_launches.py
(launch-tracker), build_nasa_news.py (civil NASA), build_jpl_news.py (JPL). Space Force
is the national-security-space service — covers NSSL launch contracts, SDA tranches,
SSC acquisition, Missile Warning/Next-Gen OPIR, GPS IIIF, guardian recruiting. Drives
RKLB ASTR LUNR KTOS SAIC LDOS PLTR MAXR + primes LMT NOC BA RTX GD LHX HWM.

Taxonomy (priority-ordered, first-match-wins):
  launch / acquisition / intel_satellite / gps_nav / cyber_ai / guardian /
  ops_readiness / international / policy / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://www.spaceforce.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=1060&max=10"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "space_force.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("launch", re.compile(r"\b(launch|NSSL|National Security Space Launch|Vulcan|Falcon|Starship|Atlas V|Delta IV|launch services|range|Cape Canaveral|Vandenberg|payload fairing|upper stage)\b", re.I)),
    ("acquisition", re.compile(r"\b(acquisition|SDA|Space Development Agency|SSC|Space Systems Command|SWAC|contract|award|IDIQ|OTA|task order|delivery order|solicitation|program office|Maj\. Gen\.)\b", re.I)),
    ("intel_satellite", re.compile(r"\b(SBIRS|Next Gen OPIR|FORGE|DMSP|missile warning|missile track|OPIR|SILENTBARKER|GSSAP|SDA tranche|surveillance|tactical ISR|TacSRT|space domain awareness|SDA mission)\b", re.I)),
    ("gps_nav", re.compile(r"\b(GPS|GPS III|GPS IIIF|M[- ]code|NTS[- ]3|navigation|PNT|position[, ]? navigation|satellite navigation|GNSS)\b", re.I)),
    ("cyber_ai", re.compile(r"\b(cyber|artificial intelligence|\bAI\b|software factory|DevSecOps|eJARVIS|Impact Level|IL[1-6]|ATO|Authority to Operate|Kessel Run|Space CAMP|zero trust|data mesh)\b", re.I)),
    ("guardian", re.compile(r"\b(Guardian|recruit|enlist|workforce|personnel|Chief of Space Operations|\bCSO\b|promotion|retirement|medal|award ceremony|change of command|commissioning)\b", re.I)),
    ("ops_readiness", re.compile(r"\b(STARCOM|Space Flag|JFSCC|CENTCOM|SPACECOM|training|exercise|readiness|operational test|wargame|table[- ]top|joint operations|combatant command)\b", re.I)),
    ("international", re.compile(r"\b(allied|partnership|NATO|Five Eyes|AUKUS|Japan|Korea|Australia|UK|Canada|France|Germany|Italy|ESA|international space|bilateral|coalition)\b", re.I)),
    ("policy", re.compile(r"\b(budget|appropriation|authorization|NDAA|testimony|hearing|Commander's Call|strategic plan|posture|Secretary of the Air Force|SecAF|Congressional|Armed Services)\b", re.I)),
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
        print(f"[space_force] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[space_force] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[space_force] no items parsed")
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
    print(f"[space_force] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
