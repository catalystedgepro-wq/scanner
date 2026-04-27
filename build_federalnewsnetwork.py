#!/usr/bin/env python3
"""
build_federalnewsnetwork.py — Federal News Network (FNN) fed-employee + ops tape.

Source: https://federalnewsnetwork.com/feed/
        WordPress RSS 2.0 w/ dc:creator + multi-category + pubDate RFC2822 +
        content:encoded.

Federal News Network is Hubbard Radio's (WFED 1500 AM DC) federal
employee + federal ops trade-press — the "what federal workers actually
listen to on their commute" outlet. Covers federal workforce benefits
(TSP, FEHB health, pay freezes, performance management), government
shutdown mechanics, DoD Budget + contract awards, IRS/VA/SSA agency
operations, federal HR (OPM, Schedule F, RIF, probationary), CISA
cyber directives, Section 508 accessibility, federal finance (CFO
council, Treasury), GAO/OIG/IG reports, DHS/ICE/CBP/TSA border+homeland,
and general federal news from a federal-employee lens distinct from
enterprise IT (Nextgov/FCW) or policy short-form (FedScoop).

Output: federalnewsnetwork.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import timezone
from email.utils import parsedate_to_datetime

URL = "https://federalnewsnetwork.com/feed/"
OUT = pathlib.Path(__file__).resolve().parent / "federalnewsnetwork.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


CLASSIFIER = [
    ("shutdown_cr",          re.compile(r"\b(government shutdown|shutdown\b|continuing resolution|\bCR\b|lapse in appropriations|furlough|back pay|shutdown bill|reopen\b|reopening|stopgap)\b", re.I)),
    ("tsp_retirement",       re.compile(r"\b(Thrift Savings Plan|\bTSP\b|retirement annuity|FERS\b|CSRS\b|federal retire|pension|L Fund|G Fund|C Fund|F Fund|I Fund|S Fund)\b", re.I)),
    ("fehb_health",          re.compile(r"\b(FEHB\b|Federal Employees Health|open season|OPM health|postal service health|PSHB\b|dental vision|FEDVIP|health benefits federal)\b", re.I)),
    ("opm_hr_workforce",     re.compile(r"\b(OPM\b|Office of Personnel|federal workforce|Schedule F|RIF\b|reduction in force|probationary|deferred resignation|federal hiring|pay freeze|pay raise|locality pay|GS\-\d|General Schedule)\b", re.I)),
    ("cyber_nist_cisa",      re.compile(r"\b(cybersecurity|CISA\b|NIST\b|cyber directive|zero trust|zero-trust|EO 14028|ransomware|OT security|operational technology|ICS security|CDM\b|continuous diagnostic)\b", re.I)),
    ("ai_federal_fnn",       re.compile(r"\b(artificial intelligence|\bAI\b|generative AI|GenAI|machine learning|\bLLM\b|AI Action Plan|federal AI|OSTP\b|chatbot federal)\b", re.I)),
    ("dhs_ice_cbp_tsa",      re.compile(r"\b(\bDHS\b|Homeland Security|\bICE\b|Immigration and Customs|Border Patrol|\bCBP\b|\bTSA\b|Transportation Security|border security|immigration enforcement)\b", re.I)),
    ("dod_fnn",              re.compile(r"\b(Pentagon|Department of Defense|\bDoD\b|Army\b|Navy\b|Air Force|Space Force|Marine Corps|Joint Chiefs|combatant command|warfighter|military)\b", re.I)),
    ("irs_tax_admin",        re.compile(r"\b(IRS\b|Internal Revenue|tax season|Direct File|taxpayer|tax administration|commissioner Werfel|Bisignano)\b", re.I)),
    ("va_veterans",          re.compile(r"\b(\bVA\b|Veterans Affairs|veteran\b|VistA|Cerner|Oracle Health|veterans benefit|VBA\b|\bVHA\b)\b", re.I)),
    ("ssa_benefits",         re.compile(r"\b(Social Security|SSA\b|retirement benefit|disability determination|\bSSI\b|\bSSDI\b|Bisignano)\b", re.I)),
    ("contract_acquisition", re.compile(r"\b(contract award|IDIQ|task order|\bOTA\b|GSA contract|Alliant|SEWP|CIO-SP|GWAC|\bBPA\b|blanket purchase|FAR\b|DFARS|bid protest|CMMC)\b", re.I)),
    ("budget_appropriations_fnn", re.compile(r"\b(appropriations|budget request|fiscal year|\bFY2[6-9]\b|\bFY3\d\b|omnibus|minibus|reconciliation|debt ceiling|CBO scoring)\b", re.I)),
    ("gao_oig_oversight",    re.compile(r"\b(GAO\b|Government Accountability|inspector general|\bOIG\b|\bIG\b report|oversight\b|watchdog|audit report|whistleblower)\b", re.I)),
    ("congress_fnn",         re.compile(r"\b(Congress\b|Senate\b|House\b|committee markup|HSGAC|HCOGR|SASC|HASC|Appropriations Committee|subcommittee|floor vote)\b", re.I)),
    ("cloud_fedramp_fnn",    re.compile(r"\b(FedRAMP|cloud migration|AWS GovCloud|Azure Gov|Google Public Sector|\bIL4\b|\bIL5\b|\bIL6\b|cloud smart|hybrid cloud federal)\b", re.I)),
    ("financial_cfo",        re.compile(r"\b(CFO council|Treasury Department|financial management|audit clean|unmodified opinion|Digital Accountability|DATA Act|Payment Integrity|improper payment)\b", re.I)),
    ("postal_usps",          re.compile(r"\b(USPS\b|postal service|Louis DeJoy|DeJoy\b|postal reform|mail delivery|postal rate|postal employee)\b", re.I)),
    ("leadership_confirm",   re.compile(r"\b(confirmed by Senate|Senate confirm|nominated\b|nomination|acting secretary|deputy secretary|under secretary|assistant secretary|appointed\b|stepping down|resigns\b|sworn in)\b", re.I)),
    ("tech_modernization_fnn", re.compile(r"\b(modernization|legacy system|COBOL\b|mainframe|Technology Modernization Fund|\bTMF\b|technical debt|21st Century IDEA|digital services|\bUSDS\b|\b18F\b)\b", re.I)),
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


def extract_all(body: str, tag: str) -> list[str]:
    return [unescape_clean(x) for x in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)]


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


def classify(title: str, summary: str, categories: list[str]) -> str:
    hay = f"{title}  {summary}  {' '.join(categories)}"
    for name, pat in CLASSIFIER:
        if pat.search(hay):
            return name
    return "fed_ops"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        categories = extract_all(raw, "category")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary, categories)
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
        print(f"federalnewsnetwork: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"federalnewsnetwork: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"federalnewsnetwork: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
