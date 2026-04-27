#!/usr/bin/env python3
"""build_doj_news.py - US Department of Justice news tape (corporate-filtered).

Source: DOJ News RSS (https://www.justice.gov/news/rss). 25-item rolling window,
stdlib only, no key.

DOJ press releases are the source-of-truth for US criminal enforcement.
Most items are street-crime (skipped); this spoke tags only corporate-impact
kinds relevant to equity catalysts.

Kind taxonomy (keyword-matched, priority order):
  * antitrust          — Sherman Act / Clayton Act / merger challenge / monopolization
  * fcpa               — Foreign Corrupt Practices Act / bribery / foreign bribery
  * securities_fraud   — insider trading / securities fraud / accounting fraud
  * healthcare_fraud   — Medicare / Medicaid / False Claims Act / kickback / pharma fraud
  * export_controls    — OFAC / sanctions / ITAR / BIS / export control
  * cyber              — ransomware / cyberattack / computer fraud / hacking indictment
  * money_laundering   — BSA / AML / money laundering / Bank Secrecy Act
  * environmental      — Clean Air Act / Clean Water Act / EPA / environmental crimes
  * opioid             — opioid / fentanyl / controlled substances distribution
  * corporate_res      — deferred prosecution / non-prosecution / corporate settlement
  * tax                — tax evasion / tax fraud / PPP fraud
  * (no tag)           — dropped (criminal non-catalyst — sex offense, assault, etc.)

Only tagged rows are written; press fallback not retained.

Output: doj_news.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "doj_news.csv"
UA = "Mozilla/5.0 CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.justice.gov/news/rss"

KIND_RULES = [
    ("antitrust", ("antitrust", "sherman act", "clayton act", "monopoliz",
                   "merger challenge", "sues to block", "sues to enjoin",
                   "price fixing", "price-fixing", "bid rigging", "bid-rigging",
                   "market allocation")),
    ("fcpa", ("fcpa", "foreign corrupt practices", "foreign bribery",
              "bribing foreign", "foreign official")),
    ("securities_fraud", ("insider trading", "securities fraud",
                          "accounting fraud", "market manipulation",
                          "pump-and-dump", "pump and dump", "stock fraud",
                          "10b-5", "ponzi")),
    ("healthcare_fraud", ("medicare fraud", "medicaid fraud",
                          "false claims act", "health care fraud",
                          "healthcare fraud", "kickback",
                          "anti-kickback", "pharmaceutical fraud")),
    ("export_controls", ("ofac", "sanctions evasion", "export control",
                         "itar violation", "bureau of industry and security",
                         "sanctions violation", "iran sanctions",
                         "russia sanctions", "north korea sanctions",
                         "evading sanctions")),
    ("cyber", ("ransomware", "computer fraud and abuse",
               "hacking indictment", "cyberattack", "cybercrime",
               "botnet", "darknet market", "crypto-mixer", "lazarus",
               "computer intrusion")),
    ("money_laundering", ("money laundering", "bank secrecy act",
                          "bsa violation", "anti-money laundering",
                          "aml violation", "msb violation",
                          "unlicensed money")),
    ("environmental", ("clean air act", "clean water act",
                       "environmental crimes", "resource conservation",
                       "rcra", "cercla", "superfund",
                       "oil spill", "illegal discharge")),
    ("opioid", ("opioid", "fentanyl distribution", "oxycodone",
                "controlled substances distribution",
                "drug distribution conspiracy")),
    ("corporate_res", ("deferred prosecution agreement",
                       "non-prosecution agreement",
                       "corporate resolution", "pleads guilty and agrees",
                       "agrees to plead guilty and pay",
                       "plea agreement with")),
    ("tax", ("tax evasion", "tax fraud", "paycheck protection program",
             "ppp fraud", "employee retention credit fraud",
             "irs fraud")),
    # Catch-all for corporate-impact enforcement events that don't match the
    # specialized kinds above. Requires a corporate context token in the same
    # blob to avoid catching street-crime + civil suits unrelated to markets.
    ("corporate_general", (
        "ceo indicted", "executive indicted", "executive sentenced",
        "ceo sentenced", "ceo charged", "executive charged",
        "company pleads guilty", "company agrees to pay",
        "publicly traded", "publicly-traded", "ticker symbol",
        "former chief", "shareholders defrauded", "investor fraud",
        "investment fraud", "wire fraud scheme", "mail fraud scheme",
        "to pay over $", "agrees to forfeit", "civil penalty of",
        "consent decree", "deferred prosecution",
    )),
]


def _classify(title: str, desc: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    return ""


def _fetch() -> bytes:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_pubdate(raw: str) -> str:
    s = raw.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s[:31], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        body = _fetch().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"doj_news: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"doj_news: keeping prior {OUT_CSV.name}")
        return

    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)

        title_raw = (t.group(1) if t else "").strip()
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title_raw))[:240]
        iso_date = _parse_pubdate(d.group(1) if d else "")
        desc_raw = desc.group(1) if desc else ""
        desc_clean = re.sub(r"<!\[CDATA\[|\]\]>", "", desc_raw)
        desc_txt = re.sub(r"<[^>]+>", " ", html.unescape(desc_clean))
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:500]
        link_url = (link.group(1) if link else "").strip()[:240]

        kind = _classify(title, desc_txt)
        if not kind or not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "title": title,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"doj_news: 0 tagged items, keeping {OUT_CSV.name}")
        else:
            fieldnames = ["filed", "kind", "title", "url", "captured_at"]
            with OUT_CSV.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writeheader()
            print("doj_news: 0 tagged items, wrote header-only CSV")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "title", "url", "captured_at"]
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
    print(f"doj_news: {len(rows)} tagged | {kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
