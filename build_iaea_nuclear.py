#!/usr/bin/env python3
"""
build_iaea_nuclear.py — IAEA Top News nuclear-agency tape.

Source: https://www.iaea.org/feeds/topnews
        RSS 2.0 with NON-STANDARD pubDate format: "YY-MM-DD  HH:MM" (local
        Vienna time, no timezone). Custom parser needed.

The International Atomic Energy Agency is the UN nuclear watchdog. Drives
uranium miners (CCJ, UUUU, UEC, DNN, NXE, LEU), SMR/AMR vendors (SMR NuScale,
OKLO, NNE Nano Nuclear, BWXT), utilities with nuclear exposure (CEG, VST,
NEE, D, DUK, SO, EXC, AEP, XEL), fuel-cycle (LEU Centrus, Orano, Urenco),
reactor OEMs (BWXT, Westinghouse/BEP, EDF, Rosatom, KEPCO).

Key signal threads:
- Ukraine/Zaporizhzhia updates (grid-attack stress, insurance implications
  for conflict-zone operators, uranium-supply rerouting)
- Safeguards inspections (Iran/NPT/JCPOA revival — rerating uranium supply)
- Reactor safety missions (post-Fukushima stress tests, China fleet growth,
  India Kaiga restart, Czech/Poland new-build pipeline)
- SMR/AMR deployment (licensing wins for SMR/OKLO/NNE + TerraPower/NuScale/
  X-energy partnerships)
- Fuel-cycle (HALEU, LEU Centrus enrichment, Russia dependency unwind)
- Fukushima ALPS treated-water discharges (TEPCO/9501.T + China seafood ban
  impact)

Distinct from build_eia_tie.py (EIA narrative) and build_doe_news.py (DOE
applied-energy press), this is the internationally-binding nuclear authority
with safeguards + verification + liability mandate.

Output: iaea_nuclear.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

URL = "https://www.iaea.org/feeds/topnews"
OUT = pathlib.Path(__file__).resolve().parent / "iaea_nuclear.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200

# Vienna is CET (UTC+1) or CEST (UTC+2). Use CET as conservative default;
# 1h skew is immaterial for a daily tape.
VIENNA_UTC_OFFSET = timedelta(hours=1)

# Priority-ordered: first match wins.
CLASSIFIER = [
    ("ukraine_zaporizhzhia",  re.compile(r"\b(ukraine|zaporizhzhya|zaporizhzhia|znpp|kh?arkiv|chernobyl|rivne|khmelnytsky)\b", re.I)),
    ("safeguards_inspection", re.compile(r"\b(safeguards?|verification|inspection|iran|jcpoa|npt\b|additional protocol|ipndv|dprk|nuclear weapons|nonprolifera|treaty)\b", re.I)),
    ("reactor_safety",        re.compile(r"\b(safety review|safety mission|safety assessment|stress test|osart|iaea review|peer review|reactor safety|safety standards|nuclear safety|radiation safety|iaea mission)\b", re.I)),
    ("transport_security",    re.compile(r"\b(transport of radioactive|safe transport|radioactive material thefts|nuclear security|physical protection|illicit trafficking)\b", re.I)),
    ("smr_amr",               re.compile(r"\b(smr\b|small modular|advanced modular|advanced reactor|amr\b|microreactor|high-temperature gas|htgr|sfr\b|lfr\b)\b", re.I)),
    ("fuel_cycle",            re.compile(r"\b(haleu|enrichment|fuel cycle|spent fuel|reprocess|uranium supply|conversion|uranium mining|uranium resources)\b", re.I)),
    ("fukushima_alps",        re.compile(r"\b(alps treated water|fukushima|tritium|tepco|tohoku)\b", re.I)),
    ("nuclear_medicine",      re.compile(r"\b(cancer|radiotherapy|nuclear medicine|radiopharmaceutical|tc-99|lutetium|radiology|rpct|imaging|global health|health through nuclear)\b", re.I)),
    ("food_safety_isotopes",  re.compile(r"\b(food safety|food irrad|food export|food waste|isotope hydrol|agriculture|crop variety|sterile insect|fao\b|faofeed|livestock)\b", re.I)),
    ("waste_management",      re.compile(r"\b(radioactive waste|spent nuclear fuel disposal|decommission|geological repository|intermediate-level|high-level waste|ll?w\b)\b", re.I)),
    ("emergency_response",    re.compile(r"\b(emergency preparedness|incusn|inex|rantrek|jplatex|joint assistance team|radiological emergency|crisis response)\b", re.I)),
    ("director_general",      re.compile(r"\b(director general|grossi|dg statement|board of governors|general conference)\b", re.I)),
    ("training_cooperation",  re.compile(r"\b(training|fellowship|cooperation|capacity building|technical cooperation|milestones approach|newcomer|embark)\b", re.I)),
    ("research_reactor",      re.compile(r"\b(research reactor|triga|neutron beam|isotope production|medical isotope)\b", re.I)),
    ("climate_nuclear",       re.compile(r"\b(net zero|climate|decarboni|cop\d+|atoms4netzero)\b", re.I)),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml,application/xml,text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def unescape_clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def extract_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)
    return unescape_clean(m.group(1)) if m else ""


def parse_iaea_pubdate(raw: str) -> str:
    """IAEA uses bespoke 'YY-MM-DD  HH:MM' (Vienna local). Parse tolerantly."""
    raw = raw.strip()
    if not raw:
        return ""
    # Channel-level pubDate is RFC2822 ("Fri, 17 Apr 26 14:44:00 +0200").
    # Item-level is "26-04-17  14:44" with embedded newlines/whitespace.
    # Try RFC2822 first.
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    # Bespoke YY-MM-DD  HH:MM.
    m = re.search(r"(\d{2})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", raw)
    if not m:
        return ""
    yy, mm, dd, hh, mi = (int(x) for x in m.groups())
    year = 2000 + yy if yy < 50 else 1900 + yy
    try:
        dt_local = datetime(year, mm, dd, hh, mi, 0, tzinfo=timezone(VIENNA_UTC_OFFSET))
        return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ""


def classify(title: str, summary: str) -> str:
    hay = f"{title}  {summary}"
    for name, pat in CLASSIFIER:
        if pat.search(hay):
            return name
    return "press"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        filed = parse_iaea_pubdate(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary)
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": title[:240],
            "link": link,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"iaea_nuclear: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "kind", "title", "link", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"iaea_nuclear: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"iaea_nuclear: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
