#!/usr/bin/env python3
"""
build_meritalk.py — MeriTalk federal IT community trade-press tape.

Source: https://www.meritalk.com/feed/
        WordPress RSS 2.0 w/ dc:creator + category + content:encoded + podcast tags.

MeriTalk is a federal-IT *community-driven* trade-press published from
Alexandria VA, distinct from GovExec Media (Nextgov/FCW/GovExec),
Scoop News Group (FedScoop/CyberScoop/DefenseScoop/StateScoop),
and Hubbard Radio (Federal News Network). Its tagline
"Improving the Outcomes of Government IT" frames a vendor-community
funded operator-tactical lens — guest commentaries, MeriTalking podcast,
MeriTalk Brainstorm events, Tech Spotlight roundtables, Federal 100
awards, Cyber Defenders Council, Cloud Computing Caucus, AI Exchange,
Data Exchange, Women in Tech federal community, Small Business federal
contractor network. Deep coverage of IT/OT convergence, zero trust,
FedRAMP 20x, AI Action Plan, quantum readiness, FITARA grading, TBM,
agile software delivery, federal acquisition reform, and the vendor
partner ecosystem supporting federal IT.

Complements govexec (exec-branch mgmt parent), nextgov (IT enterprise
longform), fedscoop (policy short-form), cyberscoop (cyber), defensescoop
(DoD warfighter), statescoop (SLED), federalnewsnetwork (fed-employee
radio) — MeriTalk provides the *community + vendor-partner ecosystem*
lens other outlets don't cover with the same operator-tactical depth.

Output: meritalk.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.meritalk.com/feed/"
OUT = pathlib.Path(__file__).resolve().parent / "meritalk.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


CLASSIFIER = [
    ("it_ot_convergence",    re.compile(r"\b(IT/OT\b|IT-OT\b|operational technology|\bOT\b security|ICS\b|industrial control|SCADA\b|critical infrastructure cyber|purdue model)\b", re.I)),
    ("ai_exchange_fed",      re.compile(r"\b(AI Exchange|artificial intelligence|\bAI\b|generative AI|machine learning|LLM\b|foundation model|AI Action Plan|AI CoP|AI community)\b", re.I)),
    ("cyber_defenders",      re.compile(r"\b(Cyber Defenders|cybersecurity|zero trust|zero-trust|CISA\b|EO 14028|ransomware|SBOM\b|CDM\b|Continuous Diagnostics|endpoint|SOC\b|SIEM\b)\b", re.I)),
    ("cloud_caucus_fedramp", re.compile(r"\b(Cloud Computing Caucus|FedRAMP\b|FedRAMP 20x|cloud smart|cloud first|IL[2-6]\b|multi-cloud|hybrid cloud|JWCC\b|cloud migration)\b", re.I)),
    ("data_exchange_meri",   re.compile(r"\b(Data Exchange|data strategy|Evidence Act|chief data officer|\bCDO\b|data governance|data mesh|data fabric|data lake|AI-ready data)\b", re.I)),
    ("fitara_tbm_scorecard", re.compile(r"\b(FITARA\b|Federal IT Acquisition|scorecard\b|TBM\b|technology business management|IT spending|IT portfolio|CIO authority)\b", re.I)),
    ("federal_100_awards",   re.compile(r"\b(Federal 100|Fed 100|Cyber Defenders award|MeriTalk award|Innovator award|Women in Tech award|Rising Star)\b", re.I)),
    ("brainstorm_events",    re.compile(r"\b(Brainstorm\b|Tech Spotlight|Cyber Central|Cloud Central|Data Central|MeriTalk event|round ?table|fireside|community gathering)\b", re.I)),
    ("meritalking_podcast",  re.compile(r"\b(MeriTalking\b|podcast episode|episode \d|listen\b|audio\b|tune in|subscribe\b)\b", re.I)),
    ("small_biz_fed",        re.compile(r"\b(small business|\bSBA\b|\b8\(a\)\b|HUBZone\b|WOSB\b|SDVOSB\b|mentor.?protege|GSA Schedule|small biz federal)\b", re.I)),
    ("women_in_tech_fed",    re.compile(r"\b(Women in Tech|WIT\b|women in STEM|gender diversity|DEI\b|inclusion tech|diversity federal IT)\b", re.I)),
    ("quantum_readiness",    re.compile(r"\b(quantum\b|post-quantum|\bPQC\b|quantum readiness|quantum computing|lattice crypto|cryptographic transition)\b", re.I)),
    ("agile_devsecops",      re.compile(r"\b(agile\b|DevSecOps|DevOps\b|continuous integration|\bCI/CD\b|scrum\b|sprint\b|product management federal|software factory)\b", re.I)),
    ("identity_access_meri", re.compile(r"\b(identity\b|\bICAM\b|PIV\b|CAC\b|login\.gov|ID\.me|passwordless|phishing-resistant|FIDO2?\b|derived credential)\b", re.I)),
    ("network_5g_edge",      re.compile(r"\b(\b5G\b|network modernization|SD-WAN\b|TIC \d|Trusted Internet|edge computing|O-RAN|spectrum\b federal)\b", re.I)),
    ("doge_workforce_meri",  re.compile(r"\b(\bDOGE\b|workforce\b|Schedule F\b|RIF\b|reskilling|upskilling|tech talent|hire federal|cyber talent|tech workforce)\b", re.I)),
    ("defense_dod_meri",     re.compile(r"\b(DoD\b|Pentagon|Army\b|Navy\b|Air Force|Space Force|\bCMMC\b|defense IT|warfighter\b|\bJADC2\b|JWCC\b)\b", re.I)),
    ("civilian_agency_it",   re.compile(r"\b(\bVA\b IT|SSA\b IT|IRS\b IT|USDA\b|\bDHS\b IT|\bHHS\b|\bDOE\b IT|Commerce IT|civilian agency|non-defense IT)\b", re.I)),
    ("acquisition_reform",   re.compile(r"\b(acquisition reform|FAR\b|DFARS|OTA\b|procurement\b|task order|\bIDIQ\b|GSA Alliant|SEWP\b|CIO-SP|streamline buying)\b", re.I)),
    ("vendor_partner_eco",   re.compile(r"\b(Armis\b|Palo Alto|Zscaler\b|CrowdStrike|SentinelOne|Splunk\b|ServiceNow|Salesforce\b|Microsoft\b|Amazon\b|AWS\b|Google Cloud|Oracle\b|IBM\b|Dell\b|HPE\b|Cisco\b|VMware|Red Hat|Snowflake|Databricks|Elastic\b|Cloudflare\b)\b", re.I)),
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
    return "fedit_community"


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
        print(f"meritalk: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"meritalk: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"meritalk: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
