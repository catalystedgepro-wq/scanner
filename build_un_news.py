#!/usr/bin/env python3
"""
build_un_news.py — UN News Global Perspective tape.

Source: https://news.un.org/feed/subscribe/en/news/all/rss.xml
        RSS 2.0 with standard RFC2822 pubDate. Server sends gzip-encoded
        response unconditionally — needs gzip decompression via stdlib gzip.

UN News is the flagship UN press firehose aggregating Secretary-General
statements + peacekeeping (UNIFIL, UNMISS, MONUSCO, UNAMA, UNDOF, UNFICYP)
+ humanitarian ops (OCHA, WFP, UNHCR, UNICEF, UNFPA, UNAIDS) + agency
programs (UNDP, UNEP, UNESCO, UNCTAD, UNODC, UNHCR) + crisis response
(Gaza, Sudan, Ukraine, Haiti, Myanmar, Yemen, Afghanistan, DRC, Syria).

Drives defence primes on peacekeeping mandate expansion (NOC/RTX/LMT/GD/
LHX), humanitarian contractors (LDOS Leidos/BAH Booz Allen), maritime
shipping sanctions-proximate risk (MAERSK/ZIM/MATX/ONEX), refugee-country
currency stress (PKR/AFN/SDG/HTG/YER), climate-policy pipeline (NEE/BEP/
ENPH on UNEP/UNFCCC announcements), food-aid commodity purchases (ADM/BG
on WFP sourcing), and SG-race geopolitical-alignment tape (2027 turnover).

Distinct from build_iaea_nuclear.py (UN nuclear-watchdog, same UN system
but dedicated agency), build_gdacs_disasters.py (UN disaster-alert RSS,
operational alerts not news), build_who_health.py (WHO press RSS, same UN
system but health-specific), build_eu_commission.py (EU executive, not UN).
This is the cross-cutting UN News firehose covering all other UN bodies.

Output: un_news.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import gzip
import html
import io
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

URL = "https://news.un.org/feed/subscribe/en/news/all/rss.xml"
OUT = pathlib.Path(__file__).resolve().parent / "un_news.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered: first match wins. Keep most-specific kinds at top.
CLASSIFIER = [
    ("sg_leadership",      re.compile(r"\b(secretary[- ]general|UN chief|guterres|next UN chief|deputy secretary|general assembly|SG statement|SG remarks|tenth UN secretary)\b", re.I)),
    ("peacekeeping",       re.compile(r"\b(peacekeep|peacekeeper|unifil|unmiss|minusca|monusco|unama|undof|unficyp|minurso|UN patrol|blue helmet|uniqfil|mandate renewal)\b", re.I)),
    ("ukraine_conflict",   re.compile(r"\b(ukraine|zaporizhz|kyiv|kharkiv|donetsk|luhansk|crimea|russian federation attack|ZNPP)\b", re.I)),
    ("gaza_israel",        re.compile(r"\b(gaza|unrwa|west bank|israel|occupied palestinian|hamas|hezbollah|lebanon|UNIFIL|rafah|khan younis|jenin)\b", re.I)),
    ("sudan_conflict",     re.compile(r"\b(sudan|darfur|khartoum|RSF|south sudan|sahel|nuba|el fasher|blue nile|port sudan)\b", re.I)),
    ("haiti_crisis",       re.compile(r"\b(haiti|port-au-prince|MSS mission|kenyan-led|g9|bbq|gang violence.{0,30}haiti)\b", re.I)),
    ("yemen_conflict",     re.compile(r"\b(yemen|houthi|sana|aden|hodeidah|ansar allah|taiz)\b", re.I)),
    ("afghanistan",        re.compile(r"\b(afghan|kabul|taliban|unama|pakistan afghan|afghan women)\b", re.I)),
    ("myanmar_asia",       re.compile(r"\b(myanmar|rohingya|rakhine|aung san|tatmadaw|ASEAN|burma)\b", re.I)),
    ("drc_africa",         re.compile(r"\b(democratic republic of the congo|\bDRC\b|goma|eastern congo|M23|north kivu|south kivu|burundi)\b", re.I)),
    ("syria_mena",         re.compile(r"\b(syria|idlib|aleppo|damascus|homs|HTS|assad|refugee camps in syria)\b", re.I)),
    ("nuclear_disarm",     re.compile(r"\b(nuclear weapon|nuclear arsenal|disarm|non-proliferation|atomic weapons|NPT\b|nuclear test|ban treaty)\b", re.I)),
    ("climate_environ",    re.compile(r"\b(climate|UNFCCC|UNEP|UN environment|COP\d+|methane|greenhouse|carbon|biodiversity|ocean treaty|plastic treaty|IPCC)\b", re.I)),
    ("food_insecurity",    re.compile(r"\b(WFP|world food programme|FAO|food insecurity|famine|IPC\b|food crisis|food aid|hunger hotspot)\b", re.I)),
    ("refugee_migration",  re.compile(r"\b(UNHCR|refugee|displaced person|asylum|migration|IOM\b|internally displaced|resettlement)\b", re.I)),
    ("health_who",         re.compile(r"\b(\bWHO\b|world health organization|outbreak|mpox|polio|ebola|marburg|tedros|vaccination|measles|cholera|pandemic)\b", re.I)),
    ("women_children",     re.compile(r"\b(UN women|UNICEF|UNFPA|children in conflict|child soldiers|gender-based violence|GBV\b|CSW\d*|maternal mortality|girls education|fertility)\b", re.I)),
    ("human_rights",       re.compile(r"\b(OHCHR|human rights|universal periodic review|UN rapporteur|high commissioner for human rights|turk|rights council)\b", re.I)),
    ("economic_dev",       re.compile(r"\b(UNDP|UN development|SDGs?|sustainable development goal|UNCTAD|LDCs|least developed|poverty reduction|ECOSOC)\b", re.I)),
    ("security_council",   re.compile(r"\b(security council|UNSC|veto|resolution \d{3,5}|presidency|chapter vii|arms embargo|sanctions regime)\b", re.I)),
    ("cyber_crime",        re.compile(r"\b(cyber|UNODC|transnational crime|drug traffick|human traffick|arms traffick|cybercrime treaty)\b", re.I)),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml,application/xml,text/xml",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        encoding = r.headers.get("Content-Encoding", "").lower()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def unescape_clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def extract_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)
    return unescape_clean(m.group(1)) if m else ""


def to_iso_utc(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
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
        # UN News has two pubDate instances — channel + item. Grab item's.
        pub_matches = re.findall(r"<pubDate>(.*?)</pubDate>", raw, re.S)
        filed = to_iso_utc(pub_matches[-1] if pub_matches else "")
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
        print(f"un_news: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"un_news: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"un_news: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
