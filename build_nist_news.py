#!/usr/bin/env python3
"""NIST News spoke.

Pulls the National Institute of Standards and Technology news RSS from
nist.gov — US technical-standards firehose covering quantum, photonics,
cybersecurity (NIST CSF + post-quantum crypto), AI RMF, materials,
forensics, construction safety (NCST), biomedical, manufacturing,
and metrology / reference materials.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "https://www.nist.gov/news-events/news/rss.xml"
OUT = Path(__file__).resolve().parent / "nist_news.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("quantum", ("quantum", "atomic clock", "entangle", "qubit", "gravitational constant", "metrology", "ytterbium", "cesium", "strontium")),
    ("photonics", ("photonic", "laser", "wavelength", "integrated circuit", "chip", "wafer", "silicon", "semiconductor", "optoelectronic")),
    ("cybersecurity", ("cybersecurity", "csf", "post-quantum", "pqc", "encryption", "cryptograph", "nvd", "vulnerability", "aes", "fips")),
    ("ai_standards", ("artificial intelligence", "ai rmf", "ai risk", "machine learning", "generative", "llm", "neural")),
    ("materials", ("material", "composite", "polymer", "nanoparticle", "nano ", "graphene", "alloy", "ceramic")),
    ("forensics", ("forensic", "fingerprint", "dna analysis", "crime lab", "identification", "pattern evidence")),
    ("construction", ("construction safety", "ncst", "structural", "building code", "fire safety", "disaster investigation", "resilience")),
    ("biomedical", ("biomedical", "cell measurement", "genome", "medical device", "clinical measurement", "pharmaceutical measurement")),
    ("manufacturing", ("advanced manufacturing", "additive manufactur", "3d print", "smart manufactur", "industry 4.0")),
    ("measurement", ("reference material", "si unit", "calibration", "standard reference", "measurement science", "precision")),
    ("press", ()),
]


def classify(text: str) -> str:
    low = text.lower()
    for kind, needles in KINDS:
        if not needles:
            continue
        if any(n in low for n in needles):
            return kind
    return "press"


def strip_tags(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(" ".join(s.split())).strip()


def parse_pubdate(raw: str) -> str:
    if not raw:
        return ""
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_items(body: str) -> list[dict]:
    rows: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        def pick(tag: str) -> str:
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return strip_tags(m.group(1)) if m else ""

        title = pick("title")
        link = pick("link")
        desc = pick("description")
        pub = pick("pubDate")
        creator = pick("dc:creator")
        if not title:
            continue
        kind = classify(f"{title} {desc}")
        rows.append(
            {
                "filed_utc": parse_pubdate(pub),
                "kind": kind,
                "creator": creator,
                "title": title[:240],
                "link": link,
                "summary": desc[:400],
            }
        )
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > 200:
        print(f"[nist] degraded fetch — preserving last-good {OUT.name}", file=sys.stderr)
        return
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["filed_utc", "kind", "creator", "title", "link", "summary"])
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    try:
        body = fetch(FEED)
    except Exception as exc:
        print(f"[nist] fetch failed: {exc}", file=sys.stderr)
        return 1
    rows = parse_items(body)
    write_csv(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(f"[nist] {len(rows)} items | kinds {breakdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
