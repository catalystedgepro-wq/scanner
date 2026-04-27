#!/usr/bin/env python3
"""build_army_amc.py — US Army Materiel Command (AMC) news RSS.

Source: army.mil/rss/static/104.xml (RSS 2.0, ~50-item rolling, free, no key).
AMC is the Army's single materiel-readiness provider and runs 9 Major Subordinate
Commands: ASC, CECOM (C4ISR), TACOM (ground vehicles), AMCOM (aviation/missiles),
JMC (ammo), MEDCOM (medical), USASMDC (space/missile defense), USASAC (FMS),
USACE-adjacent. Drives prime exposure for GD (Abrams/Stryker/TACOM), LMT (missiles
via AMCOM), RTX (missile defense), HII/GD (shipyard sustainment), HWM/SPR (avionics),
TXT (helicopters), KTOS (missile targets), LDOS/KBR/VEC/BAH (logistics), AAPL/MSFT/
PLTR (DoD IT), and org-industrial-base depot contractors (Red River, Anniston,
Letterkenny, Corpus Christi, Tobyhanna, Watervliet, Rock Island).

Taxonomy (priority-ordered, first-match-wins):
  sustainment / depot / ammo / ground_vehicle / missile_aviation / contracting /
  manufacturing / foreign_mil / workforce / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://www.army.mil/rss/static/104.xml"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "army_amc.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("depot", re.compile(r"\b(Red River|Anniston|Letterkenny|Corpus Christi|Tobyhanna|Watervliet|Rock Island|Pine Bluff|Sierra Army|Blue Grass|depot|arsenal|organic industrial base|\bOIB\b)\b", re.I)),
    ("ammo", re.compile(r"\b(Joint Munitions Command|\bJMC\b|ammunition|ammo|artillery shell|155mm|propellant|explosive|ordnance|primer|warhead|munition)\b", re.I)),
    ("ground_vehicle", re.compile(r"\b(TACOM|Abrams|Bradley|Stryker|JLTV|AMPV|M1|M2|M113|tank|armor|armored|combat vehicle|ground vehicle|main battle tank|infantry fighting vehicle|MRAP)\b", re.I)),
    ("missile_aviation", re.compile(r"\b(AMCOM|Redstone|PATRIOT|THAAD|Javelin|Stinger|Hellfire|HIMARS|GMLRS|ATACMS|PrSM|missile|helicopter|Apache|Black Hawk|Chinook|UH-60|AH-64|CH-47|Gray Eagle|rotary wing)\b", re.I)),
    ("manufacturing", re.compile(r"\b(advanced manufacturing|additive manufacturing|3D print|DEAAG|Defense Economic Adjustment|industrial base|manufacturing grant|production ramp|line of production|modernization)\b", re.I)),
    ("contracting", re.compile(r"\b(Army Contracting Command|\bACC\b|contract award|award(?:s|ed)?|task order|delivery order|IDIQ|OTA|other transaction|RFP|solicitation|sole[- ]source|modification|indefinite[- ]delivery)\b", re.I)),
    ("foreign_mil", re.compile(r"\b(FMS|Foreign Military Sales|Security Assistance|USASAC|Security Cooperation|NATO|Ukraine|Israel|Taiwan|Korea|Japan|partner nation|allied transfer|arms transfer)\b", re.I)),
    ("sustainment", re.compile(r"\b(sustainment|readiness|supply chain|logistics|agile sustainment|materiel management|fleet management|life[- ]cycle|reset|recapitalization|APS|Army Prepositioned Stock)\b", re.I)),
    ("workforce", re.compile(r"\b(civilian workforce|hiring|apprenticeship|soldier quality of life|barracks|campus|dining|PCS|recruit|Guardian|Civilian Corps|skill training|union|workforce)\b", re.I)),
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
        print(f"[army_amc] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[army_amc] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[army_amc] no items parsed")
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
    print(f"[army_amc] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
