#!/usr/bin/env python3
"""
build_occ.py — Office of the Comptroller of the Currency (OCC) bulletins tape.

Source: https://www.occ.gov/rss/occ_bulletins.xml
        Windows-1252-encoded RSS 2.0 (Rhythmyx CMS) w/ pubDate RFC2822 + category.

OCC is the **federal regulator of national banks, federal savings
associations, and federal branches of foreign banks** — the largest
prudential regulator by asset base (~$15T supervised). OCC Bulletins
are the primary supervisory-guidance channel telegraphing rule-making
direction and examiner priorities 90-365 days before enforcement or
formal regulation. Coverage spans:
- Capital rules: Basel III endgame, CBLR community-bank leverage,
  SA-CCR derivatives exposure, G-SIB surcharge, stress-capital buffer
- Liquidity: LCR, NSFR, brokered deposits, resolution plans
- Interest-rate risk: annual IRR Statistics Report, EVE/NII stress
- Credit risk: CRE concentration, leveraged lending, shared national
  credits (SNC), allowance for credit losses CECL
- Market risk: fundamental review of trading book (FRTB)
- Operational risk: third-party risk mgmt, model risk mgmt, AI use
- BSA/AML: customer due diligence, beneficial ownership, sanctions
- Consumer compliance: CRA, fair lending, flood disaster, SCRA
- Digital assets: stablecoin reserves, custody, crypto activities
- Climate: heightened governance + scenario analysis
- Cybersecurity: authentication, threat intel, incident notification

Every OCC bulletin has direct equity-catalyst lineage:
- Capital rules → JPM/BAC/WFC/C/USB/PNC/TFC G-SIB+large-bank capital
- CBLR relief → regional ZION/CFG/HBAN/KEY/MTB/RF/FITB community banks
- CRE concentration → CRE-heavy WAL/CMA/SBNY/SI + mREIT NRZ/PMT
- Interest-rate risk → bank NIM compression BK/STT/NTRS custody
- BSA/AML → HSBC/DB ex-US + DB-flagged USB/TFC
- Third-party risk → fintech partners SOFI/UPST/AFRM bank partnerships
- Crypto activities → COIN/HOOD + GS/MS/JPM custody rollout
- Model risk → CCAR stress test + AI/ML model governance
- Consumer compliance → fair-lending redlining CRA
- Climate → XOM/CVX/OXY + coal-exposed JPM/BAC loan book

Distinct from build_fdic_banking.py (FDIC state banks), build_cfpb.py
(consumer finance), build_fed_speeches.py (FRB monetary),
build_fsb_stability.py (FSB global), build_bis_dollar.py (BIS) —
OCC is the **national bank prudential** layer with direct examiner
enforcement authority over ~1,300 national banks.

Output: occ.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.occ.gov/rss/occ_bulletins.xml"
OUT = pathlib.Path(__file__).resolve().parent / "occ.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


CLASSIFIER = [
    ("capital_basel_iii",    re.compile(r"\b(capital rule|Basel\b|leverage ratio|\bCBLR\b|community bank leverage|G-SIB\b|risk-based capital|Tier [12]|SA-CCR|stress capital buffer|SCB\b)\b", re.I)),
    ("liquidity_lcr_nsfr",   re.compile(r"\b(liquidity\b|\bLCR\b|\bNSFR\b|liquidity coverage|net stable funding|brokered deposit|deposit insurance|resolution plan)\b", re.I)),
    ("interest_rate_risk",   re.compile(r"\b(interest rate risk|\bIRR\b|IRR Statistics|EVE\b|NII\b|net interest income|duration gap|yield curve risk|rate sensitivity)\b", re.I)),
    ("cre_concentration",    re.compile(r"\b(commercial real estate|\bCRE\b|office loan|multifamily\b|construction loan|land loan|concentration risk|acquisition development)\b", re.I)),
    ("credit_risk_cecl",     re.compile(r"\b(credit risk|\bCECL\b|allowance for credit|allowance for loan|ACL\b|ALLL\b|loan loss|charge-off|nonperforming|classified asset)\b", re.I)),
    ("leveraged_lending",    re.compile(r"\b(leveraged lending|leveraged loan|LBO\b|high yield\b|CLO\b|syndicated loan|SNC\b|shared national credit)\b", re.I)),
    ("market_risk_frtb",     re.compile(r"\b(market risk|\bFRTB\b|fundamental review of trading|VaR\b|value at risk|trading book|market risk rule)\b", re.I)),
    ("bsa_aml_sanctions",    re.compile(r"\b(BSA\b|Bank Secrecy Act|\bAML\b|anti.?money laundering|customer due diligence|\bCDD\b|beneficial ownership|sanctions\b|\bOFAC\b|suspicious activity|SAR\b|FinCEN\b)\b", re.I)),
    ("third_party_risk",     re.compile(r"\b(third.?party risk|vendor risk|outsourcing\b|fintech partnership|third-party service provider|\bTPRM\b|interagency guidance third-party)\b", re.I)),
    ("model_risk_mgmt",      re.compile(r"\b(model risk|model validation|model governance|\bMRM\b|model inventory|SR 11-7|SR 23|quantitative model|AI governance|machine learning model)\b", re.I)),
    ("crypto_digital_asset", re.compile(r"\b(crypto\b|digital asset|stablecoin\b|blockchain\b|distributed ledger|custody\b digital|cryptocurrency|bitcoin\b|interpretive letter.*(?:crypto|digital))\b", re.I)),
    ("cra_fair_lending",     re.compile(r"\b(Community Reinvestment|\bCRA\b|fair lending|redlining\b|disparate impact|Regulation B\b|ECOA\b|Equal Credit Opportunity|\bHMDA\b)\b", re.I)),
    ("consumer_compliance",  re.compile(r"\b(consumer compliance|Regulation Z\b|TILA\b|RESPA\b|Regulation X\b|Regulation E\b|EFTA\b|UDAAP\b|overdraft\b|junk fee)\b", re.I)),
    ("cybersecurity_ops",    re.compile(r"\b(cybersecurity\b|cyber risk|incident notification|computer.security.incident|authentication\b|phishing\b|ransomware\b|business continuity)\b", re.I)),
    ("climate_esg_occ",      re.compile(r"\b(climate\b|ESG\b|environmental\b|climate-related financial risk|greenhouse gas|transition risk|physical risk|scenario analysis)\b", re.I)),
    ("operational_risk",     re.compile(r"\b(operational risk|operational resilience|business continuity|disaster recovery|critical operation|resilience program)\b", re.I)),
    ("merger_application",   re.compile(r"\b(merger\b|acquisition\b|branch application|change of control|\bCBCA\b|bank holding company|de novo bank|national bank charter)\b", re.I)),
    ("supervisory_exam",     re.compile(r"\b(supervisory\b|examination\b|\bMRA\b|matter requiring attention|CAMELS\b|composite rating|examiner\b|Horizontal review)\b", re.I)),
    ("enforcement_action",   re.compile(r"\b(enforcement action|cease and desist|consent order|civil money penalty|\bCMP\b|formal agreement|removal action|prohibition order)\b", re.I)),
    ("leadership_occ",       re.compile(r"\b(Comptroller\b|Acting Comptroller|Senior Deputy|Hsu\b|Gould\b|nominat|confirmed\b|appointed\b|stepping down|resign\b)\b", re.I)),
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
    return "bank_supervisory"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("windows-1252", errors="replace")
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
        print(f"occ: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"occ: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"occ: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
