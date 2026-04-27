#!/usr/bin/env python3
"""
build_usda_ams.py — USDA Agricultural Marketing Service (AMS) tape.

Source: https://www.ams.usda.gov/rss.xml (RSS 2.0 via Drupal, dc:creator)

AMS runs the gate between US commodity producers and the market:
federal marketing orders (dairy, citrus, tree nuts), research & promotion
boards (Beef, Pork, Dairy, Watermelon, Mushroom, Honey, Peanut, etc.),
National Organic Program certification + enforcement, PACA license
actions against produce dealers, commodity grading standards, Federal
Milk Marketing Order price announcements, and USDA commodity purchase
solicitations that feed the food-aid programs (NSLP, TEFAP, SNAP).
Every hit is a catalyst for tickers like TSN, ADM, BG, CALM, LW, SBUX,
KDP, DE, AGCO, CTVA, MOS, DANONE, SAPUTO.

Distinct from build_usda_wasde.py (monthly WASDE report) and
build_usda_crop_progress.py (weekly condition survey). Fills the
AMS regulatory-action gap in the USDA spoke stack.

Output: usda_ams.csv — filed_utc, kind, title, link, creator, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

URL = "https://www.ams.usda.gov/rss.xml"
OUT = pathlib.Path(__file__).resolve().parent / "usda_ams.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered kind rules (first-match-wins). Specific before broad.
KIND_RULES = [
    ("paca_action",       re.compile(r"\b(paca|perishable agricultural commodities act|license revoked|license suspended|failure to pay|dishonored|imposes penalties|bars \w+ from|responsibly connected|civil penalty under)\b", re.I)),
    ("organic_cert",      re.compile(r"\b(organic certification|national organic program|nop\b|usda organic|organic standards|organic integrity|certifying agent|strengthening organic)\b", re.I)),
    ("marketing_order",   re.compile(r"\b(marketing order|marketing agreement|federal marketing order|amend.*marketing order|referendum|continuance referendum|termination referendum|marketing order \d+)\b", re.I)),
    ("milk_order",        re.compile(r"\b(federal milk marketing order|fmmo|class (i|ii|iii|iv) milk|dairy price|milk market administrator|order reform|pricing formula)\b", re.I)),
    ("promotion_board",   re.compile(r"\b(promotion board|research and promotion|beef board|pork board|cattlemen.?s beef board|dairy board|cotton board|egg board|soybean board|watermelon board|honey board|peanut board|mushroom council|nominees|nomination)\b", re.I)),
    ("commodity_purchase", re.compile(r"\b(usda announces purchase|commodity purchase|purchase solicitation|vendor award|food purchase|fresh fruit and vegetable|invites offers|request for offers|usda awards|awards contracts? to)\b", re.I)),
    ("cool_labeling",     re.compile(r"\b(country of origin labeling|cool\b|labeling rule|place of origin|truthful|generic certificat)\b", re.I)),
    ("grading_standard",  re.compile(r"\b(grading standard|united states standards for|quality standard|grade certificat|official grading|voluntary inspection)\b", re.I)),
    ("sustainability",    re.compile(r"\b(local agriculture|regional food system|farm to school|specialty crop block grant|local food promotion|regional food business|climate-smart)\b", re.I)),
    ("grant_program",     re.compile(r"\b(grant program|cooperative agreement|funding opportunity|grants available|announces funds|\$\d+[\d,]* in grants|awarded grant|receives grant)\b", re.I)),
    ("rulemaking",        re.compile(r"\b(proposed rule|final rule|interim rule|request for comments|public comment|notice of hearing|advance notice|regulatory action)\b", re.I)),
    ("market_news",       re.compile(r"\b(market news|market report|weekly.*report|monthly.*report|price announcement|retail report|daily summary|livestock price|grain price)\b", re.I)),
    ("livestock",         re.compile(r"\b(livestock|cattle|beef|hog|pork|poultry|egg|sheep|lamb|bison|packers and stockyards)\b", re.I)),
    ("produce",           re.compile(r"\b(tomato|apple|citrus|grape|cherry|almond|pecan|walnut|pistachio|peanut|watermelon|strawberry|blueberry|raspberry|lettuce|onion|potato|mushroom|cranberry)\b", re.I)),
    ("dairy",             re.compile(r"\b(dairy|milk|cheese|butter|whey|yogurt|ice cream|lactose|casein)\b", re.I)),
    ("grain_ofc",         re.compile(r"\b(grain|wheat|corn|soybean|rice|cotton|tobacco|sugar|sorghum|barley|oats|rye)\b", re.I)),
    ("leadership",        re.compile(r"\b(administrator|deputy administrator|new director|secretary vilsack|secretary rollins|names|appoints|senate confirmation)\b", re.I)),
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
    for name, pat in KIND_RULES:
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
        creator = extract_tag(raw, "dc:creator")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary)
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": title[:240],
            "link": link,
            "creator": creator,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"usda_ams: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "kind", "title", "link", "creator", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"usda_ams: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"usda_ams: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
