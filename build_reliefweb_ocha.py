#!/usr/bin/env python3
"""
build_reliefweb_ocha.py — ReliefWeb OCHA humanitarian operational tape.

Source: https://reliefweb.int/updates/rss.xml
        RSS 2.0 with RFC2822 pubDate + <category> country/source tags +
        description embedding country + source HTML divs.

ReliefWeb is the OCHA (UN Office for the Coordination of Humanitarian
Affairs) global humanitarian information portal aggregating updates
from UN agencies (OCHA, WFP, UNHCR, UNICEF, UNFPA, WHO, UNAIDS) + INGOs
(IFRC, MSF, Oxfam, Save the Children, CARE, WV, NRC, IRC, Mercy Corps)
+ government ministries across 30+ active crisis countries.

Document types: Flash Updates (acute crisis), Situation Reports (SitReps,
weekly/monthly), Protection Cluster Alerts, Humanitarian Response Plans
(HRPs), Humanitarian Needs Overviews (HNOs), Flash Appeals, Humanitarian
Snapshots, Dashboards, Assessments, Operational Updates.

Drives humanitarian logistics contractors (LDOS Leidos / BAH Booz Allen /
KBR on USAID/BHA/UN-WFP IDIQ contracts), food-aid commodity purchases
(ADM/BG/INGR/OXM on WFP + USAID sourcing), medical-aid donations (JNJ/
MRK/PFE/GSK/AZN/NOVN PEPFAR/Gavi/Global Fund programs), NFI/shelter
(tents/blankets/WASH kits procurement), freight/shipping (MAERSK/DSV/
KUEHN on agency global logistics clusters), satellite imagery (MAXR/PL
BKSY for OCHA damage assessments), remittance (WU/MGI on diaspora flows).

Distinct from build_un_news.py (UN News press firehose, statements-level),
build_gdacs_disasters.py (GDACS alert-level Red/Orange/Green rank),
build_iaea_nuclear.py (IAEA nuclear-specific), build_who_health.py (WHO
press). This is the OCHA operational-humanitarian tape sitting between
alert (GDACS) and press (UN News).

Output: reliefweb_ocha.csv — filed_utc, kind, title, link, summary.

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

URL = "https://reliefweb.int/updates/rss.xml"
OUT = pathlib.Path(__file__).resolve().parent / "reliefweb_ocha.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Document-type classifier (first match wins). Priority: doc-type over country.
DOC_TYPE_CLASSIFIER = [
    ("flash_update",       re.compile(r"\bflash update\b|\bflash appeal\b|\bFLASH\b", re.I)),
    ("situation_report",   re.compile(r"\bsituation report\b|\bSitRep\b|\bSituational Report\b|\bsnapshot\b", re.I)),
    ("response_plan",      re.compile(r"\bhumanitarian response plan\b|\bHRP\b|\bHNO\b|\bhumanitarian needs overview\b|\bstrategic response plan\b", re.I)),
    ("protection_alert",   re.compile(r"\bprotection cluster alert\b|\bprotection alert\b|\bprotection concern\b|\bprotection brief\b|\bprotection analysis update\b", re.I)),
    ("appeal_funding",     re.compile(r"\bappeal\b|\bCERF\b|\bCBPF\b|\bflash funding\b|\bfinancial tracking service\b|\bFTS\b|\bpooled fund\b", re.I)),
    ("assessment_survey",  re.compile(r"\bassessment\b|\bmulti-cluster\b|\bMSNA\b|\brapid assessment\b|\bMIRA\b|\bneeds assessment\b", re.I)),
    ("cluster_health",     re.compile(r"\bhealth cluster\b|\bdisease outbreak\b|\bcholera\b|\bmpox\b|\bEbola\b|\bmeasles\b|\bpolio\b|\boutbreak\b|\bpandemic\b", re.I)),
    ("cluster_food",       re.compile(r"\bfood security\b|\bfood cluster\b|\bIPC\b|\bfamine\b|\bmalnutrition\b|\bnutrition cluster\b|\bfood insecurity\b|\bhunger\b", re.I)),
    ("cluster_wash",       re.compile(r"\bWASH cluster\b|\bwater.{0,20}sanitation\b|\bhygiene promotion\b|\bcholera response\b", re.I)),
    ("cluster_shelter",    re.compile(r"\bshelter cluster\b|\bnon-food item\b|\bNFI\b|\bcamp coordination\b|\bCCCM\b|\bshelter.{0,15}NFI\b", re.I)),
    ("cluster_education",  re.compile(r"\beducation cluster\b|\beducation sector\b|\bschool.{0,30}conflict\b|\bout-of-school\b", re.I)),
    ("cluster_logistics",  re.compile(r"\blogistics cluster\b|\bemergency telecom\b|\bETC\b|\bsupply chain.{0,20}humanitarian\b", re.I)),
    ("cluster_protection", re.compile(r"\bprotection sector\b|\bGBV sub[- ]cluster\b|\bchild protection\b|\bmine action\b|\bhousing.{0,20}land.{0,20}property\b|\bHLP\b", re.I)),
    ("displacement_idp",   re.compile(r"\bIDP\b|\binternally displaced\b|\bdisplacement tracking matrix\b|\bDTM\b|\breturnee\b|\bresettlement\b", re.I)),
    ("refugee_cross",      re.compile(r"\brefugee.{0,20}response\b|\bUNHCR\b|\bcross-border\b|\bhost community\b|\basylum seeker\b", re.I)),
    ("cash_transfer",      re.compile(r"\bcash transfer\b|\bmulti-purpose cash\b|\bMPCA\b|\bvoucher\b|\bcash assistance\b", re.I)),
    ("epidemic_health",    re.compile(r"\boutbreak response\b|\bvaccination campaign\b|\bimmunization\b|\bdisease surveillance\b", re.I)),
    ("climate_disaster",   re.compile(r"\bcyclone\b|\btyphoon\b|\bhurricane\b|\bearthquake\b|\bflood\b|\bdrought\b|\btsunami\b|\bvolcan\b|\bla ni[nñ]a\b|\bel ni[nñ]o\b|\bTC [A-Z]\b", re.I)),
    ("conflict_escalation", re.compile(r"\bescalation of hostilities\b|\bceasefire\b|\bairstrike\b|\bshelling\b|\barmed conflict\b|\bcivilian casualties\b", re.I)),
]


# Country classifier (fallback if no doc-type match). Priority by crisis severity.
COUNTRY_CLASSIFIER = [
    ("gaza_palestine",  re.compile(r"\b(gaza|occupied palestinian|West Bank|Palestin)\b", re.I)),
    ("sudan_crisis",    re.compile(r"\b(Sudan|South Sudan|Darfur|Kordofan|Khartoum|RSF)\b", re.I)),
    ("ukraine_crisis",  re.compile(r"\b(Ukraine|Kharkiv|Donetsk|Luhansk|Zaporizhz|Kherson)\b", re.I)),
    ("lebanon_crisis",  re.compile(r"\b(Lebanon|southern Lebanon|Beirut|Bekaa|Tyre|Bint Jbeil)\b", re.I)),
    ("yemen_crisis",    re.compile(r"\b(Yemen|Sana|Aden|Hodeidah|Taiz)\b", re.I)),
    ("syria_crisis",    re.compile(r"\b(Syria|Idlib|Aleppo|Damascus|Homs)\b", re.I)),
    ("haiti_crisis",    re.compile(r"\b(Haiti|Port-au-Prince)\b", re.I)),
    ("afghanistan",     re.compile(r"\b(Afghanistan|Afghan|Kabul)\b", re.I)),
    ("myanmar_crisis",  re.compile(r"\b(Myanmar|Rakhine|Rohingya)\b", re.I)),
    ("drc_sahel",       re.compile(r"\b(Democratic Republic of the Congo|DRC|Goma|North Kivu|Burundi|Sahel|Burkina Faso|Mali|Niger|Chad|Cameroon)\b", re.I)),
    ("horn_africa",     re.compile(r"\b(Ethiopia|Somalia|Kenya|Eritrea|Djibouti|Tigray)\b", re.I)),
    ("pacific_islands", re.compile(r"\b(Solomon Islands|Vanuatu|Papua New Guinea|Fiji|Tonga|Samoa|Tuvalu|Kiribati|Cook Islands|Micronesia|TC [A-Z])\b", re.I)),
    ("mena_other",      re.compile(r"\b(Iraq|Iran|Libya|Egypt|Tunisia|Algeria|Morocco|Jordan|Israel)\b", re.I)),
    ("asia_other",      re.compile(r"\b(Bangladesh|Nepal|Sri Lanka|Pakistan|India|Indonesia|Philippines|Vietnam|Laos|Cambodia|Thailand|Malaysia)\b", re.I)),
    ("americas_crisis", re.compile(r"\b(Venezuela|Colombia|Ecuador|Peru|Bolivia|Guatemala|Honduras|El Salvador|Nicaragua|Mexico)\b", re.I)),
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
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
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
    for name, pat in DOC_TYPE_CLASSIFIER:
        if pat.search(hay):
            return name
    for name, pat in COUNTRY_CLASSIFIER:
        if pat.search(hay):
            return name
    return "humanitarian"


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
        print(f"reliefweb_ocha: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"reliefweb_ocha: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"reliefweb_ocha: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
