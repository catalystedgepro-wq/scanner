#!/usr/bin/env python3
"""
build_ustr.py — Office of the U.S. Trade Representative (USTR) tape.

Source: https://ustr.gov/rss.xml
        Drupal-rendered RSS 2.0 w/ dc:creator + pubDate RFC2822 + HTML-escaped description.

USTR is the **cabinet-level office leading U.S. bilateral and
multilateral trade negotiations**. This feed carries the live pipeline
of Section 301/232/201 tariff actions, USMCA joint-review cycles, WTO
dispute filings, China tariff schedules (Lists 1-4 + Section 301
exclusions), bilateral free-trade agreements (UK, EU, Japan, India,
Vietnam, Mexico, Kenya, Taiwan 21st Century Trade), supply-chain and
critical-minerals policy (IRA + CHIPS conditioning), digital-trade
frameworks, IP protection (Special 301 Report watch-list + out-of-cycle
reviews), labor-rights enforcement (USMCA rapid-response mechanism),
Generalized System of Preferences (GSP) renewals, forced-labor
enforcement (UFLPA Entity List + CBP WRO), and trade-adjustment
assistance. Every USTR release has direct equity catalysts:
- Section 301/232 tariff announcements → NUE/STLD/CLF/X steel, AA/CENX
  aluminum, GM/F/STLA/TM/HMC autos, SHW/RPM paint ingredients.
- Semiconductor export controls → NVDA/AMD/INTC/TSM/SMCI/AMAT/LRCX/KLAC.
- Textile tariffs → GIL/HBI/PVH/VFC/RL/UA/NKE/LULU offshore exposure.
- Agriculture retaliation → ADM/BG/CORN/WEAT/DE/AGCO farm-belt cycle.
- Critical minerals → ALB/LAC/SQM/MP/FCX/NEM/GOLD/HL + EV TSLA/RIVN/LCID.
- Solar (Section 201) → FSLR/ENPH/SEDG/RUN domestic vs JKS/CSIQ import.
- UFLPA Xinjiang enforcement → VSCO/HBI/HAS cotton + polysilicon FSLR.
- WTO disputes → panel rulings 6-18mo ahead of tariff reversal.

Distinct from build_federalreserve.py (monetary), build_fed_speeches.py
(Fed speakers), build_bls_jobs.py (labor), build_bea_gdp.py (national
accounts), build_imf_weo.py (IMF) — USTR is the **trade-policy frontier**
feed and has no current coverage in the pipeline.

Output: ustr.csv — filed_utc, kind, title, link, summary.

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

URL = "https://ustr.gov/rss.xml"
OUT = pathlib.Path(__file__).resolve().parent / "ustr.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


CLASSIFIER = [
    ("section_301_china",    re.compile(r"\b(Section 301\b|301 tariff|301 list|China tariff|tariff on Chinese|PRC goods|PRC product|exclusion list|exclusion process)\b", re.I)),
    ("section_232_steel",    re.compile(r"\b(Section 232\b|steel tariff|aluminum tariff|steel and aluminum|national security tariff|steel import|aluminum import)\b", re.I)),
    ("section_201_solar",    re.compile(r"\b(Section 201\b|safeguard\b|solar panel|solar cell|crystalline silicon|CSPV\b|imported solar|washing machine safeguard)\b", re.I)),
    ("uflpa_forced_labor",   re.compile(r"\b(UFLPA\b|Uyghur\b|Xinjiang\b|forced labor|WRO\b|withhold release|entity list|slave labor|supply chain tracing)\b", re.I)),
    ("wto_dispute",          re.compile(r"\b(\bWTO\b|World Trade Organization|dispute settlement|DSB\b|panel ruling|Appellate Body|consultation request|notification\b)\b", re.I)),
    ("usmca_mexico_canada",  re.compile(r"\b(USMCA\b|United States.?Mexico.?Canada|NAFTA\b|rapid response|\bRRM\b|rules of origin|auto rules|North American)\b", re.I)),
    ("china_bilateral",      re.compile(r"\b(China\b|Chinese\b|PRC\b|Beijing\b|phase one|bilateral with China|US-China trade|xi jinping)\b", re.I)),
    ("uk_bilateral",         re.compile(r"\b(United Kingdom|\bUK\b|Britain\b|British\b|London\b|UK-US trade|UK trade)\b", re.I)),
    ("eu_bilateral",         re.compile(r"\b(European Union|\bEU\b|Brussels\b|EU-US\b|transatlantic|TTC\b|Airbus\b|Boeing dispute|EU tariff)\b", re.I)),
    ("japan_korea_apec",     re.compile(r"\b(Japan\b|Tokyo\b|South Korea|Korea\b|Seoul\b|APEC\b|IPEF\b|Indo-Pacific|digital trade Japan)\b", re.I)),
    ("india_bilateral",      re.compile(r"\b(India\b|New Delhi|bilateral with India|India trade|Modi\b|GSP India)\b", re.I)),
    ("vietnam_asean",        re.compile(r"\b(Vietnam\b|Hanoi\b|ASEAN\b|Philippines\b|Indonesia\b|Malaysia\b|Thailand\b|Singapore\b|Cambodia\b)\b", re.I)),
    ("latam_bilateral",      re.compile(r"\b(Brazil\b|Argentina\b|Colombia\b|Peru\b|Chile\b|Ecuador\b|Honduras\b|Guatemala\b|CAFTA\b|Mercosur\b)\b", re.I)),
    ("africa_agoa",          re.compile(r"\b(Africa\b|AGOA\b|Growth and Opportunity|Kenya\b|Nigeria\b|South Africa\b|Ethiopia\b|Ghana\b)\b", re.I)),
    ("digital_trade",        re.compile(r"\b(digital trade|e-commerce\b|data flow|cross-border data|cloud services tariff|digital services tax|DSA\b|DMA\b)\b", re.I)),
    ("ip_special_301",       re.compile(r"\b(Special 301\b|intellectual property|\bIP\b protection|counterfeit\b|piracy\b|trade secret theft|patent dispute|notorious market)\b", re.I)),
    ("ag_retaliation",       re.compile(r"\b(agricultural tariff|soybean\b|corn\b|wheat\b|beef\b|pork\b|poultry\b|dairy\b|farm retaliation|agricultural export)\b", re.I)),
    ("critical_minerals",    re.compile(r"\b(critical minerals|rare earth|lithium\b|cobalt\b|nickel\b|graphite\b|IRA\b|CHIPS\b|semiconductor tariff|EV tariff)\b", re.I)),
    ("gsp_renewal",          re.compile(r"\b(Generalized System|\bGSP\b|preference program|duty.?free|eligibility review|MTB\b|miscellaneous tariff)\b", re.I)),
    ("leadership_ustr",      re.compile(r"\b(Ambassador\b|Trade Representative|confirmed\b|nominated\b|Deputy USTR|Chief Agricultural|Assistant USTR|Greer\b|Tai\b|Lighthizer\b)\b", re.I)),
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


def classify(title: str, summary: str) -> str:
    hay = f"{title}  {summary}"
    for name, pat in CLASSIFIER:
        if pat.search(hay):
            return name
    return "trade_policy"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary)
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
        print(f"ustr: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"ustr: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"ustr: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
