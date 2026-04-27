#!/usr/bin/env python3
"""build_esma_eu.py - European Securities and Markets Authority news tape.

Source: ESMA RSS (https://www.esma.europa.eu/rss.xml). 10-item rolling window,
stdlib only, no key.

ESMA is the EU's financial markets regulator — its rulemaking and consultations
drive pan-EU MiFID II / MiFIR / EMIR / MAR / CRA / PRIIPs / SFTR / CSDR
policy. Publications affect:

  - European inter-listed ADRs (ASML, NVO, BUD, UL, SAP, MC, LVMH, AZN)
  - EU-listed banks (BNP, SAN, DBK, ING, UBS)
  - Amsterdam / Paris / Frankfurt / Madrid / Milan cash + derivatives venues
  - Cross-border CFDs, crypto (MiCA), credit ratings (CRA Regulation)

Kind taxonomy (keyword-matched, priority order):
  * warning             — investor warnings, unauthorised firms
  * enforcement         — fines/sanctions/breach decisions
  * rulemaking          — adopted guidelines, final technical standards, ITS/RTS
  * consultation        — call for evidence, consultation paper, invites comment
  * supervision         — common supervisory action, peer review, priorities
  * esas_joint          — joint ESAs report (EBA/EIOPA/ESMA)
  * mar                 — market abuse / insider lists / STORs
  * cra                 — credit rating agencies
  * mifid               — MiFID II / MiFIR / consolidated tape
  * emir                — EMIR / derivatives / CCP / active account
  * mica                — crypto-assets / MiCA / DORA
  * sustainability      — SFDR / ESG / climate disclosure / taxonomy
  * press               — plain press fallback

Output: esma_eu.csv
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
OUT_CSV = ROOT / "esma_eu.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.esma.europa.eu/rss.xml"

KIND_RULES = [
    ("warning", ("investor warning", "unauthorised firm", "clone firm",
                 "beware of", "fraud alert")),
    ("enforcement", ("imposes a fine", "sanction", "breach decision",
                     "penalty", "settlement", "infringement")),
    ("mica", ("mica", "crypto-asset", "crypto asset", "dora",
              "digital operational resilience", "stablecoin")),
    ("cra", ("credit rating", "rating agency", "cra regulation")),
    ("mifid", ("mifid", "mifir", "consolidated tape", "best execution",
               "systematic internaliser")),
    ("emir", ("emir", "central counterpartie", "ccp",
              "active account requirement", "clearing obligation",
              "derivatives reporting", "otc derivatives")),
    ("mar", ("market abuse", "insider list", "stors", "insider dealing",
             "market manipulation")),
    ("sustainability", ("sfdr", "sustainable finance", "esg disclosure",
                        "taxonomy", "climate disclosure",
                        "green bond", "transition plan")),
    ("rulemaking", ("final report", "technical standards", "guidelines on",
                    "opinion on", "implementing technical",
                    "regulatory technical", "rts", "its")),
    ("consultation", ("call for evidence", "consultation paper",
                      "consultation on", "invites stakeholders",
                      "seeks views", "public consultation")),
    ("supervision", ("common supervisory action", "peer review",
                     "supervisory convergence", "supervisory priorities",
                     "strategic supervisory priorities", "work programme")),
    ("esas_joint", ("esas", "joint committee", "esas spring", "esas autumn",
                    "eba eiopa esma", "three esas")),
]


def _classify(title: str, desc: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    return "press"


def _fetch() -> bytes:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _extract_iso_date(desc_html: str) -> str:
    m = re.search(r'datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})', desc_html)
    return m.group(1) if m else ""


def _extract_section(desc_html: str) -> str:
    m = re.search(
        r'field--name-field-news-section[^>]*>\s*'
        r'<div class="field__item">([^<]+)</div>',
        desc_html)
    return (m.group(1).strip() if m else "")[:80]


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        body = _fetch().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"esma_eu: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"esma_eu: keeping prior {OUT_CSV.name}")
        return

    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)

        title_raw = (t.group(1) if t else "").strip()
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title_raw))[:240]

        desc_raw = desc.group(1) if desc else ""
        desc_html = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", desc_raw))
        iso_date = _extract_iso_date(desc_html)
        section = _extract_section(desc_html)

        desc_txt = re.sub(r"<[^>]+>", " ", desc_html)
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:500]

        link_url = (link.group(1) if link else "").strip()[:240]
        kind = _classify(title, desc_txt)

        if not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "section": section,
            "title": title,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"esma_eu: 0 items, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "section", "title", "url", "captured_at"]
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
    tb = " | ".join(f"{r['title'][:38]}:{r['kind']}" for r in top)
    print(f"esma_eu: {len(rows)} items | {kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
