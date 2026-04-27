#!/usr/bin/env python3
"""
build_govexec.py — Government Executive (GovExec) federal executive-branch tape.

Source: https://www.govexec.com/rss/all/
        WordPress-style RSS 2.0 w/ dc:creator + category + pubDate + content:encoded.

Government Executive is the **GovExec Media flagship parent** covering
the executive branch broadly: federal management, workforce policy
(OPM, Schedule F, RIF, probationary, pay), agency leadership (Senate
confirmations, nominations, resignations), federal contracting (IDIQ,
GSA, SEWP, CIO-SP, bid protests), DOGE workforce reduction fallout,
USPS reforms and executive-branch mail policy, federal retirement
benefits (TSP, FERS, CSRS), pay and performance, IG/GAO oversight,
federal health (VA, DHA, IHS), IRS operations, SSA operations, federal
real estate (GSA PBS), FedRAMP cloud, ATF/DEA/FBI/DOJ law enforcement,
DHS/ICE/CBP, Treasury, State Department, DOE/NNSA, federal workforce
reorganization. Distinct from Nextgov/FCW sister (enterprise IT) —
GovExec covers the broader *executive branch management* beat across
all agencies with a Washington-insider lens.

Complements fedscoop (policy short-form), cyberscoop (cyber), defensescoop
(DoD warfighter), statescoop (SLED), nextgov (fed enterprise-IT),
federalnewsnetwork (fed-employee radio beat) — GovExec provides
*executive-branch leadership + management decisions + USPS/management*
reporting that the IT-focused outlets don't prioritize.

Output: govexec.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.govexec.com/rss/all/"
OUT = pathlib.Path(__file__).resolve().parent / "govexec.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


CLASSIFIER = [
    ("usps_postal_policy",   re.compile(r"\b(USPS\b|Postal Service|postmaster general|DeJoy\b|mail ballot|mail-in vote|postal reform|postal rate|postal employee|letter carrier|mail delivery)\b", re.I)),
    ("doge_musk_cuts",       re.compile(r"\b(DOGE\b|Department of Government Efficiency|Musk\b|Vivek\b|probationary fir|deferred resignation|fork in the road|mass fire|federal layoff|RIF\b|reduction in force|workforce cut)\b", re.I)),
    ("schedule_f_merit",     re.compile(r"\b(Schedule F\b|Schedule Career|merit system|career civil|political appointee|\bSES\b|Senior Executive Service|MSPB|Merit Systems Protection|whistleblower|at-will)\b", re.I)),
    ("opm_hr_govex",         re.compile(r"\b(OPM\b|Office of Personnel Management|federal hiring|federal workforce|federal employee|return to office|RTO\b|remote work federal|telework federal|locality pay|pay freeze|GS-\d)\b", re.I)),
    ("retirement_tsp_govex", re.compile(r"\b(Thrift Savings|\bTSP\b|FERS\b|CSRS\b|federal retirement|annuity|pension federal|retire federal|early retire)\b", re.I)),
    ("leadership_confirm",   re.compile(r"\b(confirmed by Senate|Senate confirm|nominated|nomination|acting secretary|deputy secretary|under secretary|assistant secretary|administrator of|appointed\b|stepping down|resigns\b|sworn in|fired\b|ousted)\b", re.I)),
    ("contract_acquisition", re.compile(r"\b(contract award|IDIQ\b|task order|\bOTA\b|GSA contract|Alliant|SEWP|CIO-SP|GWAC|\bBPA\b|blanket purchase|FAR\b|DFARS|bid protest|CMMC\b|OASIS)\b", re.I)),
    ("shutdown_cr_govex",    re.compile(r"\b(government shutdown|shutdown\b|continuing resolution|\bCR\b|lapse in appropriations|furlough|back pay|reopen government|stopgap bill|shutdown bill)\b", re.I)),
    ("budget_fy",            re.compile(r"\b(appropriations|budget request|fiscal year|\bFY2[6-9]\b|\bFY3\d\b|omnibus|minibus|reconciliation|debt ceiling|CBO\b|budget deal|top-line)\b", re.I)),
    ("gao_oig_govex",        re.compile(r"\b(GAO\b|Government Accountability|inspector general|\bOIG\b|\bIG\b report|audit report|watchdog|improper payment|Payment Integrity|fraud waste)\b", re.I)),
    ("dhs_ice_law_enf",      re.compile(r"\b(\bDHS\b|Homeland Security|\bICE\b|Immigration|Border Patrol|\bCBP\b|\bTSA\b|Coast Guard|\bFEMA\b|deportation|asylum)\b", re.I)),
    ("fbi_doj_law_enf",      re.compile(r"\b(\bFBI\b|Department of Justice|\bDOJ\b|\bATF\b|\bDEA\b|Drug Enforcement|U\.S\. Attorney|federal prosecution|federal prison|BOP\b Bureau of Prisons)\b", re.I)),
    ("dod_management_govex", re.compile(r"\b(Pentagon|Department of Defense|\bDoD\b|Secretary of Defense|Joint Chiefs|Army\b|Navy\b|Air Force|Space Force|Marine Corps|military pay|military benefit)\b", re.I)),
    ("va_veterans_govex",    re.compile(r"\b(\bVA\b|Veterans Affairs|VBA\b|VHA\b|veteran|VistA|Cerner|Oracle Health|veterans benefit|veterans healthcare)\b", re.I)),
    ("state_diplomacy",      re.compile(r"\b(State Department|Secretary of State|USAID\b|foreign service|\bFSO\b|embassy|diplomat|consular|foreign aid|diplomatic)\b", re.I)),
    ("treasury_financial",   re.compile(r"\b(Treasury Department|Treasury Secretary|Bessent|sanctions\b|\bOFAC\b|\bFinCEN\b|BSA\b|AML\b|Bureau of Fiscal|debt limit|debt issuance)\b", re.I)),
    ("energy_doe_nnsa",      re.compile(r"\b(\bDOE\b|Department of Energy|\bNNSA\b|Secretary of Energy|national lab|nuclear weapon|nuclear stockpile|Los Alamos|Oak Ridge|Savannah River|Hanford)\b", re.I)),
    ("irs_ssa_benefits",     re.compile(r"\b(\bIRS\b|Internal Revenue|Social Security|\bSSA\b|Direct File|Bisignano|disability determination|\bSSI\b|\bSSDI\b)\b", re.I)),
    ("federal_real_estate",  re.compile(r"\b(federal real estate|federal building|GSA PBS|Public Building|lease\b federal|office space federal|headquarters move|disposition|FBI headquarters)\b", re.I)),
    ("cyber_ai_govex",       re.compile(r"\b(cybersecurity|CISA\b|zero trust|zero-trust|EO 14028|ransomware|artificial intelligence|\bAI\b|generative AI|OSTP|AI Action Plan)\b", re.I)),
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
    return "fed_mgmt"


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
        print(f"govexec: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"govexec: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"govexec: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
