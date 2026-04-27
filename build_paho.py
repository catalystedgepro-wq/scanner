#!/usr/bin/env python3
"""
build_paho.py — Pan American Health Organization (PAHO) news tape.

Source: https://www.paho.org/en/rss.xml
        Drupal RSS 2.0 w/ dc:creator + pubDate RFC2822 + HTML-escaped
        description (no <category> tags).

PAHO is WHO's regional office for the Americas (AMR) — the authoritative
public-health voice for 35 member states covering North/Central/South
America + Caribbean. Distinct from global WHO (build_who_health.py) which
covers Geneva headquarters; PAHO owns regional outbreak declarations,
vaccination campaigns, Venezuela/Haiti humanitarian medicine, Latin
America NCD surveillance, and Americas-specific disease burden.

Coverage kinds:
- vaccine_immunization (measles, MMR, polio, HPV, yellow fever, flu)
- outbreak_epidemic (dengue, chikungunya, zika, cholera, malaria)
- mpox_orthopox (monkeypox, smallpox, mpox)
- covid_respiratory (SARS-CoV-2, influenza, RSV)
- hiv_aids_sti (HIV, AIDS, STI, syphilis)
- maternal_child_health (maternal mortality, newborn, breastfeeding)
- noncommunicable_disease (diabetes, cardiovascular, cancer, obesity)
- mental_health_addiction (opioid, alcohol, suicide, mental health)
- antimicrobial_resistance (AMR, antibiotics)
- vector_borne_disease (mosquito, aedes, triatomine)
- tuberculosis_tb (TB, MDR-TB, latent)
- food_safety_nutrition (food safety, malnutrition, obesity)
- climate_health (climate change, air quality, heat)
- disaster_humanitarian (earthquake, hurricane, Venezuela, Haiti)
- health_system_strengthening (primary care, UHC, workforce)
- digital_health_telemedicine
- tobacco_harm_reduction
- road_safety_injury
- indigenous_health
- leadership_paho (Director, confirmation, Etienne, Barbosa)

Every outbreak/vaccine signal has direct equity-catalyst lineage:
- Measles/MMR outbreaks → MRK/PFE/GSK (MMR) + MRNA vaccines
- Mpox declarations → BVNRY (Jynneos) + EBS (Emergent BioSolutions)
- Dengue → MRK (Dengvaxia) + TAK (Qdenga) + VLA (TAK-003)
- Chikungunya → VLA (Valneva Ixchiq) + BVRS (Bavarian Nordic)
- Yellow fever → SNY + BVRS + EBS
- HIV PrEP/ART → GILD (Descovy/Truvada) + VRTX + VIIV/GSK (long-acting)
- NCD/GLP-1 → LLY (Zepbound) + NVO (Wegovy) Latin-America uptake
- AMR → MRK/PFE antibiotics + SVRA/INSM/MRNS novel antibiotics
- RSV maternal/infant → PFE (Abrysvo) + SNY (Beyfortus) + GSK (Arexvy)
- Tobacco control → PM/MO/BTI + harm-reduction vapor
- Venezuelan/Haitian humanitarian → UNH/HCA/TEVA generic supply

Distinct from build_who_health.py (WHO Geneva global),
build_cdc_newsroom.py (US-only CDC), build_fda_drug_approval.py,
build_fda_enforcement.py — PAHO covers the **Americas regional**
layer (Latin America + Caribbean health emergencies) that drives
pharma/vaccine guidance distinct from both WHO-global + CDC-US.

Output: paho.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.paho.org/en/rss.xml"
OUT = pathlib.Path(__file__).resolve().parent / "paho.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


CLASSIFIER = [
    ("mpox_orthopox",          re.compile(r"\b(mpox\b|monkeypox\b|orthopox|smallpox\b|Jynneos\b)\b", re.I)),
    ("vaccine_immunization",   re.compile(r"\b(vaccin\w*|immuniz\w*|measles\b|\bMMR\b|polio\b|\bHPV\b|yellow fever\b|influenza vaccine|flu vaccine|pertussis\b|diphtheria\b|tetanus\b|rubella\b|varicella\b|rotavirus\b|pneumococcal\b|meningococcal\b)\b", re.I)),
    ("outbreak_epidemic",      re.compile(r"\b(dengue\b|chikungunya\b|zika\b|cholera\b|malaria\b|ebola\b|oropouche\b|marburg\b|lassa\b|plague\b|epidemic\b|outbreak\b|pandemic\b|\bPHEIC\b|public health emergency)\b", re.I)),
    ("covid_respiratory",      re.compile(r"\b(COVID\b|coronavirus\b|SARS-CoV-2|long COVID|\bRSV\b|respiratory syncytial|influenza\b|\bflu\b|H5N1\b|avian flu|bird flu)\b", re.I)),
    ("hiv_aids_sti",           re.compile(r"\b(\bHIV\b|\bAIDS\b|sexually transmitted|\bSTI\b|\bPrEP\b|antiretroviral\b|\bART\b|syphilis\b|gonorrhea\b|chlamydia\b)\b", re.I)),
    ("tuberculosis_tb",        re.compile(r"\b(tuberculosis\b|\bTB\b|\bMDR-TB\b|latent TB|drug-resistant TB)\b", re.I)),
    ("maternal_child_health",  re.compile(r"\b(maternal\b|newborn\b|neonatal\b|breastfeeding\b|stillbirth\b|infant mortality|child health|pediatric\b|adolescent health|reproductive health)\b", re.I)),
    ("noncommunicable_disease",re.compile(r"\b(diabetes\b|cardiovascular\b|cancer\b|obesity\b|hypertension\b|stroke\b|\bNCD\b|noncommunicable|non-communicable|chronic disease)\b", re.I)),
    ("mental_health_addiction",re.compile(r"\b(mental health\b|depression\b|suicide\b|opioid\b|overdose\b|substance use\b|addiction\b|alcohol\b|dependence\b)\b", re.I)),
    ("antimicrobial_resistance",re.compile(r"\b(antimicrobial resistance|\bAMR\b|antibiotic\w*|drug resistance|resistant bacteria|superbug)\b", re.I)),
    ("vector_borne_disease",   re.compile(r"\b(mosquito\b|aedes\b|anopheles\b|triatomine\b|vector-borne|vector control|Chagas\b|leishmaniasis\b)\b", re.I)),
    ("food_safety_nutrition",  re.compile(r"\b(food safety|foodborne\b|nutrition\b|malnutrition\b|undernutrition\b|food insecurity|anemia\b|micronutrient\b|ultra-processed)\b", re.I)),
    ("climate_health",         re.compile(r"\b(climate change\b|air quality\b|air pollution\b|heat wave\b|extreme heat|environmental health)\b", re.I)),
    ("disaster_humanitarian",  re.compile(r"\b(earthquake\b|hurricane\b|flood\b|Venezuela\b|Venezuelan\b|Haiti\b|Haitian\b|migrant\b|refugee\b|humanitarian\b|disaster\b|emergency response)\b", re.I)),
    ("tobacco_harm_reduction", re.compile(r"\b(tobacco\b|smoking\b|cigarette\b|\be-cigarette\b|vaping\b|nicotine\b)\b", re.I)),
    ("road_safety_injury",     re.compile(r"\b(road safety|traffic injury|road traffic|violence prevention|drowning\b)\b", re.I)),
    ("indigenous_health",      re.compile(r"\b(indigenous\b|ethnic minorit|Afrodescendant\b|tribal health|native population)\b", re.I)),
    ("digital_health",         re.compile(r"\b(digital health\b|telemedicine\b|telehealth\b|eHealth\b|mHealth\b|health informatics|electronic health record|\bEHR\b|artificial intelligence|\bAI\b)\b", re.I)),
    ("leadership_paho",        re.compile(r"\b(PAHO Director\b|Director of PAHO|Barbosa\b|Etienne\b|nomination\b|confirm\w*|Deputy Director)\b", re.I)),
    ("health_system",          re.compile(r"\b(primary care\b|health system|health workforce|universal health|\bUHC\b|health financing|health coverage|essential medicines)\b", re.I)),
    ("public_health_general",  re.compile(r"\b(public health|health policy|health promotion|disease prevention|surveillance\b|epidemiolog\w*|health equity|social determinants)\b", re.I)),
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
    return "paho_news"


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
        print(f"paho: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"paho: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"paho: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
