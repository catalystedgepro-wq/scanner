#!/usr/bin/env python3
"""build_eba_banking.py - European Banking Authority daily digest.

EBA is the EU's pan-European bank regulator — the implementation arm
beneath FSB/ESMA that writes the binding technical standards (ITS/RTS)
for the EU bank rulebook (CRR/CRD/BRRD/MREL/AML). Its tape moves every
EU-listed bank (BNP, SAN, DBK, UBS, UCG, ING, BBVA, INGA, ACA, KBC)
and any US bank with EU subsidiary (JPM, BAC, C, GS, MS). No existing
`eba_` or `european_banking_` build_*.py — gap.

The feed is a daily digest where each <item> rolls up 0-5 embedded
press-release links. We emit one row per digest item plus one row per
extracted press-release link, classified independently.

10-kind priority-ordered classifier:
- stress_test   : EU-wide stress test, resilience exercise
- capital       : CRR, CRD, own funds, RWA, capital buffers
- aml           : AML, CFT, sanctions, PEP, money laundering
- resolution    : BRRD, MREL, bail-in, FOLTF, resolution plan
- consumer      : consumer protection, mortgage, payment services
- fintech       : DORA, ICT risk, AI, crypto, tokenization
- reporting     : reporting framework, ITS, RTS, Q&A, taxonomy
- governance    : remuneration, high earners, suitability, fit-and-proper
- supervision   : supervisory, peer review, guidelines, colleges
- press         : fallback

Source: eba.europa.eu/rss.xml (RSS 2.0). Output: eba_banking.csv
Columns: filed, kind, title, url, captured_at
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eba_banking.csv"
FEED = "https://www.eba.europa.eu/rss.xml"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("stress_test", ["stress test", "eu-wide stress", "resilience exercise",
                     "climate stress", "sensitivity analysis"]),
    ("capital",     ["capital requirement", "own funds", "crr", "crd",
                     "risk-weighted", "risk weighted", "rwa",
                     "capital buffer", "basel iii", "basel 3",
                     "leverage ratio", "lcr ", "nsfr"]),
    ("aml",         ["anti-money laundering", "anti money laundering",
                     "aml/cft", " aml ", "cft", "money laundering",
                     "sanctions", " pep ", "amla"]),
    ("resolution",  ["resolution plan", "brrd", "mrel", "bail-in",
                     "bail in", "failing or likely to fail", "foltf",
                     "crisis management", "resolvability"]),
    ("consumer",    ["consumer protection", "mortgage credit",
                     "payment services", "psd2", "psd3",
                     "consumer duty", "credit servicer"]),
    ("fintech",     ["dora", "ict risk", "operational resilience",
                     "crypto-asset", "crypto asset", "mica",
                     "tokenization", "artificial intelligence",
                     "ai act", "digital finance"]),
    ("reporting",   ["reporting framework", "technical package", " its ",
                     " rts ", "q&a", "taxonomy", "xbrl",
                     "implementing technical", "regulatory technical"]),
    ("governance",  ["remuneration", "high earners", "suitability",
                     "fit and proper", "fit-and-proper", "governance",
                     "board member", "key function"]),
    ("supervision", ["supervisory", "peer review", "guidelines",
                     "colleges of supervisors", "joint committee",
                     "opinion on", "recommendation on"]),
]


def classify(blob: str) -> str:
    hay = " " + blob.lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _parse_pub(raw: str) -> str | None:
    try:
        parsed = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


PRESS_LINK_RE = re.compile(
    r'href="(https://www\.eba\.europa\.eu/publications-and-media/press-releases/[^"]+)"[^>]*>([^<]+)</a>',
    re.I,
)


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"eba_banking fetch: {exc}")
        return []

    items: list[dict] = []
    seen_urls: set[str] = set()
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        desc = re.search(r"<description>(.*?)</description>", chunk, re.S)
        if not (t and d and l):
            continue
        digest_title = html.unescape(_strip_cdata(t.group(1)).strip())
        filed = _parse_pub(_strip_cdata(d.group(1)))
        if not filed:
            continue
        digest_url = _strip_cdata(l.group(1)).strip()
        description = ""
        if desc:
            description = html.unescape(_strip_cdata(desc.group(1)))

        if digest_url not in seen_urls:
            items.append({
                "filed": filed,
                "kind": classify(digest_title + " " + description),
                "title": digest_title,
                "url": digest_url,
            })
            seen_urls.add(digest_url)

        for link_match in PRESS_LINK_RE.finditer(description):
            press_url = link_match.group(1).strip()
            press_title = html.unescape(link_match.group(2).strip())
            if press_url in seen_urls or not press_title:
                continue
            items.append({
                "filed": filed,
                "kind": classify(press_title),
                "title": press_title,
                "url": press_url,
            })
            seen_urls.add(press_url)

    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"eba_banking: no rows; preserved {OUT_CSV.name}")
        return

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat()
    fields = ["filed", "kind", "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in items:
            row["captured_at"] = now
            writer.writerow(row)

    tally: dict[str, int] = {}
    for row in items:
        tally[row["kind"]] = tally.get(row["kind"], 0) + 1
    summary = " ".join(f"{k}={v}" for k, v in sorted(
        tally.items(), key=lambda kv: -kv[1]))
    print(f"eba_banking: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
