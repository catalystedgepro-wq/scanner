#!/usr/bin/env python3
"""
build_nextgov.py — Nextgov/FCW federal IT + cyber trade-press tape.

Source: https://www.nextgov.com/rss/all/
        WordPress-style RSS 2.0 w/ dc:creator + category + pubDate + content:encoded.

Nextgov/FCW is the GovExec Media flagship for US federal civilian technology +
federal enterprise cybersecurity + federal agency modernization + federal
IT policy. Merged 2022 from Nextgov (Atlantic Media enterprise-IT) + FCW
(1987 Federal Computer Week). Covers: White House OSTP AI, OMB M-memos,
federal CIO/CISO turnover, agency modernization (IRS legacy, SSA, VA, DoD),
federal cyber (CISA, NSA, CYBERCOM), AI export controls, zero-trust
federal rollout (EO 14028), FedRAMP cloud authorizations, DOGE cuts,
IRS Direct File, federal procurement (GSA Alliant 2, SEWP, CIO-SP),
congressional oversight (HCOGR, SASC, HASC), AI distillation attacks,
foreign threats (China/Russia/Iran/DPRK), contract awards, leadership
nominations (Senate confirmations).

Distinct from build_fedscoop.py (Scoop sister — federal-policy short-form),
build_cyberscoop.py (cyber incident), build_defensescoop.py (DoD),
build_statescoop.py (SLED). Nextgov/FCW is longer-form enterprise-IT +
agency-modernization reporting; different editorial lens from Scoop News
Group. Drives PLTR / MSFT / GOOGL / NVDA / CRWD / PANW / OKTA / BAH / LDOS
/ SAIC / CACI / GDIT / V2X / LEI / ACN / ORCL / AMZN federal revenue
catalysts 3-12mo ahead of SEC 8-K contract disclosures.

Output: nextgov.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.nextgov.com/rss/all/"
OUT = pathlib.Path(__file__).resolve().parent / "nextgov.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered classifier. Most-specific kinds first.
CLASSIFIER = [
    ("ai_ml_federal",        re.compile(r"\b(artificial intelligence|\bAI\b|machine learning|generative AI|GenAI|large language model|\bLLM\b|foundation model|frontier AI|AI Action Plan|OSTP AI|AI distillation|AI export|NAIAC|AI executive order|AI EO|\bNIST AI|AI RMF|responsible AI)\b", re.I)),
    ("cybersecurity_cisa",   re.compile(r"\b(CISA\b|cybersecurity|cyber defense|zero trust|zero-trust|EO 14028|14028|cyber advisory|cyber directive|BOD\b|emergency directive|ransomware|ZT architecture|CDM program|continuous diagnostics)\b", re.I)),
    ("irs_modernization",    re.compile(r"\b(IRS\b|Internal Revenue|Direct File|individual master file|\bIMF\b tax|tax modernization|tax processing|IRS legacy|tax filing)\b", re.I)),
    ("doge_workforce_cuts",  re.compile(r"\b(DOGE\b|Department of Government Efficiency|Musk\b|federal workforce|workforce cuts|RIF\b|reduction in force|probationary|deferred resignation|Schedule F|fork in the road|return to office|RTO mandate|federal layoff)\b", re.I)),
    ("cloud_fedramp",        re.compile(r"\b(FedRAMP|fed ramp|cloud migration|GovCloud|AWS GovCloud|Azure Government|Azure Gov|GCP Gov|Google Public Sector|IL4\b|IL5\b|IL6\b|StateRAMP|cloud authorization|ATO cloud|cloud smart)\b", re.I)),
    ("procurement_contract", re.compile(r"\b(contract award|IDIQ|OTA\b|GSA Alliant|Alliant 2|SEWP V|CIO-SP|8\(a\)|GWAC|BPA|blanket purchase|task order|protest GAO|COFC|bid protest|CMMC\b|OASIS\+|polaris)\b", re.I)),
    ("dod_defense_nextgov",  re.compile(r"\b(Pentagon|Department of Defense|\bDoD\b|Joint Chiefs|combatant command|CYBERCOM|NORTHCOM|INDOPACOM|Air Force\b|Space Force\b|Army\b|Navy\b|Marine Corps|DARPA\b|autonomous weapon|warfighter)\b", re.I)),
    ("intelligence_ic",      re.compile(r"\b(intelligence community|\bIC\b|\bODNI\b|\bCIA\b|\bNSA\b|\bDIA\b|\bNGA\b|\bNRO\b|FBI\b|classified\b|TS\/SCI|\bSCI\b|counterintelligence|foreign intelligence)\b", re.I)),
    ("federal_cio_ciso",     re.compile(r"\b(federal CIO|agency CIO|federal CISO|agency CISO|chief information officer|chief information security|chief digital|chief data officer|CTO federal|deputy CIO|acting CIO|named director|nominated|confirmed by Senate)\b", re.I)),
    ("identity_access_fed",  re.compile(r"\b(login\.gov|ID\.me|identity proofing|PIV\b|\bCAC\b card|multi-factor|MFA federal|FIDO|phishing-resistant|passwordless|IAL2|IAL3|AAL2|AAL3|Okta federal|credential)\b", re.I)),
    ("data_governance_fed",  re.compile(r"\b(Evidence Act|open data|data strategy|data.gov|chief data officer|CDO council|data sharing|privacy impact|PIA\b|Paperwork Reduction|data maturity|data governance federal)\b", re.I)),
    ("quantum_federal",      re.compile(r"\b(quantum computing|quantum-safe|post-quantum|\bPQC\b|NIST quantum|quantum networking|NQI Act|quantum information)\b", re.I)),
    ("space_federal",        re.compile(r"\b(NASA\b|SpaceX|commercial space|FAA AST|launch license|Starlink federal|MILSATCOM|satellite communication|LEO constellation|commercial LEO|space policy)\b", re.I)),
    ("health_federal_va",    re.compile(r"\b(\bVA\b|Veterans Affairs|VistA|Cerner|Oracle Health|Indian Health|\bIHS\b|military health|DHA\b|Defense Health|electronic health record|\bEHR\b federal)\b", re.I)),
    ("social_security",      re.compile(r"\b(Social Security|SSA\b|\bSSN\b|retirement|disability determination|Bisignano|DAC program|SSI\b|SSDI\b)\b", re.I)),
    ("energy_nuclear_fed",   re.compile(r"\b(DOE\b|Department of Energy|national lab|Los Alamos|Oak Ridge|Argonne|Sandia|\bNNSA\b|nuclear security|grid security|DOE cyber|electricity|SCADA)\b", re.I)),
    ("budget_appropriations", re.compile(r"\b(appropriations|budget request|continuing resolution|\bCR\b shutdown|government shutdown|Congressional Budget|CBO scoring|fiscal year|FY26\b|FY27\b|omnibus|minibus)\b", re.I)),
    ("foreign_threats",      re.compile(r"\b(China\b|Chinese\b|\bPRC\b|Russia\b|Russian\b|Iran\b|Iranian\b|North Korea|DPRK\b|cyber espionage|state-sponsored|APT\d+|nation-state actor|foreign adversary|Volt Typhoon|Salt Typhoon|Flax Typhoon)\b", re.I)),
    ("congress_oversight",   re.compile(r"\b(Congress\b|Senate\b|House\b|committee|subcommittee|HCOGR|SASC|HASC|HSGAC|oversight hearing|GAO report|OIG\b|inspector general|whistleblower|markup|floor vote)\b", re.I)),
    ("federal_tech_policy",  re.compile(r"\b(federal IT|enterprise IT|modernization|legacy system|COBOL\b|mainframe|technical debt|technology transformation|TMF\b|Technology Modernization Fund|21st Century IDEA)\b", re.I)),
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
    return "fedtech_longform"


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
        print(f"nextgov: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"nextgov: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"nextgov: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
