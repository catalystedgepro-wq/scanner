#!/usr/bin/env python3
"""build_fed_speeches.py — Federal Reserve speeches/statements tape.

Fed-speak is the single highest-conviction macro-catalyst input for:
- Front-end rate vol (2Y yields, SOFR futures, TLT)
- Bank net-interest-margin (JPM, WFC, KRE basket)
- Real estate / long-duration (IYR, QQQ multiples)
- USD crosses (DXY, JPY/Treasury curve linkage)

Signal extraction:
- Speaker × keyword hawkish/dovish frequency
- Hawkish terms: persistent, restrictive, elevated, tight, patience, disinflation pace
- Dovish terms: cuts, easing, accommodation, normalize, moderate, softening, transitory
- Distinctive phrases from FOMC voting members (Powell, Williams, Jefferson, etc.)

Source: federalreserve.gov/feeds/speeches.xml (RSS)
Output: fed_speeches.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fed_speeches.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.federalreserve.gov/feeds/speeches.xml"

VOTING_MEMBERS = {
    "powell", "jefferson", "williams", "barr", "bowman", "cook",
    "jefferson", "kugler", "waller", "goolsbee", "collins", "bostic",
    "daly", "musalem", "schmid", "logan", "kashkari", "barkin", "harker",
}
HAWKISH = {
    "restrictive", "persistent", "elevated", "tight", "patience",
    "vigilant", "sticky", "resilient", "higher for longer", "maintain",
    "additional tightening", "monitor carefully", "not in a hurry",
}
DOVISH = {
    "cuts", "easing", "accommodation", "normalize", "moderate",
    "softening", "progress", "cooling", "balanced", "data dependent",
    "closer to target", "confidence", "risks have shifted",
}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"fed_speeches: {url[:80]}: {e}")
        return ""


def _extract(text: str, tag: str) -> str:
    m = re.search(
        rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", text, re.S)
    return (m.group(1) if m else "").strip()


def _speaker_from_title(title: str, link: str) -> str:
    # Title pattern: "Last, Remarks on X"  OR  link slug: /newsevents/speech/waller20260417a.htm
    m = re.match(r"([A-Z][a-z]+),", title)
    if m:
        return m.group(1).lower()
    m = re.search(r"/speech/([a-z]+)\d{8}", link)
    if m:
        return m.group(1).lower()
    return ""


def _classify(title_desc: str) -> tuple[int, int, str]:
    t = title_desc.lower()
    haw = sum(1 for w in HAWKISH if w in t)
    dov = sum(1 for w in DOVISH if w in t)
    if haw > dov:
        tone = "HAWKISH"
    elif dov > haw:
        tone = "DOVISH"
    else:
        tone = "NEUTRAL"
    return haw, dov, tone


def main() -> None:
    xml = _get(FEED)
    if not xml:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fed_speeches: no fetch, keeping {OUT_CSV.name}")
        return
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    if not items:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    rows: list[dict] = []
    for it in items:
        title = _extract(it, "title")
        link = _extract(it, "link")
        desc = _extract(it, "description")
        pub = _extract(it, "pubDate")
        cat = _extract(it, "category")
        speaker = _speaker_from_title(title, link)
        voter = "yes" if speaker in VOTING_MEMBERS else ""
        haw, dov, tone = _classify(f"{title} {desc}")
        rows.append({
            "pub_date": pub,
            "speaker": speaker,
            "is_voter": voter,
            "category": cat,
            "tone": tone,
            "hawk_hits": str(haw),
            "dove_hits": str(dov),
            "title": title[:200],
            "description": desc[:300],
            "link": link,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fed_speeches: empty, keeping {OUT_CSV.name}")
        return

    fieldnames = ["pub_date", "speaker", "is_voter", "category", "tone",
                  "hawk_hits", "dove_hits", "title", "description",
                  "link", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    haw_total = sum(int(r["hawk_hits"]) for r in rows)
    dov_total = sum(int(r["dove_hits"]) for r in rows)
    voter_count = sum(1 for r in rows if r["is_voter"] == "yes")
    tones = {"HAWKISH": 0, "DOVISH": 0, "NEUTRAL": 0}
    for r in rows:
        tones[r["tone"]] = tones.get(r["tone"], 0) + 1
    print(f"fed_speeches: {len(rows)} items | voters={voter_count} "
          f"H/D={haw_total}/{dov_total} "
          f"haw={tones['HAWKISH']} dov={tones['DOVISH']} "
          f"neu={tones['NEUTRAL']} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
