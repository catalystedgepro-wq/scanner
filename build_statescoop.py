#!/usr/bin/env python3
"""
build_statescoop.py — StateScoop state/local/education (SLED) IT tape.

Source: https://statescoop.com/feed/
        WordPress RSS 2.0 w/ dc:creator + multi-category + pubDate RFC2822.

StateScoop covers US state + local + education (SLED) government technology
firehose: state CIOs, broadband deployment (BEAD, E-Rate, Universal Service
Fund), state cybersecurity (SLCGP State and Local Cybersecurity Grant
Program), NASCIO conferences, state AI governance, DMV modernization,
state health IT (Medicaid modernization), unemployment insurance system
overhauls, 988 crisis line, 911 next-gen, state data strategy, state
privacy laws (CA CPRA/CO CPA/TX TDPSA/VA VCDPA enforcement), K-12 edtech,
higher-ed IT, court system modernization, state procurement (CoSN,
MS-ISAC), gov-tech vendors (Tyler Technologies TYL, NIC/PayIt, Accela,
Granicus, OpenGov).

Distinct from build_fedscoop.py (federal IT), build_cyberscoop.py (cyber
incident), build_defensescoop.py (DoD warfighter-IT) — StateScoop covers
the SLED market layer that drives TYL / CDW SLED resale / GDEN Granicus
+ Accela etc govtech SaaS + state-level infra (T-Mobile TMUS/VZ/T
fixed-wireless rural broadband + Charter CHTR/Comcast CMCSA state
ISP awards) + Medicaid ORCL Cerner.

Output: statescoop.csv — filed_utc, kind, title, link, summary.

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

URL = "https://statescoop.com/feed/"
OUT = pathlib.Path(__file__).resolve().parent / "statescoop.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered classifier. Most-specific kinds first.
CLASSIFIER = [
    ("broadband_bead",       re.compile(r"\b(broadband|BEAD\b|Broadband Equity|E-Rate|ERate|Universal Service Fund|\bUSF\b|rural broadband|fiber deployment|ACP\b|Affordable Connectivity|digital divide|digital equity|middle.?mile)\b", re.I)),
    ("state_cyber_slcgp",    re.compile(r"\b(SLCGP|State and Local Cybersecurity Grant|state cyber|municipal cyber|ransomware|MS-ISAC|CIS Security|local government attack|school ransomware|city hack|county breach)\b", re.I)),
    ("state_ai_governance",  re.compile(r"\b(state AI|state.{0,15}artificial intelligence|AI governance|AI procurement|GovAI|generative AI government|state AI policy|AI executive order state|AI task force)\b", re.I)),
    ("dmv_modernization",    re.compile(r"\b(DMV\b|Department of Motor|driver.?license|REAL ID|mobile driver license|mDL\b|vehicle registration|motor vehicle)\b", re.I)),
    ("medicaid_health_it",   re.compile(r"\b(Medicaid|MMIS|Medicaid management|state.{0,5}health|MES\b|enterprise system|Medicaid eligibility|HHS state|WIC\b|SNAP\b|TANF\b)\b", re.I)),
    ("unemployment_uiis",    re.compile(r"\b(unemployment insurance|\bUI\b system|UIIS|workforce system|claimant|identity proofing|benefit fraud|LWC\b|department of workforce|labor department)\b", re.I)),
    ("emergency_988_911",    re.compile(r"\b(988 crisis|988 lifeline|mental health crisis|NG911|next.?generation 911|next-gen 911|emergency services|dispatch|PSAP\b|public safety answering)\b", re.I)),
    ("state_data_cdo",       re.compile(r"\b(state CDO|chief data officer|state data strategy|data governance|data.?driven state|NASCIO|data sharing|open data|public data)\b", re.I)),
    ("state_privacy_law",    re.compile(r"\b(CPRA\b|CCPA\b|California privacy|CPA\b Colorado|TDPSA|Texas privacy|VCDPA|Virginia privacy|consumer data privacy|state privacy enforcement|Connecticut privacy|Oregon privacy|Utah privacy|DPIA|data protection)\b", re.I)),
    ("k12_edtech",           re.compile(r"\b(K-12|K12\b|school district|edtech|chromebook|classroom technology|digital learning|LMS\b|learning management|CoSN|COSN Consortium|student.{0,5}data|CIPA\b)\b", re.I)),
    ("higher_ed_it",         re.compile(r"\b(higher education|university IT|college CIO|EDUCAUSE|campus network|student information|Banner\b|Workday student|PeopleSoft|higher ed ransomware)\b", re.I)),
    ("court_system",         re.compile(r"\b(court system|courts modernization|e-filing|judicial system|case management|CMS court|digital court|Tyler court|CourtCall)\b", re.I)),
    ("cloud_migration_sled", re.compile(r"\b(cloud migration|state cloud|local cloud|StateRAMP|TX-RAMP|GovCloud state|AWS GovCloud|Azure Government|GCP state|multi.?cloud state)\b", re.I)),
    ("state_procurement",    re.compile(r"\b(RFP\b|request for proposal|state procurement|NASPO|NASCIO procurement|cooperative contract|multi.?state contract|bid protest state|procurement reform|GovTech contract)\b", re.I)),
    ("city_smart_city",      re.compile(r"\b(smart city|smart cities|connected city|IoT municipal|city government|mayor|city council|urban technology|civic tech)\b", re.I)),
    ("election_security",    re.compile(r"\b(election|voting system|CISA election|EAC\b|Election Assistance|secretary of state|absentee|ballot|voter registration|voting equipment|Dominion|ES&S)\b", re.I)),
    ("tax_revenue_modern",   re.compile(r"\b(state tax|revenue department|tax modernization|DoR\b|department of revenue|tax processing|integrated tax|FAST Enterprises)\b", re.I)),
    ("workforce_development", re.compile(r"\b(workforce|reskilling|upskilling|apprenticeship|state hiring|state workforce|public sector talent|tech talent pipeline)\b", re.I)),
    ("leadership_cio",       re.compile(r"\b(state CIO|chief information officer|CTO\b|chief technology officer|chief privacy officer|CPO\b|\bCISO\b|appointed|named|hired|resignation|steps down|promoted)\b", re.I)),
    ("local_county",         re.compile(r"\b(county\b|municipal\b|township|borough|precinct|city of [A-Z]|town of [A-Z]|village of)\b", re.I)),
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
    return "sledtech"


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
        print(f"statescoop: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"statescoop: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"statescoop: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
