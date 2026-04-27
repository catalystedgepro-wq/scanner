#!/usr/bin/env python3
"""build_fca_uk.py - UK Financial Conduct Authority news/enforcement tape.

Source: FCA News RSS (https://www.fca.org.uk/news/rss.xml). Public, no key,
stdlib only. ~40 items rolling across News stories / Press releases / Blogs /
Speeches / Statements categories.

Catalyst angle: UK FCA regulates LSE-listed tickers (HSBA, BARC, LLOY, NWG,
STAN, AV, LGEN, PRU, SDR, PSN) and US names with UK subsidiaries (JPM, C, BAC,
AIG, MS, GS). FCA enforcement (Final Notices, liquidations, s166 skilled-person
reviews) and rulemaking (consumer-duty, short-selling regime, crypto permission
rules) both move UK banks + US-subsidiary tickers.

Kind taxonomy (keyword-matched, priority order):
  * final_notice   — formal disciplinary sanction on an authorised firm
  * fine           — monetary penalty
  * ban            — prohibition order / individual ban
  * liquidation    — firm winding-up / insolvency / administration
  * cease_trade    — stop-carrying-on-regulated-activity / voluntary requirement
  * warning        — public warning list notice / scam alert
  * investigation  — skilled-person / investigation / market abuse probe
  * rulemaking     — policy statement / consultation paper / handbook change
  * consumer_duty  — Consumer Duty outcome / annual board report
  * thematic       — thematic review / multi-firm review
  * press          — plain press release fallback
  * other          — speech / blog / corporate comms

Output: fca_uk.csv
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
OUT_CSV = ROOT / "fca_uk.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.fca.org.uk/news/rss.xml"

KIND_RULES = [
    ("final_notice", ("final notice", "decision notice")),
    ("fine", ("fined ", "fines ", " fine of", "financial penalty",
              "penalty of", "million fine", "pay a fine")),
    ("ban", ("prohibition order", "prohibited from",
             "permanently ban", "banned from")),
    ("liquidation", ("enters liquidation", "in liquidation",
                     "creditors' voluntary liquidation",
                     "special administration",
                     "administration order",
                     "insolvent liquidation",
                     "wound up")),
    ("cease_trade", ("stop carrying out", "stop providing",
                     "voluntary requirement", "varied the permission",
                     "cancelled the authorisation", "cancellation of")),
    ("warning", ("warning list", "scam warning", "unauthorised firm",
                 "alert: ", "consumer warning")),
    ("investigation", ("skilled person", "s166", "under investigation",
                       "market abuse", "investigatory",
                       "opens investigation", "enforcement action")),
    ("rulemaking", ("policy statement", "consultation paper",
                    "final rules", "handbook changes", "rule changes",
                    "finalised", "new rules", "discussion paper")),
    ("consumer_duty", ("consumer duty", "consumer principle",
                       "fair value assessment")),
    ("thematic", ("thematic review", "multi-firm review",
                  "portfolio letter", "dear ceo letter",
                  "dear chair letter")),
]

ENTITY_PAT = re.compile(
    r"((?:[A-Z][A-Za-z0-9&.\-']*\.?,?\s+){0,5}"
    r"[A-Z][A-Za-z0-9&.\-']*,?\s+"
    r"(?:Limited|Ltd\.?|PLC|plc|LLP|Inc\.?|LLC|Corp\.?|Group|"
    r"Holdings|Bank|Securities|Capital|Investments|Insurance|"
    r"Advisers|Advisors|Services|Partners|Management))\b"
)

BLACKLIST = (
    "financial conduct", "prudential regulation", "bank of england",
    "the fca", "the pra", "the prra", "consumer duty",
    "financial ombudsman",
)


def _classify(title: str, desc: str, category: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    cat = (category or "").lower()
    if "press" in cat:
        return "press"
    return "other"


def _extract_entity(title: str, desc: str) -> str:
    for text in (title, desc):
        for m in ENTITY_PAT.finditer(text):
            cand = m.group(1).strip()
            if any(b in cand.lower() for b in BLACKLIST):
                continue
            if len(cand) < 6:
                continue
            return cand[:120]
    return ""


def _extract_amount(desc: str) -> str:
    m = re.search(
        r"£\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand|m|bn|k)?",
        desc, re.IGNORECASE)
    if not m:
        return ""
    num = m.group(1).replace(",", "")
    scale = (m.group(2) or "").lower()
    try:
        v = float(num)
    except ValueError:
        return ""
    if scale in ("billion", "bn"):
        v *= 1_000_000_000
    elif scale in ("million", "m"):
        v *= 1_000_000
    elif scale in ("thousand", "k"):
        v *= 1_000
    return f"{int(v)}"


def _fetch() -> bytes:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_pubdate(raw: str) -> str:
    """FCA uses 'Friday, April 17, 2026 - 13:02' not RFC-822."""
    s = raw.strip()
    for fmt in (
        "%A, %B %d, %Y - %H:%M",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
    ):
        try:
            return dt.datetime.strptime(s[:40], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        body = _fetch().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"fca_uk: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fca_uk: keeping prior {OUT_CSV.name}")
        return

    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)
        cat = re.search(r"<category>(.*?)</category>", it, re.DOTALL)

        title = html.unescape((t.group(1) if t else "").strip())[:200]
        iso_date = _parse_pubdate(d.group(1) if d else "")
        desc_raw = desc.group(1) if desc else ""
        desc_txt = re.sub(r"<[^>]+>", " ", html.unescape(desc_raw))
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:600]
        category = html.unescape((cat.group(1) if cat else "").strip())[:40]
        link_url = (link.group(1) if link else "").strip()[:200]

        kind = _classify(title, desc_txt, category)
        entity = _extract_entity(title, desc_txt)
        penalty_gbp = _extract_amount(desc_txt) if kind == "fine" else ""

        if not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "category": category,
            "entity": entity,
            "penalty_gbp": penalty_gbp,
            "title": title,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fca_uk: 0 items, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "category", "entity", "penalty_gbp",
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
    tagged = sum(1 for r in rows if r["entity"])
    top = [r for r in rows if r["entity"]][:3]
    tb = " | ".join(f"{r['entity'][:28]}:{r['kind']}" for r in top)
    print(f"fca_uk: {len(rows)} items ({tagged} tagged) | "
          f"{kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
