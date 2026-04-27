#!/usr/bin/env python3
"""build_gao_reports.py - US Government Accountability Office reports feed.

GAO is the nonpartisan audit arm of Congress — it investigates how
federal dollars are spent, identifies program waste/fraud/abuse, and
publishes findings that directly shape appropriations. Complements
CBO (bill scoring) with audit-based, backward-looking fiscal tape.

GAO reports move:
- defense primes (NOC LMT RTX GD LHX HII) on DoD contract waste / F-35 / LCS
- VA-exposed health ops (HCA UHS THC CYH VET) on VA Community Care
- Medicare/Medicaid beneficiaries (UNH HUM CNC CVS ELV MOH) on CMS findings
- infra (CAT DE URI VMC MLM) on IIJA/CHIPS program execution
- GSA contractors (IRM CBRE JLL FLS) on federal real property reorg
- AI acquisition winners (MSFT GOOGL AMZN PLTR CRWD) on AI procurement
- tariff / customs exposure (FedEx UPS EXPD CHRW MATX) on CBP + trade

No existing `gao_`, `accountability_office_`, or `audit_report_` spoke.

9-kind priority-ordered classifier on title + description:
- defense          : DoD, Navy, Army, Air Force, Space Force, Pentagon, F-35, missile, submarine
- va_health        : VA Health Care, Veterans, veteran caregiver, VHA, behavioral health
- healthcare       : Medicare, Medicaid, CMS, pharmacy, drug pricing, nursing home, HHS
- ai_tech          : Artificial Intelligence, AI, cyber, cybersecurity, information technology, IT modernization
- fin_mgmt         : financial management, fiscal, budget, appropriations, federal debt, Treasury, CBO counterpart
- federal_property : federal real property, GSA, reorganization, leasing, disposal
- fraud            : combating fraud, illicit, enforcement, waste, abuse, program integrity
- testimony        : testimony, statement for the record, hearing, before the committee
- press            : fallback

Source: gao.gov/rss/reports.xml (RSS 2.0, ~100 report rolling window).
Output: gao_reports.csv
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
OUT_CSV = ROOT / "gao_reports.csv"
FEED = "https://www.gao.gov/rss/reports.xml"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("defense",          ["department of defense", " dod ", " navy ",
                          " army ", " air force ", "space force",
                          " pentagon ", " f-35 ", " f35 ", "missile ",
                          "submarine", "combatant", "weapon system",
                          "nuclear deterrent", "defense contract",
                          "military ", "warfighter", "sea systems"]),
    ("va_health",        ["veterans affairs", " va ", "veteran ",
                          "veterans ", "veteran caregiver",
                          "veteran community care", "vha",
                          "veteran homeless", "veteran benefits"]),
    ("healthcare",       ["medicare", "medicaid", " cms ",
                          "health care", "nursing home", "pharmacy",
                          "drug pricing", "behavioral health",
                          " hhs ", "substance use", "opioid",
                          "mental health", "crisis pregnancy"]),
    ("ai_tech",          ["artificial intelligence", " ai ",
                          "cybersecurity", " cyber ", "information technology",
                          "it modernization", "technology transfer",
                          "science and technology", "stem ",
                          "ai acquisition", "ai procurement"]),
    ("fin_mgmt",         ["financial management", " fiscal ",
                          "federal debt", " budget ", "appropriation",
                          " treasury ", "financial report",
                          "fiscal outlook", "borrowing needs",
                          "debt management", "revolving fund",
                          "gift shop revolving"]),
    ("federal_property", ["federal real property", " gsa ",
                          "federal property", "real property",
                          "reorganization", "federal lease",
                          "federal building", "disposal"]),
    ("fraud",            ["combating fraud", " fraud ", " illicit ",
                          " waste ", " abuse ", "program integrity",
                          "improper payment", "e-cigarette",
                          "unauthorized ", "doj enforcement"]),
    ("testimony",        ["testimony", "statement for the record",
                          "before the committee", "before the subcommittee",
                          "before the house", "before the senate",
                          "congressional hearing"]),
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


def _strip_tags(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", no_tags).strip()


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


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"gao_reports fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        desc = re.search(r"<description>(.*?)</description>", chunk, re.S)
        if not (t and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        filed = _parse_pub(_strip_cdata(d.group(1))) if d else None
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = _strip_cdata(l.group(1)).strip()
        description = ""
        if desc:
            description = _strip_tags(html.unescape(_strip_cdata(desc.group(1))))
            description = description[:2000]
        items.append({
            "filed": filed,
            "kind": classify(title + " " + description),
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"gao_reports: no rows; preserved {OUT_CSV.name}")
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
    print(f"gao_reports: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
