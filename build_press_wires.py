#!/usr/bin/env python3
"""build_press_wires.py — Aggregate corporate press-release wires.

Pulls RSS from:
  - PR Newswire — https://www.prnewswire.com/rss/news-releases-list.rss
  - GlobeNewswire — https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire
  - BusinessWire — https://www.businesswire.com/portal/site/home/?ndmViewId=news_view&rss=1
  - Accesswire — https://www.accesswire.com/rss/latest.aspx

Output: press_wires.csv
Columns: source, published, title, link, ticker_guess, tags
"""
from __future__ import annotations
import csv
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "press_wires.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

FEEDS = {
    "PRNewswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
    "GlobeNewswire": "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire",
    # 2026-04-27: original BusinessWire URL 403'd; switched to feed.businesswire.com.
    "BusinessWire": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVtRWA==",
    # 2026-04-27: Accesswire dropped — both old and new public RSS URLs return
    # HTTP 403 (their feed is now API-key gated). Re-enable if a working URL
    # is identified; until then PRN/GNW/BW cover the corporate-news space.
}

# Headline-driven categorisation — moves price often
TAG_PATTERNS = [
    ("FDA_APPROVAL", re.compile(r"\b(FDA\s+(approv|clear|accept)|breakthrough designation)", re.I)),
    ("MERGER", re.compile(r"\b(acquir|merger|to\s+buy|tender\s+offer|going\s+private)\b", re.I)),
    ("EARNINGS_BEAT", re.compile(r"\b(beats?\s+estimates|tops?\s+consensus|record\s+revenue)", re.I)),
    ("EARNINGS_MISS", re.compile(r"\b(miss(es)?\s+estimates|below\s+consensus|shortfall)", re.I)),
    ("GUIDANCE_UP", re.compile(r"\b(raises?\s+(guid|outlook|forecast)|increases?\s+outlook)", re.I)),
    ("GUIDANCE_DOWN", re.compile(r"\b(lowers?\s+(guid|outlook|forecast)|cuts?\s+outlook)", re.I)),
    ("CONTRACT_WIN", re.compile(r"\b(awarded?\s+contract|contract\s+win|signs?\s+agreement\s+with)", re.I)),
    ("DILUTION", re.compile(r"\b(public\s+offering|secondary\s+offering|at-?the-?market|ATM\s+offering)", re.I)),
    ("BUYBACK", re.compile(r"\b(share\s+repurchase|stock\s+buyback|authorizes?\s+repurchase)", re.I)),
    ("DIVIDEND", re.compile(r"\b(declares?\s+dividend|quarterly\s+dividend|special\s+dividend)", re.I)),
    ("GOING_CONCERN", re.compile(r"going\s+concern", re.I)),
    ("BANKRUPTCY", re.compile(r"\b(chapter\s+11|files?\s+for\s+bankruptcy|creditor\s+protection)", re.I)),
    ("PARTNERSHIP", re.compile(r"\b(partnership|strategic\s+alliance|collaborates?\s+with)", re.I)),
    ("SPINOFF", re.compile(r"\b(spin-?off|separation|demerger)\b", re.I)),
    ("CEO_CHANGE", re.compile(r"\b(CEO|chief\s+executive)\s+(resigns?|steps?\s+down|departing)", re.I)),
    ("SHORT_REPORT", re.compile(r"\b(short\s+report|fraud|manipulat|restat)", re.I)),
]

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.I)
LINK_RE = re.compile(r"<link[^>]*>(.*?)</link>", re.DOTALL | re.I)
ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL | re.I)
PUB_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL | re.I)
DESC_RE = re.compile(r"<description[^>]*>(.*?)</description>", re.DOTALL | re.I)
CASHTAG_RE = re.compile(r"(?:NYSE|NASDAQ|AMEX|OTC)[:\s]+([A-Z]{1,5})\b")


def fetch(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"press_wires: {url[:60]}... -> {e}")
        return None


def clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#39;|&apos;", "'", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    return re.sub(r"\s+", " ", s).strip()


def tag_headline(text: str) -> str:
    tags = []
    for name, rx in TAG_PATTERNS:
        if rx.search(text):
            tags.append(name)
    return ";".join(tags)


def parse_feed(source: str, xml: str) -> list[dict]:
    out = []
    for item_xml in ITEM_RE.findall(xml):
        tm = TITLE_RE.search(item_xml)
        lm = LINK_RE.search(item_xml)
        pm = PUB_RE.search(item_xml)
        dm = DESC_RE.search(item_xml)
        title = clean(tm.group(1)) if tm else ""
        link = clean(lm.group(1)) if lm else ""
        pub = clean(pm.group(1)) if pm else ""
        desc = clean(dm.group(1)) if dm else ""
        full = f"{title} {desc}"
        cm = CASHTAG_RE.search(full)
        tic = cm.group(1) if cm else ""
        out.append({
            "source": source,
            "published": pub,
            "title": title[:240],
            "link": link,
            "ticker_guess": tic,
            "tags": tag_headline(full),
        })
    return out


def main():
    rows: list[dict] = []
    for src, url in FEEDS.items():
        xml = fetch(url)
        if not xml:
            continue
        rows.extend(parse_feed(src, xml))
    # Dedupe by link
    seen, dedup = set(), []
    for r in rows:
        if r["link"] in seen:
            continue
        seen.add(r["link"])
        dedup.append(r)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["source", "published", "title", "link", "ticker_guess", "tags"],
        )
        w.writeheader()
        w.writerows(dedup)
    tagged = sum(1 for r in dedup if r["tags"])
    withtic = sum(1 for r in dedup if r["ticker_guess"])
    print(f"press_wires: {len(dedup)} items ({tagged} tagged, {withtic} with cashtag) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
