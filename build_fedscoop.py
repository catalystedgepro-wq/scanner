#!/usr/bin/env python3
"""
build_fedscoop.py — FedScoop federal-tech + cyber news tape.

Source: https://www.fedscoop.com/feed
        RSS 2.0 WordPress feed w/ dc:creator, category (multiple per item),
        content:encoded, pubDate RFC2822.

FedScoop is the federal IT/cyber trade-press firehose covering US federal
agency tech modernization, procurement, AI policy, zero-trust rollout,
CDM program, FedRAMP authorizations, cloud migration (AWS GovCloud, Azure
Gov, GCP federal, Oracle Gov), AI.gov, OMB memos, CIO/CISO leadership
changes, congressional oversight hearings, DOGE-adjacent efficiency
mandates, federal data-center buildouts, power/grid federal nexus.

Drives federal cyber-contractors (CRWD/PANW/OKTA/ZS/FTNT/S/TENB/RPD/MIME
on federal CDM Phase 3 + zero-trust EO + CISA BOD), cloud-federal
(AMZN AWS GovCloud + MSFT Azure Gov + GOOGL GCP federal + ORCL Gov Cloud +
IBM + SAP NS2), defence-IT/systems integrators (LDOS Leidos + BAH Booz
Allen + SAIC + CACI + GD IT + KBR + V2X + Vectrus + PSX Parsons + MAXR
Maxar + PLTR Palantir), AI-federal (PLTR + C3.ai + NVDA H100/H200 export
controls + AMD MI300 + INTC Gaudi3 federal wins + MSFT Copilot+PC + GOOGL
Gemini Enterprise), FedRAMP-authorized SaaS (SNOW Snowflake + ZM Zoom for
Government + BOX + DDOG Datadog FedRAMP High), federal-ISV (ORCL Cerner
VA/DHA MHS GENESIS + EPIC private + ORCL E-Business + ADBE Adobe Gov).

Distinct from build_darpa.py (DARPA defense-research), build_nsf_news.py
(NSF basic-research), build_doe_news.py (DOE applied-energy), build_sec_
litigation.py (SEC enforcement), build_fed_register.py (Federal Register
rulemaking). This is the federal-IT trade-press operational tape sitting
between policy (Federal Register) and execution (agency contracts).

Output: fedscoop.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

URL = "https://www.fedscoop.com/feed"
OUT = pathlib.Path(__file__).resolve().parent / "fedscoop.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered classifier. Most-specific kinds first.
CLASSIFIER = [
    ("ai_ml_policy",        re.compile(r"\b(artificial intelligence|\bAI\b|machine learning|\bML\b|generative AI|GenAI|LLM\b|large language model|chatbot|AI policy|AI.gov|AI executive order|AI governance)\b", re.I)),
    ("cybersecurity_cisa",  re.compile(r"\b(CISA|cybersecurity.{0,20}infrastructure|zero trust|zero-trust|CDM\b|BOD \d+|binding operational directive|FedRAMP|continuous diagnostic|SBOM\b|software bill of materials|threat intelligence|ransomware|SolarWinds|log4j|vulnerability disclosure)\b", re.I)),
    ("cloud_migration",     re.compile(r"\b(cloud migration|AWS GovCloud|Azure Government|GCP federal|Oracle Gov Cloud|JEDI|JWCC|Joint Warfighting Cloud|IC marketplace|cloud-first|multi-cloud federal)\b", re.I)),
    ("doge_efficiency",     re.compile(r"\b(DOGE\b|Department of Government Efficiency|Musk|workforce reduction|RIF\b|reduction in force|modernization act|MGT act|IT reform|IT modernization|Technology Modernization Fund|TMF\b)\b", re.I)),
    ("procurement_contract", re.compile(r"\b(IDIQ|GWAC\b|Alliant|Polaris|SEWP|8\(a\)|OTA\b|other transaction authority|sole source|task order|contract award|bid protest|GAO protest|GSA schedule)\b", re.I)),
    ("congressional_oversight",  re.compile(r"\b(hearing|testimony|Congress|Senate\b|House\b|budget request|appropriations|FY2\d|GAO report|inspector general|IG report|whistleblow|oversight committee|subcommittee)\b", re.I)),
    ("doge_data_center",    re.compile(r"\b(data center|data-center|electricity|power grid|grid capacity|interconnection queue|small modular reactor|colocation facility|hyperscaler|AI infrastructure)\b", re.I)),
    ("dod_defense",         re.compile(r"\b(Pentagon|Department of Defense|\bDoD\b|Space Force|CYBERCOM|USSOCOM|Joint Staff|combatant command|NSA\b|DISA\b|defense industrial base|DIB\b)\b", re.I)),
    ("intelligence_ic",     re.compile(r"\b(ODNI|intelligence community|\bIC\b|CIA\b|NSA\b|NGA\b|NRO\b|clearance|TS/SCI|top secret|classified|ICAM\b|mission partner)\b", re.I)),
    ("federal_cio_ciso",    re.compile(r"\b(federal CIO|CISO|chief information officer|chief information security officer|OCIO\b|OMB memo|OMB M-\d|federal CDO|chief data officer)\b", re.I)),
    ("data_governance",     re.compile(r"\b(data governance|data strategy|privacy act|FISMA\b|NIST 800|OSCAL|federal data strategy|open data|data mesh|data fabric)\b", re.I)),
    ("identity_access",     re.compile(r"\b(identity credential access management|ICAM|PIV\b|CAC\b|common access card|derived credential|phishing-resistant|FIDO\b|passkeys|login.gov|ID.me)\b", re.I)),
    ("quantum_federal",     re.compile(r"\b(quantum computing|post-quantum|\bPQC\b|NIST PQC|cryptographic agility|quantum-resistant|CNSA 2\.0|quantum-safe)\b", re.I)),
    ("biotech_health_fed",  re.compile(r"\b(HHS\b|CDC\b|NIH\b|\bFDA\b|VA\b Veterans Affairs|DHA\b|Defense Health|\bCMS\b|\bIHS\b|Indian Health Service|MHS GENESIS|VistA|biomedical IT)\b", re.I)),
    ("space_technology",    re.compile(r"\b(NASA\b|satellite|low earth orbit|\bLEO\b|commercial space|NOAA satellite|GOES-R|space domain awareness|SDA\b|proliferated LEO)\b", re.I)),
    ("energy_nuclear_fed",  re.compile(r"\b(DOE\b|Department of Energy|NNSA\b|national laboratory|Oak Ridge|Argonne|\bPNNL\b|LLNL\b|Sandia|Idaho National|small modular reactor|nuclear regulatory commission)\b", re.I)),
    ("workforce_training",  re.compile(r"\b(federal workforce|hiring|upskilling|reskilling|cyber workforce|AI workforce|OPM\b|pathways program|scholarship for service|SFS)\b", re.I)),
    ("budget_appropriations", re.compile(r"\b(budget|appropriation|continuing resolution|\bCR\b|shutdown|NDAA\b|National Defense Authorization Act|omnibus|FY2\d budget)\b", re.I)),
    ("irs_tax_modernization", re.compile(r"\b(IRS\b|Internal Revenue|Direct File|tax modernization|taxpayer experience|CADE\b|enterprise case management)\b", re.I)),
    ("state_local_gov",     re.compile(r"\b(state.{0,10}local|SLED\b|StateScoop|municipal|state CIO|governor|State Department)\b", re.I)),
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
    return "fedtech"


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
        print(f"fedscoop: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"fedscoop: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"fedscoop: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
