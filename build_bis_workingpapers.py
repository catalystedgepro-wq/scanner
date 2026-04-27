#!/usr/bin/env python3
"""
build_bis_workingpapers.py — BIS Working Papers research frontier.

Source: https://www.bis.org/doclist/wppubls.rss
        RSS 1.0/RDF with cb:JELCode + cb:keyword + dc:date ISO-8601.

BIS (Bank for International Settlements, Basel) is the central bank of
central banks — 60+ member CBs coordinate via BIS research. Working Papers
(~50-80/yr) telegraph 6-24mo-ahead monetary + regulatory direction:
rate-path research → Fed/ECB/BOE/BOJ/PBOC policy pivots, financial-
stability research → Basel III.5/Basel IV capital rules, CBDC/stablecoin
research → BIS Innovation Hub regulatory framework, cross-border payment
research → mBridge/Agorá G20 infrastructure, climate-risk research → NGFS
scenario framework drives bank stress testing.

Drives rate-path instrument pairs (TLT/IEF/SHY/TIPS/DX-Y.NYB), financial-
sector regulation (JPM/BAC/C/WFC/GS/MS/DBK/HSBA/UBSG), payments/stablecoin
(CRCL/MA/V/PYPL/USDT/USDC proxies), crypto (BTC/ETH regulatory framework),
climate-transition (NEE/BEP/ENPH on NGFS scenario uplifts).

Distinct from build_ecb_press.py (ECB press firehose, EU-specific
monetary), build_fed_speeches.py (US Fed speaker + voter-vote scan),
build_bis_dollar.py (BIS narrow-dollar EER dataset numerics),
build_bis_rates.py (BIS CB policy rates dataset numerics), build_fsb_
stability.py (FSB G20 financial-stability peer review). This is the
cross-cutting BIS research firehose covering academic frontier feeding
central-bank decisions.

Output: bis_workingpapers.csv — filed_utc, kind, title, link, summary.

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

URL = "https://www.bis.org/doclist/wppubls.rss"
OUT = pathlib.Path(__file__).resolve().parent / "bis_workingpapers.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# JEL-code family → kind. Priority order: most-specific first.
# Reference: https://www.aeaweb.org/econlit/jelCodes.php
JEL_PREFIX_MAP = [
    # Monetary / macro
    ("E5", "monetary_policy"),       # Monetary policy, central banking, money supply
    ("E4", "money_interest"),        # Money and interest rates
    ("E3", "prices_inflation"),      # Prices, business fluctuations, cycles
    ("E6", "macro_policy"),          # Macroeconomic aspects of public finance
    ("E2", "macro_consumption"),     # Consumption, saving, investment
    # Financial economics
    ("G2", "financial_institutions"),  # Banks, pension funds, insurance
    ("G1", "asset_markets"),         # General financial markets
    ("G3", "corporate_finance"),     # M&A, governance
    ("G5", "household_finance"),     # Household finance
    # International
    ("F3", "international_finance"),  # BOP, exchange rates, capital flows
    ("F4", "international_macro"),   # International macroeconomic aspects
    ("F1", "trade_policy"),          # Trade, tariffs, protectionism
    ("F6", "globalization"),         # Global economic effects
    # Econometrics / methods
    ("C1", "econometrics"),          # Econometric methods
    ("C5", "econometric_modeling"),  # Model evaluation, validation
    ("C8", "data_methods"),          # Data collection, econometric methodology
    # Growth / development
    ("O3", "tech_innovation"),       # Innovation, R&D, technological change
    ("O4", "growth_productivity"),   # Growth, productivity
    # Labor / public
    ("J", "labor_economics"),        # Labor
    ("H", "public_finance"),         # Public economics, taxation
    # Environment / resources
    ("Q5", "climate_environment"),   # Environmental economics
    ("Q4", "energy_economics"),      # Energy markets
]


# Secondary fallback — keyword → kind. Scans title + description if JEL miss.
KEYWORD_CLASSIFIER = [
    ("cbdc",                re.compile(r"\b(CBDC|central bank digital currency|digital euro|digital yuan|project icebreaker|project agor|project mbridge|wholesale CBDC|retail CBDC)\b", re.I)),
    ("stablecoin_crypto",   re.compile(r"\b(stablecoin|tether|USDC|USDT|cryptocurrency|bitcoin|BTC|ethereum|ETH\b|tokenis|decentrali[sz]ed finance|DeFi|tokenized deposit)\b", re.I)),
    ("fx_exchange_rate",    re.compile(r"\b(exchange rate|FX\b|foreign exchange|dollar dominance|reserve currency|renminbi|RMB|dedollari|DXY|currency intervention)\b", re.I)),
    ("bank_regulation",     re.compile(r"\b(Basel III|Basel IV|capital adequacy|liquidity coverage|leverage ratio|systemic risk|G-SIB|TLAC|MREL|countercyclical buffer|FSB\b)\b", re.I)),
    ("climate_risk",        re.compile(r"\b(climate risk|NGFS|transition risk|physical risk|stranded asset|green bond|sustainable finance|carbon|emissions)\b", re.I)),
    ("inflation_research",  re.compile(r"\b(inflation|price stability|CPI|PCE\b|inflation expectation|Phillips curve|wage-price)\b", re.I)),
    ("monetary_transmission",  re.compile(r"\b(monetary policy|rate hike|rate cut|policy rate|QE\b|quantitative easing|balance sheet|reserve requirement|forward guidance|zero lower bound|ZLB)\b", re.I)),
    ("payments_systems",    re.compile(r"\b(payment system|cross-border payment|fast payment|settlement|real-time gross|RTGS|correspondent bank)\b", re.I)),
    ("ai_ml_macro",         re.compile(r"\b(artificial intelligence|machine learning|AI\b|neural network|large language model|LLM\b|big data|quantum comput)\b", re.I)),
    ("housing_mortgage",    re.compile(r"\b(housing|mortgage|real estate|house price|property price)\b", re.I)),
    ("labor_market",        re.compile(r"\b(labour market|labor market|unemployment|employment|wage|worker|Phillips)\b", re.I)),
    ("sovereign_debt",      re.compile(r"\b(sovereign debt|fiscal|government debt|debt sustainability|bond yield|term premium|yield curve)\b", re.I)),
    ("capital_flows",       re.compile(r"\b(capital flow|cross-border|BOP\b|balance of payment|international investment)\b", re.I)),
    ("trade_supply",        re.compile(r"\b(trade|tariff|supply chain|globali[sz]ation|protectionism|import|export)\b", re.I)),
    ("crisis_stability",    re.compile(r"\b(financial crisis|financial stability|systemic|contagion|stress test|bank run|spillover)\b", re.I)),
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
    # ISO-8601 form first (BIS uses "2026-04-01T09:21:00Z")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})", raw)
    if m:
        y, mo, d, hh, mm, ss = (int(x) for x in m.groups())
        try:
            return datetime(y, mo, d, hh, mm, ss, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return ""
    # RFC2822 fallback
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def classify(jel_codes: list[str], title: str, keywords: list[str], summary: str) -> str:
    # Primary: JEL-code prefix match
    for code in jel_codes:
        code = code.strip().upper()
        for prefix, kind in JEL_PREFIX_MAP:
            if code.startswith(prefix):
                return kind
    # Secondary: keyword/title regex
    hay = " ".join([title, summary] + keywords)
    for name, pat in KEYWORD_CLASSIFIER:
        if pat.search(hay):
            return name
    return "research"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    # RDF <item rdf:about="..."> ... </item>
    items = re.findall(r"<item\s+rdf:about[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        jel_codes = extract_all(raw, "cb:JELCode")
        keywords = extract_all(raw, "cb:keyword")
        filed = to_iso_utc(extract_tag(raw, "dc:date"))
        if not (title and link):
            continue
        kind = classify(jel_codes, title, keywords, summary)
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
        print(f"bis_workingpapers: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"bis_workingpapers: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"bis_workingpapers: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
