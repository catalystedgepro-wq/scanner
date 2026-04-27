#!/usr/bin/env python3
"""
build_eu_commission.py — EU Commission Presscorner press-release tape.

Source: https://ec.europa.eu/commission/presscorner/api/rss?service=press-release&lang=en
        RSS 2.0 with <category>POLICY_AREA=XXX</category> self-tagged taxonomy.

The European Commission Presscorner is the flagship EU executive press firehose:
- Speeches by Commissioners (Kubilius/Defence, Šefčovič/Trade, von der Leyen,
  Séjourné, Cafiero de Raho, Virkkunen, Hoekstra, Dombrovskis, Valean)
- Daily News bundles (MEX_YY_NNN) aggregating 10-20 announcements
- Information Packages (IP_YY_NNN) = binding policy releases
- Speech releases (SPEECH_YY_NNN) = commissioner-level signalling
- Mnemo releases (MEMO_YY_NNN) = Q&A briefings accompanying big packages

Built-in POLICY_AREA taxonomy used verbatim as kind when present; fallback
classifier on title+description for untagged speeches/daily-news bundles.

Distinct from existing esma_eu.py (ESMA markets), eba_banking.py (EBA bank reg),
ecb_press.py (ECB monetary), eu_indpro.py + eu_retail.py (Eurostat numerics) —
this is the EU executive policy/trade/defence/competition/digital-markets tape.

Output: eu_commission.csv — filed_utc, kind, title, link, policy_area, summary.

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

URL = "https://ec.europa.eu/commission/presscorner/api/rss?service=press-release&lang=en"
OUT = pathlib.Path(__file__).resolve().parent / "eu_commission.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# POLICY_AREA tokens emitted by the API, normalized to snake_case kinds.
POLICY_AREA_MAP = {
    "DEFENCE":      "defence",
    "TRADE":        "trade",
    "CLIMA":        "climate",
    "ENER":         "energy",
    "ENERGY":       "energy",
    "AGRI":         "agriculture",
    "DIGITAL":      "digital",
    "CNECT":        "digital",
    "ECON":         "economic_policy",
    "FISMA":        "financial_markets",
    "FINANCE":      "financial_markets",
    "TAXUD":        "tax_customs",
    "TAX":          "tax_customs",
    "CUST":         "tax_customs",
    "COMP":         "competition",
    "COMPETITION":  "competition",
    "SANTE":        "health_food",
    "HEALTH":       "health_food",
    "ENV":          "environment",
    "ENVIRONMENT":  "environment",
    "MARE":         "maritime",
    "EMPL":         "employment",
    "EMPLOYMENT":   "employment",
    "TRAN":         "transport",
    "MOVE":         "transport",
    "TRANSPORT":    "transport",
    "REGIO":        "regional_policy",
    "RTD":          "research",
    "RESEARCH":     "research",
    "INTPA":        "intl_partners",
    "NEAR":         "enlargement",
    "ENLARGEMENT":  "enlargement",
    "ECHO":         "humanitarian",
    "JUST":         "justice",
    "JUSTICE":      "justice",
    "HOME":         "home_affairs",
    "SECURITY":     "home_affairs",
    "MIGRATION":    "migration",
    "HR":           "human_rights",
    "FPI":          "foreign_policy",
    "EEAS":         "foreign_policy",
    "GROW":         "single_market",
    "SINGLE_MARKET": "single_market",
    "BUDG":         "budget",
    "BUDGET":       "budget",
    "REFORM":       "reform",
    "EAC":          "education_culture",
    "CULTURE":      "education_culture",
    "CLIMATE":      "climate",
    "ECFIN":        "economic_policy",
    "GENINFO":      "daily_news",
    "INSTINFO":     "institutional",
    "DIGAG":        "digital",
    "CLIMACTION":   "climate",
    "AGRURAL":      "agriculture",
    "MIDDLE":       "intl_partners",
    "ESAI":         "intl_partners",
    "SPORT":        "education_culture",
    "YOUTH":        "education_culture",
    "SOCIAL":       "employment",
    "GENDER":       "justice",
    "EUEAST":       "foreign_policy",
    "PEPPOL":       "digital",
}


# Fallback classifier for un-tagged items (speeches, memos, daily news bundles).
FALLBACK_RULES = [
    ("defence",          re.compile(r"\b(defence|defense|military|weapons|nato|security|arms|edip|asap|sstec|european defence)\b", re.I)),
    ("trade",            re.compile(r"\b(trade|tariff|dumping|wto|fta|cbam|safeguard|export control|trade deal|sanctions)\b", re.I)),
    ("climate",          re.compile(r"\b(climate|emission|green deal|renewable|decarboni|carbon|net zero|energy transition|electric vehicle)\b", re.I)),
    ("energy",            re.compile(r"\b(energy|gas|hydrogen|nuclear|power grid|electricity market|oil supply|lng|pipeline|repowered?eu)\b", re.I)),
    ("digital",          re.compile(r"\b(digital|artificial intelligence|ai act|platform|data act|dsa|dma|dga|gdpr|cyber|fintech|quantum|semi conductor|chips act)\b", re.I)),
    ("financial_markets", re.compile(r"\b(banking|capital markets|mifid|emir|solvency|credit rating|basel|stress test|esg disclosure|cmu|saving|investment union)\b", re.I)),
    ("competition",      re.compile(r"\b(antitrust|cartel|state aid|merger|abuse of dominant|fine of|investigation into|commitments|block(?:s|ed))\b", re.I)),
    ("economic_policy",  re.compile(r"\b(economic forecast|fiscal|budget deficit|excessive deficit|stability programme|convergence|recovery and resilience|rrf|ngeu)\b", re.I)),
    ("agriculture",      re.compile(r"\b(agriculture|cap reform|farmers?|rural development|food security|fisheries|livestock|dairy)\b", re.I)),
    ("health_food",      re.compile(r"\b(health|pharmaceutical|medicine|vaccine|disease|cancer|ema authorisation|food safety|pesticide|ehr)\b", re.I)),
    ("justice",          re.compile(r"\b(justice|rule of law|judicial|fundamental rights|corruption|anti-money launder|aml|whistleblower)\b", re.I)),
    ("humanitarian",     re.compile(r"\b(humanitarian|refugee|displaced|ukraine aid|disaster response|echo|gaza|famine|emergency assistance)\b", re.I)),
    ("enlargement",      re.compile(r"\b(enlargement|accession|ukraine membership|moldova membership|western balkans|candidate country)\b", re.I)),
    ("tax_customs",      re.compile(r"\b(tax|customs|vat|minimum tax|pillar 2|beps|transfer pricing|duty-free|carbon border)\b", re.I)),
    ("single_market",    re.compile(r"\b(single market|internal market|cross-border|services directive|goods package|professional qualifications)\b", re.I)),
    ("transport",        re.compile(r"\b(aviation|maritime|rail|transport|ten-t|emission performance|vehicle type|shipping|seafarer)\b", re.I)),
    ("intl_partners",    re.compile(r"\b(global gateway|partnership agreement|cooperation programme|development aid|global health|neighbour)\b", re.I)),
    ("speech",           re.compile(r"\b(speech by|remarks by|address by|keynote|statement by|opening remarks|welcome message)\b", re.I)),
    ("daily_news",       re.compile(r"\b(daily news|midday express|mex[_ ]\d)\b", re.I)),
    ("memo",             re.compile(r"\b(questions and answers|q&a|memo[_ ]\d|frequently asked|explanatory)\b", re.I)),
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


def extract_policy_area(body: str) -> str:
    m = re.search(r"<category[^>]*>\s*POLICY_AREA=([^<]+?)\s*</category>", body, re.S)
    if not m:
        return ""
    # Composite tags like "DIGAG,TECH" — take the first token for mapping.
    raw = m.group(1).strip().upper()
    return raw.split(",")[0].strip()


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


def classify(title: str, summary: str, policy_area: str) -> str:
    if policy_area:
        kind = POLICY_AREA_MAP.get(policy_area)
        if kind:
            return kind
        # Unknown tag — keep as lowercase snake_case for visibility
        return f"policy_{policy_area.lower()}"
    hay = f"{title}  {summary}"
    for name, pat in FALLBACK_RULES:
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
        policy_area = extract_policy_area(raw)
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary, policy_area)
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": title[:240],
            "link": link,
            "policy_area": policy_area,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"eu_commission: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "kind", "title", "link", "policy_area", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"eu_commission: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"eu_commission: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
