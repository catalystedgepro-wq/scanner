#!/usr/bin/env python3
"""
build_nsf_news.py — NSF (National Science Foundation) news tape.

Source: https://www.nsf.gov/rss/rss_www_news.xml (RSS 2.0 with dc:creator)

NSF is the $8B+/yr federal grant-making agency for non-medical basic research.
Every release telegraphs:
- university research dollars → spin-offs
- critical minerals / semiconductor / quantum / AI initiatives → CHIPS Act rebid tape
- AI-Ready America + TechAccess grants → NVDA/AMD/INTC/IBM/GOOGL/MSFT/PLTR/CRWD
- Graduate Research Fellowships → pipeline for NVDA/TSM/AMD/AVGO engineers
- Critical-minerals tech-metal transformation → MP/LAC/UUUU/LYC/ALB
- Quantum science → IBM/IONQ/RGTI/QUBT/ARQQ/HON
- NSF Engines regional innovation hubs → place-based economic tape
- Engineering directorates (ENG/CISE/EDU/SBE/MPS/GEO/BIO) → sector-specific research flow

Distinct from build_nih_grants.py (NIH biomedical), build_darpa.py (DARPA defense),
build_doe_news.py (DOE applied-energy). Fills NSF basic-research gap.

Output: nsf_news.csv — filed_utc, kind, title, link, creator, summary.

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

URL = "https://www.nsf.gov/rss/rss_www_news.xml"
OUT = pathlib.Path(__file__).resolve().parent / "nsf_news.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered kind rules (first-match-wins). Specific before broad.
KIND_RULES = [
    ("ai_initiative",     re.compile(r"\b(artificial intelligence|ai-ready|ai ready|machine learning|techaccess|ai institute|ai research|generative ai|llm|ai literacy|ai workforce)\b", re.I)),
    ("quantum",           re.compile(r"\b(quantum computing|quantum information|quantum science|quantum network|quantum sensor|quantum materials|qis|q-leap|quantum workforce)\b", re.I)),
    ("critical_minerals", re.compile(r"\b(critical minerals?|rare earth|tech metal|strategic minerals?|lithium|cobalt|nickel|graphite|manganese|domestic supply chain|mineral independence|metal transformation)\b", re.I)),
    ("semiconductor",     re.compile(r"\b(semiconductor|microelectronics|chip fabrication|chips and science|chips act|photonic integrated|compound semi|gaas|gan|sic|node process|foundry research)\b", re.I)),
    ("biotech_research",  re.compile(r"\b(synthetic biology|bioeconomy|genomic|biomanufacturing|crispr|gene editing|molecular engineering|protein design|biotechnology|cell biology)\b", re.I)),
    ("climate_earth",     re.compile(r"\b(climate|sea level|permafrost|arctic|antarctic|ocean observatory|coral|ice sheet|atmospheric|extreme weather|earth system|sea ice|polar science)\b", re.I)),
    ("clean_energy",      re.compile(r"\b(clean energy|solar cell|battery chemistry|grid research|hydrogen|fusion|geothermal|carbon capture|energy storage|photovoltaic research)\b", re.I)),
    ("space_astronomy",   re.compile(r"\b(telescope|observatory|astronomy|astrophysics|dark matter|dark energy|gravitational wave|ligo|exoplanet|black hole|cosmology|spacetime|rubin observatory|alma|noirlab)\b", re.I)),
    ("engines_regional",  re.compile(r"\b(nsf engines|regional innovation|place-based|innovation ecosystem|tech hub|regional tech|corridor|cluster award)\b", re.I)),
    ("workforce_education", re.compile(r"\b(graduate research fellowship|grfp|workforce|k-12|k12|stem education|teacher|professional development|cs teachers|scholarship|undergraduate research|experiential learning|broadening participation)\b", re.I)),
    ("cyber_security",    re.compile(r"\b(cybersecurity|cyber physical|secure and trustworthy|satc\b|post-quantum|cryptography research|zero trust|software assurance)\b", re.I)),
    ("materials_science", re.compile(r"\b(materials genome|advanced materials|nanomaterials|metamaterials|composite materials|topological|superconduct|graphene|polymer|ceramic)\b", re.I)),
    ("funding_opportunity", re.compile(r"\b(funding opportunity|solicitation|dear colleague|request for proposals|rfp\b|notice of funding|program announcement|seeking proposals|invites proposals)\b", re.I)),
    ("award_announcement", re.compile(r"\b(announces.*award|awards \$|awards more than|million (?:in|to)|awarded to|selected recipient|winners of|winning teams|finalists)\b", re.I)),
    ("partnership",       re.compile(r"\b(partnership with|cooperative agreement|public.?private|industry partner|memorandum of understanding|mou with|joint initiative|multi-agency)\b", re.I)),
    ("leadership",        re.compile(r"\b(director of|deputy director|names|appoints|nominated|assistant director|confirmed as|secretary|ostp|national science board)\b", re.I)),
    ("podcast",           re.compile(r"\b(podcast)\b", re.I)),
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
    for name, pat in KIND_RULES:
        if pat.search(hay):
            return name
    return "press"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        creator = extract_tag(raw, "dc:creator")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary)
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": title[:240],
            "link": link,
            "creator": creator,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"nsf_news: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "kind", "title", "link", "creator", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"nsf_news: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"nsf_news: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
