#!/usr/bin/env python3
"""build_fed_enforcement.py - Federal Reserve Board enforcement action tape.

Source: FRB Press Release RSS enforcement feed
(https://www.federalreserve.gov/feeds/press_enforcement.xml). Rolling window,
stdlib only, no key.

Fed Board enforcement actions cover bank holding companies (BHCs), state member
banks, and their senior officers. Categories:
  - Cease and Desist Orders (C&D) — formal enforcement
  - Written Agreements — informal enforcement with the Fed
  - Civil Money Penalties (CMP)
  - Prohibition orders against bank officers
  - Termination of prior enforcement (RELIEF event)

Target universe: regional/community bank holding companies (WFC, USB, COF, PNC,
KEY, FITB, RF, HBAN, CFG, MTB, CUBI, BOK, CMA) and subject-of-termination tape
that can drive 3-10% same-week relief on large-bank names.

Kind taxonomy (keyword-matched, priority order):
  * termination     — prior enforcement terminated (RELIEF, bullish)
  * cease_desist    — formal C&D order issued (bearish)
  * civil_penalty   — CMP with $-amount
  * written_agreement — informal enforcement
  * prohibition     — individual officer prohibition
  * consent         — consent order
  * press           — fallback

Output: fed_enforcement.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fed_enforcement.csv"
UA = "Mozilla/5.0 CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.federalreserve.gov/feeds/press_enforcement.xml"

KIND_RULES = [
    ("termination", ("termination of enforcement",
                     "terminates enforcement", "terminate enforcement",
                     "termination of cease", "termination of written")),
    ("cease_desist", ("cease and desist order", "cease-and-desist",
                      "issues cease and desist")),
    ("civil_penalty", ("civil money penalty", "civil monetary penalty",
                       "assesses a civil", "assesses civil money",
                       "imposes civil money")),
    ("written_agreement", ("written agreement",)),
    ("prohibition", ("prohibition order", "order of prohibition",
                     "bars from banking", "banning from the banking",
                     "prohibits from participating")),
    ("consent", ("consent order", "consent to")),
]

ENTITY_SUFFIX = (
    r"(?:Bancshares|Bankshares|Bancorp|Bancorporation|Banc|Financial Group|"
    r"Financial Corporation|Financial Corp|Holdings?|Holding Company|Bank|"
    r"Trust Company|Trust|Corp|Corporation|Company|N\.A\.|"
    r"National Association|Inc|Incorporated|LLC|Group)"
)
ENTITY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&\-\.\s]{2,60}?\s+" + ENTITY_SUFFIX + r")\b"
)
BLACKLIST = {
    "federal reserve board", "federal reserve", "the board",
    "the fed", "fomc", "board of governors", "reserve bank",
}


def _classify(title: str, desc: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    return "press"


def _extract_entity(text: str) -> str:
    for m in ENTITY_RE.finditer(text):
        cand = m.group(1).strip()
        if cand.lower() in BLACKLIST:
            continue
        low = cand.lower()
        if any(b in low for b in BLACKLIST):
            continue
        return cand[:120]
    return ""


def _extract_penalty_usd(text: str) -> int:
    pats = [
        (r"\$([0-9][0-9,\.]*)\s*(?:million|mn|M\b)", 1_000_000),
        (r"\$([0-9][0-9,\.]*)\s*(?:billion|bn|B\b)", 1_000_000_000),
        (r"\$([0-9][0-9,\.]*)\s*(?:thousand|K\b)", 1_000),
        (r"\$([0-9][0-9,\.]{3,})", 1),
    ]
    for pat, scale in pats:
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                n = float(m.group(1).replace(",", ""))
                return int(n * scale)
            except ValueError:
                continue
    return 0


def _fetch() -> bytes:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_pubdate(raw: str) -> str:
    s = raw.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s[:31], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        raw = _fetch()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"fed_enforcement: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fed_enforcement: keeping prior {OUT_CSV.name}")
        return

    body = raw.decode("utf-8-sig", "ignore")
    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)

        title_raw = (t.group(1) if t else "").strip()
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title_raw)).strip()[:240]
        iso_date = _parse_pubdate(
            re.sub(r"<!\[CDATA\[|\]\]>", "",
                   (d.group(1) if d else "")).strip())
        desc_raw = desc.group(1) if desc else ""
        desc_clean = re.sub(r"<!\[CDATA\[|\]\]>", "", desc_raw)
        desc_txt = re.sub(r"<[^>]+>", " ", html.unescape(desc_clean))
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:500]
        link_url = re.sub(r"<!\[CDATA\[|\]\]>", "",
                          (link.group(1) if link else "")).strip()[:240]

        kind = _classify(title, desc_txt)
        entity = _extract_entity(title + " " + desc_txt)
        penalty = _extract_penalty_usd(title + " " + desc_txt)

        if not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "entity": entity,
            "penalty_usd": penalty,
            "title": title,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fed_enforcement: 0 items, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "entity", "penalty_usd",
                  "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in
                  sorted(by_kind.items(), key=lambda kv: -kv[1]))
    top = rows[:3]
    tb = " | ".join(f"{(r['entity'] or r['title'][:30])[:40]}:{r['kind']}"
                    for r in top)
    print(f"fed_enforcement: {len(rows)} items | {kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
