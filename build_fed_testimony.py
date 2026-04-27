#!/usr/bin/env python3
"""
build_fed_testimony.py — Federal Reserve Board congressional testimony tape.

Source: https://www.federalreserve.gov/feeds/testimony.xml
        UTF-8 BOM RSS 2.0 w/ CDATA + pubDate RFC2822 + single category.

Fed testimony is the **highest-fidelity real-time monetary + supervisory
policy signal** the Board produces — Chair, Vice Chair, Governors, and
supervisory staff testifying before House Financial Services, Senate
Banking, Joint Economic Committee, House Ways & Means, and
subcommittees (Digital Assets/Fintech/AI, Consumer Protection,
Financial Institutions, Housing). Every testimony has a prepared
statement + live Q&A that often moves markets intraday — FOMC rate-path
signals, stress-test severity hints, Basel III endgame calibration,
CBDC/stablecoin framework, fintech bank-partnership guidance, climate
scenario pilots, emergency-lending 13(3) defense, and consumer
compliance rule-making.

Coverage kinds:
- monetary_policy_report (Semiannual Monetary Policy Report = HFSC/SB)
- digital_assets_fintech (DeFi, stablecoin, AI, tokenization)
- regulation_innovation (Reg Z/B/E/X rule-making testimony)
- bank_supervision (Basel, CCAR, large-bank capital)
- ccar_stress_test (stress test design + severity)
- community_banking (CRA, CBLR, tailoring rule)
- consumer_protection (TILA, HMDA, UDAAP, overdraft)
- cyber_resilience (cyber risk, operational resilience)
- climate_finance (climate-related financial risk, scenario)
- housing_mortgage (GSE, mortgage credit, MBS)
- labor_inflation (employment, inflation, price stability)
- liquidity_resolution (LCR, NSFR, resolution plan)
- gse_housing_agency (Fannie/Freddie, FHFA coordination)
- deposit_insurance (FDIC, deposit insurance fund)
- emergency_lending (13(3), BTFP, PDCF defense)
- debt_ceiling_fiscal (Treasury debt ceiling, fiscal)
- international_cooperation (IMF, FSB, G20, BIS)
- appropriations_oversight (Fed budget, audit, GAO)
- dodd_frank_reform (Dodd-Frank, EGRRCPA tailoring)
- confirmation_hearing (Senate Banking confirmation)

Every testimony has direct equity-catalyst lineage:
- Powell Semiannual MPR → 2s10s + TLT/IEF + XLF/KRE NIM + SPY
- Digital assets testimony → COIN/HOOD/MSTR + CRCL/USDC
- CCAR testimony → JPM/BAC/C/WFC/GS/MS buyback capacity
- CBDC/FedNow → FIS/FISV/GPN/V/MA + SOFI/AFRM instant
- Climate scenario → JPM/BAC/WFC/C loan-book transition
- Emergency 13(3) → regional WAL/CMA/SI/SBNY liquidity defense
- Housing mortgage → UWMC/RKT/LDI + NLY/AGNC mREIT + MBB
- Confirmation → contract-unlock halo + rate-path recalibration

Distinct from build_fed_press.py (press_all.xml announcements),
build_fed_speeches.py (speeches.xml), build_fed_enforcement.py
(press_enforcement.xml), build_fed_balance_sheet.py (FRED),
build_federalreserve.py (Treasury/H.15 rates) — testimony.xml is the
**congressional-hearing prepared-statement** layer, which carries
more legal + forward-looking weight than informal speeches.

Output: fed_testimony.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.federalreserve.gov/feeds/testimony.xml"
OUT = pathlib.Path(__file__).resolve().parent / "fed_testimony.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200

SPEAKER_SLUG = re.compile(r"/testimony/([a-z]+)\d{8}")


CLASSIFIER = [
    ("monetary_policy_report", re.compile(r"\b(Semiannual Monetary Policy|Monetary Policy Report|Humphrey.?Hawkins|monetary policy testimony|state of the economy|monetary policy outlook)\b", re.I)),
    ("digital_assets_fintech", re.compile(r"\b(digital asset|stablecoin\b|tokeniz|crypto\b|cryptocurrency|blockchain\b|distributed ledger|DeFi\b|fintech\b|artificial intelligence|\bAI\b|machine learning|novel activit)\b", re.I)),
    ("cbdc_payment_innov",     re.compile(r"\b(central bank digital currency|\bCBDC\b|FedNow\b|Fedwire\b|FedACH\b|instant payment|real-time payment|payment system|retail payment)\b", re.I)),
    ("ccar_stress_test",       re.compile(r"\b(CCAR\b|DFAST\b|stress test|comprehensive capital|stress capital buffer|\bSCB\b|capital plan)\b", re.I)),
    ("bank_supervision_test",  re.compile(r"\b(Basel III\b|Basel endgame|G-SIB\b|global systemically important|bank supervision|large bank|risk-based capital|FRTB\b|SA-CCR|tailoring rule|Category I{1,4}\b)\b", re.I)),
    ("community_banking_test", re.compile(r"\b(community bank\b|Community Bank Leverage|\bCBLR\b|small bank|regional bank\b|mid-size\b|de novo\b|bank holding company\b)\b", re.I)),
    ("consumer_protection",    re.compile(r"\b(consumer protection|Regulation Z\b|TILA\b|Regulation B\b|\bECOA\b|Regulation E\b|\bEFTA\b|Regulation X\b|\bRESPA\b|\bHMDA\b|\bUDAAP\b|overdraft\b|junk fee)\b", re.I)),
    ("cra_fair_lending_test",  re.compile(r"\b(Community Reinvestment\b|\bCRA\b|fair lending|redlining\b|disparate impact|underserved)\b", re.I)),
    ("cyber_resilience_test",  re.compile(r"\b(cybersecurity\b|cyber risk|operational resilience|business continuity|incident notification|authentication\b|ransomware\b)\b", re.I)),
    ("climate_finance_test",   re.compile(r"\b(climate\b|climate-related financial|pilot climate scenario|transition risk|physical risk|greenhouse gas)\b", re.I)),
    ("housing_mortgage_test",  re.compile(r"\b(housing\b|mortgage\b|\bGSE\b|Fannie Mae|Freddie Mac|\bFHFA\b|single-family\b|multifamily\b|\bMBS\b|home equity)\b", re.I)),
    ("labor_inflation_test",   re.compile(r"\b(labor market|employment\b|unemployment\b|jobless\b|inflation\b|price stability|dual mandate|wage growth|Phillips curve)\b", re.I)),
    ("liquidity_resolution",   re.compile(r"\b(\bLCR\b|\bNSFR\b|liquidity coverage|net stable funding|resolution plan|living will|Title II|orderly liquidation)\b", re.I)),
    ("deposit_insurance_test", re.compile(r"\b(deposit insurance|\bFDIC\b|uninsured deposit|deposit insurance fund|\bDIF\b|Title I\b)\b", re.I)),
    ("emergency_lending_test", re.compile(r"\b(13\(3\)|emergency lending|Bank Term Funding|\bBTFP\b|Primary Dealer Credit|\bPDCF\b|Section 13|liquidity facility|lender of last resort)\b", re.I)),
    ("debt_ceiling_fiscal",    re.compile(r"\b(debt ceiling|debt limit|Treasury General Account|\bTGA\b|extraordinary measures|X-date|fiscal\b|appropriation\b)\b", re.I)),
    ("international_coop",     re.compile(r"\b(International Monetary Fund|\bIMF\b|Financial Stability Board|\bFSB\b|\bG20\b|G-20|\bBIS\b|Bank for International|Basel Committee|cross-border\b|global financial)\b", re.I)),
    ("dodd_frank_reform",      re.compile(r"\b(Dodd-Frank\b|Dodd Frank|\bEGRRCPA\b|Regulatory Relief|living will|Volcker\b|SIFI\b|systemically important)\b", re.I)),
    ("confirmation_hearing",   re.compile(r"\b(nomination\b|confirm\w*|renomination|Vice Chair\b|\bChairman\b|Senate Banking\b|Senate Committee)\b", re.I)),
    ("appropriations_audit",   re.compile(r"\b(appropriation\b|audit\b|\bGAO\b|\bOIG\b|Board budget|oversight\b|\bIG\b|transparency\b)\b", re.I)),
    ("regulation_innovation",  re.compile(r"\b(regulation\b|innovation\b|rule-making|proposed rule|final rule|regulatory\b|supervision\b)\b", re.I)),
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


def extract_speaker(link: str) -> str:
    m = SPEAKER_SLUG.search(link)
    return m.group(1) if m else ""


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


def classify(title: str, summary: str, speaker: str) -> str:
    hay = f"{title}  {summary}  {speaker}"
    for name, pat in CLASSIFIER:
        if pat.search(hay):
            return name
    if speaker in ("powell", "clarida", "brainard", "jefferson"):
        return "monetary_policy_report"
    return "fed_testimony"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8-sig", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        speaker = extract_speaker(link)
        kind = classify(title, summary, speaker)
        display_title = f"[{speaker}] {title}" if speaker else title
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": display_title[:240],
            "link": link,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"fed_testimony: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"fed_testimony: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"fed_testimony: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
