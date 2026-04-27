#!/usr/bin/env python3
"""build_sec_speeches.py — SEC Chair/Commissioner/staff speeches tape.

Source: sec.gov/news/speeches.rss  (clean RSS 2.0, ~30-item rolling, free, no key)
Distinct from build_sec_press.py (press-release firehose) — this spoke is the
named-speaker tape where SEC Chair (Atkins) + Commissioners (Peirce, Uyeda,
Crenshaw, Lizárraga) + Division Directors (TM, Corp Fin, IM, Enf) telegraph
rulemaking priorities 3-12 months before Reg-S-K/Reg-NMS amendments hit
Federal Register. Speeches move rate-/sector-sensitive names immediately:

  - CAT/options roundtables     → VIRT/IBKR/HOOD/SCHW market-maker economics
  - crypto/digital asset stance → COIN/MSTR/MARA/RIOT (BTC spot ETF, staking)
  - climate disclosure          → XLE/XLU/XLK Reg S-K Item 106/1500 compliance
  - private fund adviser rule   → BX/APO/KKR/ARES/TPG PE/VC industry repricing
  - market-structure (Reg NMS)  → tick-size pilots, order-comp rebate bans
  - enforcement policy          → whistleblower bounty tape, admissions-based
  - testimony                   → SEC appropriations + staffing + crypto bills

Output: sec_speeches_latest.csv
Schema: filed_utc, kind, speaker, title, link, summary

Python stdlib only. Browser UA. Degraded-run guard preserves last-good CSV.
"""

from __future__ import annotations

import csv
import html
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

URL = "https://www.sec.gov/news/speeches.rss"
OUT = Path(__file__).resolve().parent / "sec_speeches_latest.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Priority-ordered: speaker first (chair/commissioner/staff), then topic.
# First-match wins. Topics are set from title; speaker tag overrides to keep
# speaker attribution (e.g., chair_speech on crypto) queryable alongside topic.
SPEAKER_KIND: list[tuple[str, tuple[str, ...]]] = [
    ("chair_speech",        ("chairman", "chair ", "chairperson")),
    ("commissioner_speech", ("commissioner",)),
    ("staff_speech",        ("director", "deputy", "chief accountant",
                             "general counsel", "division", "chief economist")),
]

TOPIC_KIND: list[tuple[str, tuple[str, ...]]] = [
    ("crypto_digital",   ("crypto", "digital asset", "bitcoin", "ether",
                          "tokeniz", "stablecoin", "blockchain", "defi",
                          "spot etf", "staking")),
    ("options_market",   ("options", "option market", "butterfl", "condor",
                          "cat ", "consolidated audit trail")),
    ("market_structure", ("market structure", "reg nms", "nbbo", "tick size",
                          "best execution", "pfof", "payment for order flow",
                          "order competition", "regulation best")),
    ("esg_climate",      ("climate", "esg", "sustainab", "human capital",
                          "diversity", "item 1500")),
    ("private_funds",    ("private fund", "private equity", "hedge fund",
                          "venture capital", "asset manage", "investment adviser",
                          "family office")),
    ("enforcement",      ("enforcement", "whistleblower", "penalt", "admit",
                          "fraud", "insider trading", "manipulat")),
    ("disclosure",       ("disclosure", "10-k", "8-k", "proxy", "reg s-k",
                          "reg sk", "corp fin", "corporation finance",
                          "financial reporting", "accounting")),
    ("international",    ("iosco", "cross-border", "international", "foreign",
                          "equivalen", "fsb ")),
    ("testimony",        ("testimony", "testif", "hearing", "appropriation",
                          "oversight hearing", "before the ")),
    ("mmf_liquidity",    ("money market", "mmf", "liquidity", "swing pricing",
                          "open-end", "mutual fund")),
    ("municipal",        ("municipal", "muni ", "muni bond", "continuing disclosure")),
    ("fixed_income",     ("fixed income", "treasury market", "corporate bond",
                          "off-the-run", "trace")),
    ("spac",             ("spac", "de-spac", "shell company", "special purpose")),
    ("cyber",            ("cyber", "cybersecurity", "rule 106")),
    ("press",            ()),
]


def classify_speaker(speaker: str) -> str:
    low = speaker.lower()
    for kind, needles in SPEAKER_KIND:
        if any(n in low for n in needles):
            return kind
    return ""


def classify_topic(title: str) -> str:
    low = title.lower()
    for kind, needles in TOPIC_KIND:
        if not needles:
            continue
        if any(n in low for n in needles):
            return kind
    return "press"


def clean(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[", "", text)
    text = re.sub(r"]]>", "", text)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def to_iso(pubdate: str) -> str:
    if not pubdate:
        return ""
    try:
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def parse_field(item: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
    return clean(m.group(1)) if m else ""


def fetch() -> str:
    req = urllib.request.Request(URL, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    try:
        body = fetch()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"[sec_speeches] fetch failed: {exc}", file=sys.stderr)
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[sec_speeches] degraded run: preserving last-good CSV "
                  f"({OUT.stat().st_size}B)", file=sys.stderr)
            return 0
        return 1

    rows: list[dict] = []
    for item in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        title = parse_field(item, "title")
        link = parse_field(item, "link")
        speaker = parse_field(item, "description")
        pub = parse_field(item, "pubDate")
        if not title:
            continue
        speaker_kind = classify_speaker(speaker)
        topic_kind = classify_topic(title)
        if speaker_kind and topic_kind == "press":
            kind = speaker_kind
        else:
            kind = topic_kind
        rows.append({
            "filed_utc": to_iso(pub),
            "kind": kind,
            "speaker": speaker,
            "title": title,
            "link": link,
            "summary": f"{speaker}: {title}",
        })

    if not rows:
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[sec_speeches] degraded run: preserving last-good CSV "
                  f"({OUT.stat().st_size}B)", file=sys.stderr)
            return 0
        print("[sec_speeches] no rows and no last-good CSV", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    cols = ["filed_utc", "kind", "speaker", "title", "link", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    kind_str = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1]))
    print(f"[sec_speeches] wrote {len(rows)} rows -> {OUT.name} | "
          f"kinds: {kind_str}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
