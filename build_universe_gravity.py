#!/usr/bin/env python3
"""build_universe_gravity.py — Ingest the full 10,000+ ticker traded universe.

The "Empty Map" — every traded node exists here regardless of filing activity.
This is the Gravity Layer; filings add Velocity on top.

Data sources (all free, no auth):
  1. SEC company_tickers_exchange.json  — CIK + exchange for ~12,000 tickers
  2. NASDAQ nasdaqtraded.txt            — symbol + name + market category
  3. .gics_sic_cache.json              — SIC codes we already fetched
  4. industry_hierarchy_lookup.json    — GICS classifications already computed
  5. Yahoo Finance quoteSummary         — market cap (fetched for top tickers)

Output: entity_master.json
  {
    "AAPL": {
      "cik": "0000320193",
      "name": "Apple Inc.",
      "exchange": "NMS",
      "etf": false,
      "lei": null,         <- populated by build_lei_enrichment.py
      "isin": null,        <- populated by build_lei_enrichment.py
      "figi": null,        <- populated by build_lei_enrichment.py
      "mkt_cap_usd": null, <- populated by enrich_market_caps()
      "mkt_cap_tier": "unknown",
      "etf_weights_sum": 0.0,
      "gravity": null,     <- computed by gravity_engine.py
      "gics": {"s":"tech","ig":"...","i":"...","si":"..."},
      "last_updated": "2026-04-04"
    }
  }

Run once to build the map, then nightly to catch new listings/delistings.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

try:
    import yfinance as yf
except Exception:
    yf = None

try:
    from build_gics_mapper import sic_to_gics as _sic_to_gics
except Exception:
    def _sic_to_gics(sic: int) -> str:
        return "other"

try:
    from build_gics_hierarchy import sic_to_gics as _sic_to_full_gics
except Exception:
    _sic_to_full_gics = None

ROOT = Path(__file__).parent
TODAY = str(date.today())

UA = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 contact@catalystedge.com")
_SIC_FETCH_DELAY_SEC = max(0.12, float(os.environ.get("UNIVERSE_SIC_FETCH_DELAY_SEC", "0.18") or 0.18))
_COMMON_STOCK_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_ACTIVE_PRIORITY_FILES = (
    "sec_catalyst_tickers.txt",
    "combined_priority_tickers.txt",
    "sec_top_gappers_tickers.txt",
)
_SECTOR_ETF_TO_SECTOR = {
    "XLK": "tech",
    "SMH": "semis",
    "XLF": "financials",
    "XLV": "biotech",
    "XLE": "energy",
    "XLB": "materials",
    "XLI": "industrials",
    "XLU": "utilities",
    "XLRE": "real_estate",
    "XLY": "consumer",
    "XLP": "staples",
    "XLC": "comms",
}
_YAHOO_SECTOR_MAP = {
    "technology": "tech",
    "financial services": "financials",
    "healthcare": "biotech",
    "health care": "biotech",
    "energy": "energy",
    "basic materials": "materials",
    "industrials": "industrials",
    "consumer cyclical": "consumer",
    "consumer defensive": "staples",
    "communication services": "comms",
    "real estate": "real_estate",
    "utilities": "utilities",
}
_FREEFORM_SECTOR_PHRASES = {
    "software infrastructure": "tech",
    "software application": "tech",
    "information technology services": "tech",
    "it services": "tech",
    "internet content information": "tech",
    "shell companies": "financials",
    "blank check": "financials",
    "asset management": "financials",
    "capital markets": "financials",
    "financial data stock exchanges": "financials",
    "banks diversified": "financials",
    "insurance brokers": "financials",
    "mortgage finance": "financials",
    "reit office": "real_estate",
    "reit retail": "real_estate",
    "reit mortgage": "real_estate",
    "reit specialty": "real_estate",
    "real estate services": "real_estate",
    "real estate development": "real_estate",
    "telecom services": "comms",
    "broadcasting": "comms",
    "medical devices": "biotech",
    "health information services": "biotech",
    "drug manufacturers specialty generic": "biotech",
    "drug manufacturers general": "biotech",
    "biotechnology": "biotech",
    "packaged foods": "staples",
    "farm products": "staples",
    "beverages wineries distilleries": "staples",
    "beverages non alcoholic": "staples",
    "restaurants": "consumer",
    "internet retail": "consumer",
    "specialty retail": "consumer",
    "auto manufacturers": "consumer",
    "aerospace defense": "industrials",
    "specialty industrial machinery": "industrials",
    "electrical equipment parts": "industrials",
    "building products equipment": "industrials",
    "oil gas e p": "energy",
    "oil gas midstream": "energy",
    "oil gas refining marketing": "energy",
    "specialty chemicals": "materials",
    "steel": "materials",
    "coking coal": "materials",
    "utilities regulated electric": "utilities",
    "utilities diversified": "utilities",
    "utilities renewable": "utilities",
    "semiconductor equipment materials": "semis",
}
_SECTOR_TITLES = {
    "biotech": "Health Care",
    "comms": "Communication Services",
    "consumer": "Consumer Discretionary",
    "energy": "Energy",
    "financials": "Financials",
    "industrials": "Industrials",
    "materials": "Materials",
    "other": "Other",
    "real_estate": "Real Estate",
    "semis": "Information Technology",
    "staples": "Consumer Staples",
    "tech": "Information Technology",
    "utilities": "Utilities",
}
_FREEFORM_SECTOR_RULES: list[tuple[str, str, tuple[re.Pattern[str], ...]]] = [
    (
        "semis",
        "semiconductor_text",
        (
            re.compile(r"\bsemiconductor(?:s| equipment| materials)?\b", re.I),
            re.compile(r"\bchip(?:s|maker|set)?\b", re.I),
            re.compile(r"\bfabless\b", re.I),
        ),
    ),
    (
        "tech",
        "software_cyber_text",
        (
            re.compile(r"\bsoftware\b", re.I),
            re.compile(r"\bcyber(?:security)?\b", re.I),
            re.compile(r"\bcloud\b", re.I),
            re.compile(r"\binformation technology\b", re.I),
            re.compile(r"\b(?:saas|platform|internet|digital|data center|hosting|identity|endpoint|network security)\b", re.I),
        ),
    ),
    (
        "financials",
        "financial_market_text",
        (
            re.compile(r"\b(?:bank|banking|banc|financial services|capital markets|asset management|wealth|insurance|reinsurance|broker(?:age)?|securities|credit services|mortgage finance|lending)\b", re.I),
            re.compile(r"\b(?:shell compan(?:y|ies)|blank check|spac|acquisition corp|investment trust)\b", re.I),
        ),
    ),
    (
        "real_estate",
        "real_estate_text",
        (
            re.compile(r"\breit\b", re.I),
            re.compile(r"\b(?:real estate|property|properties|mortgage reit|residential reit|office reit|retail reit)\b", re.I),
        ),
    ),
    (
        "biotech",
        "healthcare_text",
        (
            re.compile(r"\b(?:biotech|biotechnology|pharmaceutical|drug manufacturers?|medical devices?|health(?:care| information)?|diagnostics?)\b", re.I),
        ),
    ),
    (
        "energy",
        "energy_text",
        (
            re.compile(r"\b(?:oil|gas|petroleum|midstream|upstream|downstream|drilling|exploration|royalty trust|uranium|renewable)\b", re.I),
        ),
    ),
    (
        "materials",
        "materials_text",
        (
            re.compile(r"\b(?:chemicals?|specialty chemicals|metals?|steel|mining|minerals?|copper|lithium|gold|silver|coal|forest products)\b", re.I),
        ),
    ),
    (
        "industrials",
        "industrials_text",
        (
            re.compile(r"\b(?:industrial|industrials|machinery|equipment|engineering|aerospace|defense|logistics|transport|shipping|rail|airlines?)\b", re.I),
        ),
    ),
    (
        "staples",
        "staples_text",
        (
            re.compile(r"\b(?:staples|packaged foods?|farm products|beverages?|household|grocery|tobacco)\b", re.I),
        ),
    ),
    (
        "consumer",
        "consumer_text",
        (
            re.compile(r"\b(?:consumer cyclical|consumer discretionary|restaurants?|retail|specialty retail|internet retail|travel|leisure|hotels?|apparel|footwear|auto manufacturers?)\b", re.I),
        ),
    ),
    (
        "comms",
        "communications_text",
        (
            re.compile(r"\b(?:communication services|telecom|wireless|broadcasting|media|advertising|streaming)\b", re.I),
        ),
    ),
    (
        "utilities",
        "utilities_text",
        (
            re.compile(r"\b(?:utilities|regulated electric|regulated water|diversified utilities|independent power|renewable utilities?)\b", re.I),
        ),
    ),
]
_ETF_VEHICLE_NAME_RE = re.compile(
    r"\b(etf|exchange[- ]traded fund|fund|trust|portfolio|index|spdr|ishares|vanguard|invesco|proshares|direxion)\b",
    re.I,
)
_NAME_SECTOR_RULES: list[tuple[str, str, tuple[re.Pattern[str], ...]]] = [
    (
        "real_estate",
        "property_reit",
        (
            re.compile(r"\breit\b", re.I),
            re.compile(r"\b(realty|properties|property|mortgage|apartment|residential|self-storage|land trust)\b", re.I),
        ),
    ),
    (
        "financials",
        "financial_services",
        (
            re.compile(r"\b(bank|banc|bancorp|bancshares|financial|finance|insurance|reinsurance|asset management|securities|brokerage|capital markets|specialty finance|credit|lending)\b", re.I),
            re.compile(r"\b(acquisition corp\.?|spac|capital corp\.?|investment trust|shell compan(?:y|ies)|blank check)\b", re.I),
        ),
    ),
    (
        "financials",
        "financial_vehicles",
        (
            re.compile(r"\b((closed[- ]end|income|bond|credit|municipal|tax[- ]free|floating rate|dividend|opportunistic)\s+(fund|trust)|business development company)\b", re.I),
        ),
    ),
    (
        "biotech",
        "health_sciences",
        (
            re.compile(r"\blabs?\b", re.I),
            re.compile(r"\b(pharma|pharmaceutical|therapeutic|therapeutics|therapies|biotech|biopharma|biosciences|biomedical|biomed|genomic|genomics|oncology|medical|health|life sciences?|diagnostic|laborator|clinic|surgical)\b", re.I),
        ),
    ),
    (
        "semis",
        "semiconductor",
        (
            re.compile(r"\b(semiconductor|semiconductors|chip|microelectronics)\b", re.I),
        ),
    ),
    (
        "tech",
        "software_systems",
        (
            re.compile(r"\b(software|systems|technology|technologies|tech|data|digital|cloud|cyber|cybersecurity|networks?|internet|ai|artificial intelligence|information|platforms?|identity|access|security)\b", re.I),
        ),
    ),
    (
        "energy",
        "energy_resources",
        (
            re.compile(r"\b(energy|petroleum|oil|gas|lng|uranium|drilling|exploration|pipeline|midstream|solar|wind|renewable)\b", re.I),
        ),
    ),
    (
        "materials",
        "materials_metals",
        (
            re.compile(r"\b(mining|minerals|metals|steel|copper|lithium|gold|silver|chemical|chemicals|fertilizer|forest products)\b", re.I),
        ),
    ),
    (
        "utilities",
        "power_water",
        (
            re.compile(r"\b(utility|utilities|electric|power|water|wastewater|gas distribution)\b", re.I),
        ),
    ),
    (
        "industrials",
        "industrial_logistics",
        (
            re.compile(r"\b(aerospace|aviation|defense|industrial|logistics|transport|shipping|freight|railroad|railway|railways|airlines?|machinery|automation|robotics|engineering|manufactur|equipment|marine|vessel|tankers?|cargo)\b", re.I),
        ),
    ),
    (
        "staples",
        "consumer_staples",
        (
            re.compile(r"\b(food|foods|beverage|beverages|household|grocery|tobacco|packaged goods)\b", re.I),
        ),
    ),
    (
        "consumer",
        "consumer_discretionary",
        (
            re.compile(r"\b(retail|restaurant|restaurants|apparel|footwear|gaming|entertainment|travel|hotel|leisure|automotive|beauty|wax|salon|casino)\b", re.I),
        ),
    ),
    (
        "comms",
        "media_telecom",
        (
            re.compile(r"\b(media|telecom|wireless|communications|broadcast|streaming|advertising)\b", re.I),
        ),
    ),
]
_DERIVATIVE_SUFFIX_RULES = (
    re.compile(r"[-./$](WSA|WSB|WS|WT|W|U|R|RI|RT|UN)$", re.I),
    re.compile(r"[-./$](PR[A-Z]{1,2}|P[A-Z]{1,2})$", re.I),
    re.compile(r"\$[A-Z]{1,2}$", re.I),
)
_COMPACT_DERIVATIVE_SUFFIX_RULES = (
    re.compile(r"^(?P<base>[A-Z0-9]{3,12}?)(?P<suffix>WSA|WSB|WS|WT|RT|UN|U|W|R)$", re.I),
    re.compile(r"^(?P<base>[A-Z0-9]{3,12}?)(?P<suffix>PR[A-Z]{1,2}|P[A-Z]{1,2})$", re.I),
    re.compile(r"^(?P<base>[A-Z0-9]{4,12}?)(?P<suffix>P)$", re.I),
)
_SOFT_SECTOR_SOURCES = {"name_heuristic", "base_symbol", "inferred_etf", "etf_self"}
_GENERIC_OTHER_SOURCES = {
    "adr_foreign_common",
    "holding_company",
    "long_tail_unclassified",
    "otc_derivative_generic",
}
_LONG_TAIL_SECTOR_CACHE = ROOT / ".long_tail_sector_cache.json"
_LONG_TAIL_BUCKET_SECTOR = {
    "closed_end_fund": "financials",
    "income_fund": "financials",
    "investment_vehicle": "financials",
    "business_development_company": "financials",
    "royalty_trust": "energy",
    "shell_company": "financials",
    "blank_check": "financials",
}


def _normalized_freeform_text(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        text = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _bridge_freeform_sector(*values: object) -> tuple[str, str]:
    haystack = _normalized_freeform_text(*values)
    if not haystack:
        return "", ""

    for phrase, sector in _FREEFORM_SECTOR_PHRASES.items():
        if phrase in haystack:
            return sector, f"text_bridge:{phrase}"

    if "security" in haystack and not re.search(
        r"\b(?:securities|broker|brokerage|asset management|capital markets|investment|fund|trust|insurance)\b",
        haystack,
        re.I,
    ):
        return "tech", "text_bridge:security_company"

    for sector, label, patterns in _FREEFORM_SECTOR_RULES:
        for pattern in patterns:
            if pattern.search(haystack):
                return sector, f"{label}:{pattern.pattern}"
    return "", ""

# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get(url: str, retries: int = 3, timeout: int = 15,
         headers: dict | None = None) -> bytes | None:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
            else:
                print(f"  WARN: fetch failed {url}: {exc}")
    return None


# ── Source 1: SEC company_tickers_exchange.json ───────────────────────────────
def fetch_sec_tickers() -> dict[str, dict]:
    """Returns {ticker: {cik, name, exchange}} for ~12,000 SEC-registered entities."""
    print("  Fetching SEC company_tickers_exchange.json ...")
    raw = _get("https://www.sec.gov/files/company_tickers_exchange.json")
    if not raw:
        print("  WARN: SEC ticker file unavailable")
        return {}
    try:
        data = json.loads(raw)
        # Format: {"fields": [...], "data": [[cik, name, ticker, exchange], ...]}
        fields = data.get("fields", [])
        rows   = data.get("data", [])
        cik_i  = fields.index("cik")  if "cik"      in fields else 0
        name_i = fields.index("name") if "name"     in fields else 1
        tick_i = fields.index("ticker") if "ticker" in fields else 2
        exch_i = fields.index("exchange") if "exchange" in fields else 3
        out = {}
        for row in rows:
            t = str(row[tick_i]).strip().upper()
            if not t or t == "None":
                continue
            out[t] = {
                "cik":      str(row[cik_i]).zfill(10),
                "name":     str(row[name_i]).strip(),
                "exchange": str(row[exch_i]).strip(),
            }
        print(f"  SEC: {len(out)} tickers")
        return out
    except Exception as exc:
        print(f"  WARN: SEC parse error: {exc}")
        return {}


# ── Source 2: NASDAQ nasdaqtraded.txt ─────────────────────────────────────────
def fetch_nasdaq_symbols() -> dict[str, dict]:
    """Returns {ticker: {name, etf, nasdaq_category}} from NASDAQ symbol dir."""
    print("  Fetching NASDAQ nasdaqtraded.txt ...")
    raw = _get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt",
               timeout=20)
    if not raw:
        print("  WARN: NASDAQ symbol file unavailable, skipping")
        return {}
    try:
        text = raw.decode("latin-1")
        out = {}
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        for row in reader:
            t = (row.get("Symbol") or row.get("NASDAQ Symbol") or "").strip().upper()
            if not t or t.startswith("FILE"):
                continue
            if (row.get("Test Issue") or "N").strip().upper() == "Y":
                continue
            out[t] = {
                "name":  (row.get("Security Name") or "").strip(),
                "etf":   (row.get("ETF") or "N").strip().upper() == "Y",
                "nasdaq_category": (row.get("Market Category") or "").strip(),
            }
        print(f"  NASDAQ: {len(out)} symbols")
        return out
    except Exception as exc:
        print(f"  WARN: NASDAQ parse error: {exc}")
        return {}


# ── Source 3: Market cap — SEC EDGAR shares × Yahoo v8 price ─────────────────
# Yahoo Finance authenticated endpoints (v10/v7/crumb) are all gated as of 2025.
# Strategy: SEC EDGAR company facts API (free, no auth) → shares outstanding
#           Yahoo Finance v8 chart (free, no auth)       → latest price
#           market_cap = shares × price
_YF_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Safari/537.36")

# EDGAR share-count XBRL tags to try in order
_SHARE_TAGS = [
    ("dei",     "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesIssuedAndOutstanding"),
]


def _fetch_shares_outstanding(cik: str) -> int | None:
    """Return latest share count from SEC EDGAR XBRL company facts."""
    padded = cik.zfill(10)
    url    = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json"
    raw    = _get(url, timeout=15)
    if not raw:
        return None
    try:
        facts = json.loads(raw)
        for ns, tag in _SHARE_TAGS:
            entries = (facts.get("facts", {})
                       .get(ns, {})
                       .get(tag, {})
                       .get("units", {})
                       .get("shares", []))
            if entries:
                # Most recent filed value
                recent = max(entries, key=lambda x: x.get("end", ""))
                val = recent.get("val", 0)
                if val and val > 0:
                    return int(val)
    except Exception:
        pass
    return None


def _fetch_price(ticker: str) -> float | None:
    """Return latest price from Yahoo Finance v8 chart (no auth required)."""
    encoded = urllib.parse.quote(ticker)
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
           f"?interval=1d&range=1d")
    raw = _get(url, timeout=10, headers={"User-Agent": _YF_UA})
    if not raw:
        return None
    try:
        d     = json.loads(raw)
        meta  = ((d.get("chart") or {}).get("result") or [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        if price and price > 0:
            return float(price)
    except Exception:
        pass
    return None


def _fetch_market_cap(ticker: str, cik: str | None = None) -> float | None:
    """
    Compute market cap from SEC EDGAR shares × Yahoo v8 price.
    Falls back to meta.marketCap from v8 chart (present on ~30% of tickers).
    Returns float or None.
    """
    # ── Attempt 1: EDGAR shares × Yahoo price ─────────────────────────────
    if cik:
        shares = _fetch_shares_outstanding(cik)
        time.sleep(0.1)
        if shares:
            price = _fetch_price(ticker)
            if price and price > 0:
                return float(shares * price)

    # ── Attempt 2: v8 chart meta.marketCap (sometimes present) ────────────
    encoded = urllib.parse.quote(ticker)
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
           f"?interval=1d&range=1d")
    raw = _get(url, timeout=10, headers={"User-Agent": _YF_UA})
    if raw:
        try:
            d    = json.loads(raw)
            meta = ((d.get("chart") or {}).get("result") or [{}])[0].get("meta", {})
            cap  = meta.get("marketCap")
            if cap and cap > 0:
                return float(cap)
        except Exception:
            pass

    return None


def _classify_yahoo_gics(sector: str | None, industry: str | None) -> dict | None:
    sector_raw = str(sector or "").strip()
    industry_raw = str(industry or "").strip()
    sector_norm = sector_raw.lower()
    industry_norm = industry_raw.lower()

    mapped = _YAHOO_SECTOR_MAP.get(sector_norm)
    bridged_sector, bridge_evidence = _bridge_freeform_sector(sector_raw, industry_raw)
    if bridged_sector:
        mapped = bridged_sector
    elif "semiconductor" in industry_norm:
        mapped = "semis"
    elif not mapped and ("biotech" in industry_norm or "drug manufacturer" in industry_norm or "pharmaceutical" in industry_norm):
        mapped = "biotech"

    if not mapped:
        return None

    leaf = industry_raw or sector_raw or bridge_evidence or mapped.replace("_", " ").title()
    return {
        "s": mapped,
        "ig": sector_raw or mapped.replace("_", " ").title(),
        "i": leaf,
        "si": leaf,
    }


def _build_gics(sector_key: str, industry_text: str = "") -> dict:
    title = _SECTOR_TITLES.get(sector_key, sector_key.replace("_", " ").title())
    leaf = industry_text.strip() if industry_text else title
    return {"s": sector_key, "ig": title, "i": leaf, "si": leaf}


def _gics_from_sic(sic: int) -> dict | None:
    if not sic:
        return None
    if _sic_to_full_gics is not None:
        try:
            full_gics = _sic_to_full_gics(sic)
        except Exception:
            full_gics = {}
        if isinstance(full_gics, dict):
            sector = str(full_gics.get("s") or "").strip().lower()
            if sector:
                normalized = {key: value for key, value in full_gics.items() if value}
                normalized["s"] = sector
                return normalized
    sector = _sic_to_gics(sic)
    if sector and sector != "other":
        return _build_gics(sector, f"SIC {sic}")
    return None


def _fetch_yahoo_profile(ticker: str) -> tuple[str | None, str | None]:
    if yf is not None:
        try:
            quote = yf.Ticker(ticker)
            info = getattr(quote, "info", {}) or {}
            sector = info.get("sector") or info.get("sectorDisp")
            industry = info.get("industry") or info.get("industryDisp")
            if sector or industry:
                return str(sector or "").strip() or None, str(industry or "").strip() or None
        except Exception:
            pass
    encoded = urllib.parse.quote(ticker)
    url = (f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{encoded}"
           f"?modules=assetProfile")
    raw = _get(url, timeout=10, headers={"User-Agent": _YF_UA})
    if not raw:
        return None, None
    try:
        data = json.loads(raw)
        profile = ((data.get("quoteSummary") or {}).get("result") or [{}])[0].get("assetProfile", {})
        sector = profile.get("sector")
        industry = profile.get("industry")
        if sector or industry:
            return sector, industry
    except Exception:
        pass
    return None, None


def _fetch_sic(cik: str) -> int | None:
    padded = str(cik or "").zfill(10)
    if not padded.strip("0"):
        return None
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    raw = _get(url, timeout=15)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        value = int(data.get("sic") or 0)
        return value or None
    except Exception:
        return None


def enrich_market_caps(entity_master: dict,
                       priority_tickers: list[str],
                       batch_size: int = 50) -> int:
    """
    Fetch market cap from Yahoo Finance quoteSummary for priority tickers.
    Updates entity_master in-place. Returns count of successful fetches.
    """
    # Load existing quote cache to avoid redundant fetches
    qcache_path = ROOT / ".sec_quote_cache.json"
    qcache: dict = {}
    if qcache_path.exists():
        try:
            qcache = json.loads(qcache_path.read_text())
        except Exception:
            pass

    updated = 0
    for i, ticker in enumerate(priority_tickers):
        rec = entity_master.get(ticker, {})
        if rec.get("mkt_cap_usd"):
            continue

        # Check quote cache first
        cached = qcache.get(ticker, {})
        cap = None
        if cached.get("marketCap"):
            cap = cached["marketCap"]
        else:
            cik = rec.get("cik", "")
            cap = _fetch_market_cap(ticker, cik=cik)
            if cap:
                qcache.setdefault(ticker, {})["marketCap"] = cap
            time.sleep(0.15)  # rate limit

        if cap and cap > 0:
            entity_master[ticker]["mkt_cap_usd"] = cap
            updated += 1

        if (i + 1) % batch_size == 0:
            # Save cache progress
            qcache_path.write_text(json.dumps(qcache, indent=2))
            print(f"  market cap: {i+1}/{len(priority_tickers)} processed, {updated} enriched ...")

    # Final cache save
    qcache_path.write_text(json.dumps(qcache, indent=2))
    return updated


def load_active_priority_tickers() -> set[str]:
    active: set[str] = set()
    for fname in _ACTIVE_PRIORITY_FILES:
        path = ROOT / fname
        if not path.exists():
            continue
        active.update(
            line.strip().upper()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return active


def _extract_etf_symbols(raw: list | tuple | str | dict | None) -> list[str]:
    if not raw:
        return []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    symbols: list[str] = []
    for item in items:
        if isinstance(item, str):
            symbol = item
        elif isinstance(item, dict):
            symbol = item.get("etf") or item.get("ticker") or item.get("symbol") or ""
        else:
            symbol = ""
        symbol = str(symbol or "").strip().upper()
        if symbol:
            symbols.append(symbol)
    return symbols


def _normalized_gics(rec: dict) -> dict:
    gics = rec.get("gics")
    return gics if isinstance(gics, dict) else {}


def _cik_variants(cik: str | None) -> list[str]:
    raw = str(cik or "").strip()
    if not raw:
        return []
    normalized = raw.lstrip("0")
    variants = [raw]
    if normalized and normalized not in variants:
        variants.append(normalized)
    padded = normalized.zfill(10) if normalized else raw.zfill(10)
    if padded not in variants:
        variants.append(padded)
    return variants


def _canonical_cik(cik: str | None) -> str:
    variants = _cik_variants(cik)
    return variants[-1] if variants else ""


def _has_cached_sic_value(cik_variants: list[str], sic_cache: dict) -> bool:
    for variant in cik_variants:
        if variant not in sic_cache:
            continue
        value = sic_cache.get(variant)
        if value in (None, "", 0, "0"):
            continue
        try:
            if int(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _is_generic_other_source(source: str, sector: str) -> bool:
    return sector == "other" and source in _GENERIC_OTHER_SOURCES


def _needs_sector_retry(rec: dict) -> bool:
    sector = _normalized_sector(rec)
    source = str(rec.get("sector_source") or "")
    return sector == "unknown" or _is_generic_other_source(source, sector)


def _is_strong_sector_source(source: str, sector: str = "") -> bool:
    return bool(source) and source not in _SOFT_SECTOR_SOURCES and not _is_generic_other_source(source, sector)


def _mapped_sector_etf_hits(rec: dict) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for symbol in _extract_etf_symbols(rec.get("etf_overlords")) + _extract_etf_symbols(rec.get("canopy_etfs")):
        if symbol in seen:
            continue
        seen.add(symbol)
        sector = _SECTOR_ETF_TO_SECTOR.get(symbol)
        if sector:
            hits.append((symbol, sector))
    return hits


def _sector_from_etf_refs(rec: dict) -> tuple[str, str]:
    hits = _mapped_sector_etf_hits(rec)
    if not hits:
        return "", ""
    sectors = {sector for _, sector in hits}
    if sectors <= {"tech", "semis"} and "semis" in sectors:
        semis_hits = [symbol for symbol, sector in hits if sector == "semis"]
        return "semis", "|".join(semis_hits)
    if len(sectors) != 1:
        return "", ""
    return hits[0][1], "|".join(symbol for symbol, _ in hits)


def _gics_specificity(gics: dict | None) -> int:
    if not isinstance(gics, dict):
        return 0
    return sum(1 for key in ("s", "ig", "i", "si") if gics.get(key))


def _looks_derivative_like(ticker: str) -> bool:
    cleaned = str(ticker or "").upper().strip()
    if not cleaned:
        return False
    if "$" in cleaned:
        return True
    if any(pattern.search(cleaned) for pattern in _DERIVATIVE_SUFFIX_RULES):
        return True
    return any(pattern.fullmatch(cleaned) for pattern in _COMPACT_DERIVATIVE_SUFFIX_RULES)


def _sector_from_sic_cache(rec: dict, sic_cache: dict) -> tuple[dict | None, str, bool, str]:
    for cik_key in _cik_variants(rec.get("cik")):
        if cik_key not in sic_cache:
            continue
        try:
            sic = int(sic_cache[cik_key] or 0)
        except (TypeError, ValueError):
            continue
        gics = _gics_from_sic(sic)
        if gics:
            return gics, "sic_cache", False, str(sic)
    return None, "", False, ""


def _sector_from_bedrock(ticker: str, bedrock_cache: dict) -> tuple[dict | None, str, bool, str]:
    rec = bedrock_cache.get(ticker) or {}
    sector = str(rec.get("sector") or "").strip().lower()
    if not sector or sector == "unknown":
        return None, "", False, ""
    industry = str(rec.get("industry") or "").strip()
    return _build_gics(sector, industry), "bedrock_cache", False, str(rec.get("sector_fmp") or sector)


def _sector_from_long_tail_cache(ticker: str, long_tail_cache: dict) -> tuple[dict | None, str, bool, str]:
    entry = (long_tail_cache or {}).get(ticker) or {}
    if not isinstance(entry, dict):
        return None, "", False, ""
    sector = str(entry.get("sector") or "").strip().lower()
    bucket = str(entry.get("generic_bucket") or "").strip().lower()
    if not sector:
        sector = _LONG_TAIL_BUCKET_SECTOR.get(bucket, "")
    bridge_evidence = ""
    if not sector:
        sector, bridge_evidence = _bridge_freeform_sector(
            entry.get("classification"),
            entry.get("industry"),
            entry.get("name"),
            bucket,
        )
    if not sector:
        return None, "", False, ""
    industry = str(entry.get("industry") or entry.get("classification") or entry.get("name") or "").strip()
    confidence = entry.get("confidence")
    confidence_text = ""
    if confidence not in (None, ""):
        try:
            confidence_text = f"{float(confidence):.2f}"
        except (TypeError, ValueError):
            confidence_text = str(confidence)
    evidence_parts = [
        part
        for part in (
            bucket,
            confidence_text,
            str(entry.get("model") or "").strip(),
            bridge_evidence,
        )
        if part
    ]
    source = str(entry.get("source") or "").strip() or ("long_tail_bucket" if bucket and not entry.get("sector") else "ollama_burnin")
    return _build_gics(sector, industry), source, True, "|".join(evidence_parts)


def _sector_from_name(ticker: str, rec: dict) -> tuple[dict | None, str, bool, str]:
    name = str(rec.get("name") or "").strip()
    if not name:
        return None, "", False, ""
    if rec.get("etf") and _ETF_VEHICLE_NAME_RE.search(name):
        return _build_gics("financials", name), "etf_vehicle", True, "name:etf_vehicle"
    for sector, label, patterns in _NAME_SECTOR_RULES:
        if rec.get("etf") and label == "financial_vehicles":
            continue
        for pattern in patterns:
            if pattern.search(name):
                return _build_gics(sector, name), "name_heuristic", True, f"{label}:{pattern.pattern}"
    bridged_sector, bridge_evidence = _bridge_freeform_sector(name)
    if bridged_sector:
        return _build_gics(bridged_sector, name), "name_bridge", True, bridge_evidence
    return None, "", False, ""


def _final_long_tail_fallback(ticker: str, rec: dict) -> tuple[dict | None, str, bool, str]:
    name = str(rec.get("name") or ticker).strip()
    name_upper = name.upper()
    ticker_upper = str(ticker or "").upper().strip()
    bridged_sector, bridge_evidence = _bridge_freeform_sector(name, ticker)
    if bridged_sector:
        return _build_gics(bridged_sector, name), "long_tail_bridge", True, bridge_evidence
    if any(
        token in name_upper
        for token in (
            "BUSINESS DEVELOPMENT",
            "MUNICIPAL",
            "TARGET TERM TRUST",
            "INCOME FUND",
            "CLOSED-END",
            "CLOSED END",
            "TOTAL RETURN FUND",
        )
    ) or re.search(r"\bBDC\b", name_upper):
        return _build_gics("financials", name), "long_tail_vehicle", True, "fund_trust_bdc"
    if "ROYALTY" in name_upper:
        return _build_gics("energy", name), "long_tail_vehicle", True, "royalty_trust"
    if "ADR" in name_upper or ticker_upper.endswith(("F", "Y")):
        return _build_gics("other", name), "adr_foreign_common", True, "suffix_or_adr_wrapper"
    if _looks_derivative_like(ticker_upper):
        return _build_gics("other", name), "otc_derivative_generic", True, "derivative_wrapper"
    if "HOLDINGS" in name_upper or "HOLDING" in name_upper:
        return _build_gics("other", name), "holding_company", True, "holding_company_residual"
    if rec.get("cik") or _COMMON_STOCK_TICKER_RE.fullmatch(ticker_upper):
        return _build_gics("other", name), "long_tail_unclassified", True, "residual_common_stock"
    return _build_gics("other", name), "long_tail_unclassified", True, "residual_generic_tail"


def _base_ticker_candidates(ticker: str) -> list[str]:
    out: list[str] = []
    cleaned = str(ticker or "").upper().strip()
    if not cleaned:
        return out
    if "$" in cleaned:
        out.append(cleaned.split("$", 1)[0])
    for pattern in _DERIVATIVE_SUFFIX_RULES:
        if pattern.search(cleaned):
            out.append(pattern.sub("", cleaned))
    for pattern in _COMPACT_DERIVATIVE_SUFFIX_RULES:
        match = pattern.fullmatch(cleaned)
        if match:
            out.append(match.group("base"))
    deduped: list[str] = []
    for symbol in out:
        symbol = symbol.strip("-./$")
        if symbol and symbol != cleaned and symbol not in deduped:
            deduped.append(symbol)
    return deduped


def _base_inheritance_allowed(ticker: str, rec: dict, base_rec: dict) -> bool:
    current_cik = _canonical_cik(rec.get("cik"))
    base_cik = _canonical_cik(base_rec.get("cik"))
    if current_cik and base_cik and current_cik == base_cik:
        return True
    return _looks_derivative_like(ticker)


def _same_cik_peer_sector(
    ticker: str,
    rec: dict,
    hier: dict,
    sector_lookup: dict,
    sic_cache: dict,
    bedrock_cache: dict,
    long_tail_cache: dict,
    entity_master: dict[str, dict],
    cik_index: dict[str, list[str]],
    direct_cache: dict[str, tuple[dict | None, str, bool, str]],
) -> tuple[dict | None, str, bool, str]:
    cik_key = _canonical_cik(rec.get("cik"))
    if not cik_key:
        return None, "", False, ""
    peers = cik_index.get(cik_key) or []
    candidates: dict[str, dict] = {}
    for peer_ticker in peers:
        if peer_ticker == ticker:
            continue
        peer_rec = entity_master.get(peer_ticker) or {}
        peer_direct = direct_cache.get(peer_ticker)
        if peer_direct is None:
            peer_direct = _recover_sector_direct(
                peer_ticker,
                peer_rec,
                hier,
                sector_lookup,
                sic_cache,
                bedrock_cache,
                long_tail_cache,
            )
            direct_cache[peer_ticker] = peer_direct
        peer_gics, peer_source, _, _ = peer_direct
        sector = str((peer_gics or {}).get("s") or "").strip().lower()
        if not sector or not _is_strong_sector_source(peer_source, sector):
            continue
        slot = candidates.setdefault(sector, {"gics": peer_gics, "tickers": []})
        slot["tickers"].append(peer_ticker)
        if _gics_specificity(peer_gics) > _gics_specificity(slot.get("gics")):
            slot["gics"] = peer_gics
    if len(candidates) != 1:
        return None, "", False, ""
    _, slot = next(iter(candidates.items()))
    evidence = "|".join(sorted(slot["tickers"])[:3])
    return slot["gics"], "same_cik_peer", True, evidence


def _recover_sector_direct(
    ticker: str,
    rec: dict,
    hier: dict,
    sector_lookup: dict,
    sic_cache: dict,
    bedrock_cache: dict,
    long_tail_cache: dict,
) -> tuple[dict | None, str, bool, str]:
    gics = _normalized_gics(rec)
    existing_source = str(rec.get("sector_source") or "gics")
    gics_sector = str(gics.get("s") or "").strip().lower()
    if gics_sector and existing_source not in _SOFT_SECTOR_SOURCES and not _is_generic_other_source(existing_source, gics_sector):
        return gics, rec.get("sector_source") or "gics", bool(rec.get("sector_inferred")), str(rec.get("sector_evidence") or "")

    direct_sector = str(rec.get("sector") or "").strip().lower()
    if direct_sector and existing_source not in _SOFT_SECTOR_SOURCES and not _is_generic_other_source(existing_source, direct_sector):
        return _build_gics(direct_sector, str(rec.get("name") or ticker)), rec.get("sector_source") or "sector_field", bool(rec.get("sector_inferred")), str(rec.get("sector_evidence") or "")

    lookup_gics = hier.get(ticker)
    if isinstance(lookup_gics, dict):
        sector = str(lookup_gics.get("s") or "").strip().lower()
        if sector:
            normalized = {key: value for key, value in lookup_gics.items() if value}
            normalized["s"] = sector
            return normalized, "industry_lookup", False, ""

    sector_list = sector_lookup.get(ticker) or []
    if sector_list:
        sector = str(sector_list[0] or "").strip().lower()
        if sector:
            return _build_gics(sector, str(rec.get("name") or ticker)), "sector_lookup", False, "|".join(str(item) for item in sector_list if item)

    sic_gics, sic_source, sic_inferred, sic_evidence = _sector_from_sic_cache(rec, sic_cache)
    if sic_gics:
        return sic_gics, sic_source, sic_inferred, sic_evidence

    bedrock_gics, bedrock_source, bedrock_inferred, bedrock_evidence = _sector_from_bedrock(ticker, bedrock_cache)
    if bedrock_gics:
        return bedrock_gics, bedrock_source, bedrock_inferred, bedrock_evidence

    long_tail_gics, long_tail_source, long_tail_inferred, long_tail_evidence = _sector_from_long_tail_cache(ticker, long_tail_cache)
    if long_tail_gics:
        return long_tail_gics, long_tail_source, long_tail_inferred, long_tail_evidence

    if rec.get("etf"):
        sector = _SECTOR_ETF_TO_SECTOR.get(ticker)
        if sector:
            return _build_gics(sector, str(rec.get("name") or ticker)), "etf_self", True, ticker

    inferred_etf_sector, inferred_etf_evidence = _sector_from_etf_refs(rec)
    if inferred_etf_sector:
        return _build_gics(inferred_etf_sector, str(rec.get("name") or ticker)), "inferred_etf", True, inferred_etf_evidence

    name_gics, name_source, name_inferred, name_evidence = _sector_from_name(ticker, rec)
    if name_gics:
        return name_gics, name_source, name_inferred, name_evidence

    return None, "", False, ""


def _recover_sector_detail(
    ticker: str,
    rec: dict,
    hier: dict,
    sector_lookup: dict,
    sic_cache: dict,
    bedrock_cache: dict,
    long_tail_cache: dict,
    entity_master: dict[str, dict],
    cik_index: dict[str, list[str]],
    direct_cache: dict[str, tuple[dict | None, str, bool, str]],
) -> tuple[dict | None, str, bool, str]:
    direct_result = direct_cache.get(ticker)
    if direct_result is None:
        direct_result = _recover_sector_direct(
            ticker,
            rec,
            hier,
            sector_lookup,
            sic_cache,
            bedrock_cache,
            long_tail_cache,
        )
        direct_cache[ticker] = direct_result
    direct_gics, direct_source, direct_inferred, direct_evidence = direct_result
    if direct_gics and _is_strong_sector_source(direct_source):
        return direct_gics, direct_source, direct_inferred, direct_evidence

    same_cik_gics, same_cik_source, same_cik_inferred, same_cik_evidence = _same_cik_peer_sector(
        ticker,
        rec,
        hier,
        sector_lookup,
        sic_cache,
        bedrock_cache,
        long_tail_cache,
        entity_master,
        cik_index,
        direct_cache,
    )
    if same_cik_gics:
        return same_cik_gics, same_cik_source, same_cik_inferred, same_cik_evidence

    for base_ticker in _base_ticker_candidates(ticker):
        base_rec = entity_master.get(base_ticker) or {}
        if not base_rec or not _base_inheritance_allowed(ticker, rec, base_rec):
            continue
        base_direct = direct_cache.get(base_ticker)
        if base_direct is None:
            base_direct = _recover_sector_direct(
                base_ticker,
                base_rec,
                hier,
                sector_lookup,
                sic_cache,
                bedrock_cache,
                long_tail_cache,
            )
            direct_cache[base_ticker] = base_direct
        base_gics, base_source, _, _ = base_direct
        base_sector = str((base_gics or {}).get("s") or "").strip().lower()
        if base_sector and _is_strong_sector_source(base_source, base_sector):
            return base_gics, "base_symbol", True, base_ticker

    if direct_gics:
        return direct_gics, direct_source, direct_inferred, direct_evidence

    for base_ticker in _base_ticker_candidates(ticker):
        base_rec = entity_master.get(base_ticker) or {}
        if not base_rec or not _base_inheritance_allowed(ticker, rec, base_rec):
            continue
        base_direct = direct_cache.get(base_ticker)
        if base_direct is None:
            base_direct = _recover_sector_direct(
                base_ticker,
                base_rec,
                hier,
                sector_lookup,
                sic_cache,
                bedrock_cache,
                long_tail_cache,
            )
            direct_cache[base_ticker] = base_direct
        base_gics, _, _, _ = base_direct
        if base_gics and base_gics.get("s"):
            return base_gics, "base_symbol", True, base_ticker

    final_gics, final_source, final_inferred, final_evidence = _final_long_tail_fallback(ticker, rec)
    if final_gics:
        return final_gics, final_source, final_inferred, final_evidence

    return None, "", False, ""


def _normalized_sector(rec: dict) -> str:
    gics = rec.get("gics") or {}
    sector = (gics.get("s") or rec.get("sector") or "").strip().lower()
    return sector or "unknown"


def apply_sector_recovery(
    entity_master: dict[str, dict],
    hier: dict,
    sector_lookup: dict,
    sic_cache: dict,
    bedrock_cache: dict,
    long_tail_cache: dict,
) -> tuple[int, dict[str, int]]:
    recovered = 0
    by_source: dict[str, int] = {}
    cik_index: dict[str, list[str]] = {}
    direct_cache: dict[str, tuple[dict | None, str, bool, str]] = {}
    for ticker, rec in entity_master.items():
        cik_key = _canonical_cik(rec.get("cik"))
        if cik_key:
            cik_index.setdefault(cik_key, []).append(ticker)
    for ticker, rec in entity_master.items():
        before_sector = _normalized_sector(rec)
        recovered_gics, sector_source, sector_inferred, sector_evidence = _recover_sector_detail(
            ticker,
            rec,
            hier,
            sector_lookup,
            sic_cache,
            bedrock_cache,
            long_tail_cache,
            entity_master,
            cik_index,
            direct_cache,
        )
        if not recovered_gics:
            if str(rec.get("sector_source") or "") in _SOFT_SECTOR_SOURCES:
                rec.pop("gics", None)
                rec.pop("sector", None)
                rec.pop("sector_source", None)
                rec.pop("sector_inferred", None)
                rec.pop("sector_evidence", None)
                if not rec.get("mkt_cap_usd") and str(rec.get("gravity_source") or "") in {"gics_baseline", "gics+etf"}:
                    rec.pop("gravity", None)
                    rec.pop("gravity_source", None)
            continue
        rec["gics"] = recovered_gics
        rec["sector"] = recovered_gics.get("s")
        rec["sector_source"] = sector_source
        if sector_inferred:
            rec["sector_inferred"] = True
            rec["sector_evidence"] = sector_evidence
        else:
            rec.pop("sector_inferred", None)
            rec.pop("sector_evidence", None)
        after_sector = str(recovered_gics.get("s") or "").strip().lower()
        if after_sector and before_sector in {"unknown", "other"} and before_sector != after_sector:
            recovered += 1
            by_source[sector_source] = by_source.get(sector_source, 0) + 1
    return recovered, by_source


def promote_flat_sector_fields(entity_master: dict[str, dict]) -> int:
    promoted = 0
    for ticker, rec in entity_master.items():
        direct_sector = str(rec.get("sector") or "").strip().lower()
        if not direct_sector:
            continue
        if _normalized_gics(rec).get("s") == direct_sector and rec.get("sector_source"):
            continue
        rec["gics"] = _build_gics(direct_sector, str(rec.get("name") or ticker))
        rec["sector_source"] = rec.get("sector_source") or "sector_field"
        promoted += 1
    return promoted


def enrich_sic_for_unknowns(
    entity_master: dict[str, dict],
    sic_cache: dict,
    active_tickers: set[str],
    limit: int = 0,
) -> int:
    if limit <= 0:
        return 0
    candidates: list[tuple[tuple, str, str]] = []
    for ticker, rec in entity_master.items():
        if not _needs_sector_retry(rec):
            continue
        if rec.get("etf"):
            continue
        cik_variants = _cik_variants(rec.get("cik"))
        if not cik_variants:
            continue
        if _has_cached_sic_value(cik_variants, sic_cache):
            continue
        priority = (
            ticker not in active_tickers,
            -(float(rec.get("gravity") or 0.0)),
            not bool(rec.get("canopy_etfs") or rec.get("etf_overlords")),
            not bool(_COMMON_STOCK_TICKER_RE.fullmatch(ticker)),
            len(ticker),
            ticker,
        )
        candidates.append((priority, ticker, cik_variants[0]))
    candidates.sort(key=lambda item: item[0])
    selected = candidates[:limit]
    ordered_ciks: list[str] = []
    cik_to_tickers: dict[str, list[str]] = {}
    for _, ticker, cik in selected:
        if cik not in cik_to_tickers:
            ordered_ciks.append(cik)
            cik_to_tickers[cik] = []
        cik_to_tickers[cik].append(ticker)

    updated = 0
    for cik in ordered_ciks:
        sic = _fetch_sic(cik)
        for variant in _cik_variants(cik):
            sic_cache[variant] = sic
        if sic:
            updated += len(cik_to_tickers.get(cik) or [])
        time.sleep(_SIC_FETCH_DELAY_SEC)
    return updated


def enrich_unknown_sectors(
    entity_master: dict[str, dict],
    active_tickers: set[str],
    limit: int = 0,
) -> int:
    if limit <= 0:
        return 0
    cache_path = ROOT / ".universe_sector_cache.json"
    sector_cache: dict = {}
    if cache_path.exists():
        try:
            sector_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            sector_cache = {}
    candidates: list[tuple[tuple, str]] = []
    for ticker, rec in entity_master.items():
        if not _needs_sector_retry(rec):
            continue
        if _looks_derivative_like(ticker):
            continue
        if rec.get("etf") and not _sector_from_name(ticker, rec)[0]:
            continue
        priority = (
            ticker not in active_tickers,
            -(float(rec.get("gravity") or 0.0)),
            not bool(rec.get("cik")),
            not bool(rec.get("canopy_etfs") or rec.get("etf_overlords")),
            not bool(_COMMON_STOCK_TICKER_RE.fullmatch(ticker)),
            len(ticker),
            ticker,
        )
        candidates.append((priority, ticker))
    candidates.sort(key=lambda item: item[0])

    updated = 0
    for _, ticker in candidates[:limit]:
        cached = sector_cache.get(ticker) or {}
        sector = cached.get("sector")
        industry = cached.get("industry")
        if not (sector or industry):
            sector, industry = _fetch_yahoo_profile(ticker)
            if sector or industry:
                sector_cache[ticker] = {
                    "sector": sector,
                    "industry": industry,
                    "fetched_at": TODAY,
                }
            time.sleep(0.12)
        yahoo_gics = _classify_yahoo_gics(sector, industry)
        if yahoo_gics:
            entity_master[ticker]["gics"] = yahoo_gics
            entity_master[ticker]["sector"] = yahoo_gics.get("s")
            entity_master[ticker]["sector_source"] = "yahoo_profile"
            entity_master[ticker].pop("sector_inferred", None)
            entity_master[ticker].pop("sector_evidence", None)
            updated += 1

    cache_path.write_text(json.dumps(sector_cache, indent=2), encoding="utf-8")
    return updated


def _cap_gravity_source(rec: dict) -> str:
    etf_weight = float(rec.get("etf_weights_sum") or 0.0)
    return "market_cap+etf" if etf_weight > 0 else "market_cap"


def fallback_gravity_detail(
    ticker: str,
    rec: dict,
    active_tickers: set[str],
) -> tuple[float | None, str]:
    """Provide a durable artifact-side gravity floor when market cap is absent."""
    existing = rec.get("gravity")
    existing_source = str(rec.get("gravity_source") or "")
    if (
        isinstance(existing, (int, float)) and existing > 0
        and not rec.get("mkt_cap_usd")
        and existing_source in {"gics_baseline", "gics+etf"}
        and _normalized_sector(rec) == "unknown"
    ):
        rec.pop("gravity", None)
        rec.pop("gravity_source", None)
        existing = None
    if isinstance(existing, (int, float)) and existing > 0:
        return float(existing), existing_source or (
            _cap_gravity_source(rec) if rec.get("mkt_cap_usd") else "existing"
        )

    ticker = str(ticker or "").upper()
    etf_weight = float(rec.get("etf_weights_sum") or 0.0)
    sector = _normalized_sector(rec)

    if ticker in active_tickers:
        gravity = 2.8 + min(etf_weight, 0.25) * 4.0
        return round(gravity, 2), "recent_activity"

    if sector != "unknown":
        gravity = 1.15 + min(etf_weight, 0.25) * 2.0
        return round(gravity, 2), "gics_baseline" if etf_weight <= 0 else "gics+etf"

    if etf_weight > 0:
        gravity = 1.05 + min(etf_weight, 0.2) * 3.5
        return round(gravity, 2), "etf_anchor"

    if rec.get("cik") and not rec.get("etf") and _COMMON_STOCK_TICKER_RE.fullmatch(ticker):
        return 1.05, "common_stock_baseline"

    return None, "none"


def apply_fallback_gravity(entity_master: dict[str, dict], active_tickers: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ticker, rec in entity_master.items():
        if rec.get("mkt_cap_usd"):
            if rec.get("gravity"):
                rec["gravity_source"] = rec.get("gravity_source") or _cap_gravity_source(rec)
                counts[rec["gravity_source"]] = counts.get(rec["gravity_source"], 0) + 1
            continue

        fallback_gravity, source = fallback_gravity_detail(ticker, rec, active_tickers)
        if fallback_gravity is None:
            continue

        rec["gravity"] = fallback_gravity
        rec["gravity_source"] = source
        rec.setdefault("mkt_cap_tier", "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


# ── Main ──────────────────────────────────────────────────────────────────────
def main(
    enrich_caps: bool = False,
    cap_limit: int = 500,
    cap_offset: int = 0,
    sector_limit: int = 0,
    sic_limit: int = 0,
    recovery_only: bool = False,
) -> None:
    # Load existing entity_master (preserve LEI/ISIN already fetched)
    em_path = ROOT / "entity_master.json"
    entity_master: dict[str, dict] = {}
    if em_path.exists():
        try:
            entity_master = json.loads(em_path.read_text(encoding="utf-8"))
            print(f"build_universe_gravity: loaded {len(entity_master)} existing entities")
        except Exception:
            pass

    # Load enrichment data
    hier = {}
    hier_path = ROOT / "industry_hierarchy_lookup.json"
    if hier_path.exists():
        try:
            hier = json.loads(hier_path.read_text())
        except Exception:
            pass

    sector_lookup = {}
    sector_lookup_path = ROOT / "sector_lookup.json"
    if sector_lookup_path.exists():
        try:
            sector_lookup = json.loads(sector_lookup_path.read_text())
        except Exception:
            pass

    sic_cache: dict = {}
    sic_cache_path = ROOT / ".gics_sic_cache.json"
    if sic_cache_path.exists():
        try:
            sic_cache = json.loads(sic_cache_path.read_text())
        except Exception:
            pass

    bedrock_cache: dict = {}
    bedrock_cache_path = ROOT / ".fmp_bedrock_cache.json"
    if bedrock_cache_path.exists():
        try:
            bedrock_cache = json.loads(bedrock_cache_path.read_text())
        except Exception:
            pass
    long_tail_cache: dict = {}
    if _LONG_TAIL_SECTOR_CACHE.exists():
        try:
            long_tail_payload = json.loads(_LONG_TAIL_SECTOR_CACHE.read_text(encoding="utf-8"))
            if isinstance(long_tail_payload, dict) and isinstance(long_tail_payload.get("symbols"), dict):
                long_tail_cache = long_tail_payload.get("symbols") or {}
            elif isinstance(long_tail_payload, dict):
                long_tail_cache = long_tail_payload
        except Exception:
            long_tail_cache = {}

    # ── Fetch universe sources ────────────────────────────────────────────────
    if recovery_only:
        new_count = 0
        print(f"build_universe_gravity: recovery-only mode on existing artifact ({len(entity_master)} tickers)")
    else:
        sec_tickers    = fetch_sec_tickers()
        nasdaq_symbols = fetch_nasdaq_symbols()

        # Merge into entity_master
        all_tickers = set(sec_tickers) | set(nasdaq_symbols)
        new_count = 0
        for ticker in all_tickers:
            is_new = ticker not in entity_master
            rec = entity_master.setdefault(ticker, {
                "lei":            None,
                "isin":           None,
                "figi":           None,
                "mkt_cap_usd":    None,
                "mkt_cap_tier":   "unknown",
                "etf_weights_sum": 0.0,
                "gravity":        None,
            })

            # Fill from SEC
            if ticker in sec_tickers:
                rec.setdefault("cik",      sec_tickers[ticker]["cik"])
                rec.setdefault("name",     sec_tickers[ticker]["name"])
                rec.setdefault("exchange", sec_tickers[ticker]["exchange"])

            # Fill/update from NASDAQ
            if ticker in nasdaq_symbols:
                rec.setdefault("name", nasdaq_symbols[ticker]["name"])
                rec["etf"] = nasdaq_symbols[ticker].get("etf", False)
                rec.setdefault("nasdaq_category",
                               nasdaq_symbols[ticker].get("nasdaq_category", ""))

            rec["last_updated"] = TODAY
            if is_new:
                new_count += 1

        print(f"build_universe_gravity: universe = {len(entity_master)} tickers "
              f"({new_count} new)")

    active_tickers = load_active_priority_tickers()
    sector_recovered, sector_sources = apply_sector_recovery(
        entity_master,
        hier,
        sector_lookup,
        sic_cache,
        bedrock_cache,
        long_tail_cache,
    )
    if sector_recovered:
        ordered = ", ".join(
            f"{source}={count}"
            for source, count in sorted(sector_sources.items(), key=lambda item: (-item[1], item[0]))
        )
        print(f"build_universe_gravity: {sector_recovered} sectors recovered ({ordered})")

    # ── Optional: enrich market caps for top tickers ──────────────────────────
    if enrich_caps and not recovery_only:
        def _priority_key(ticker: str) -> int:
            if ticker in active_tickers:
                return 0          # recently filed — highest priority
            if entity_master.get(ticker, {}).get("gics"):
                return 1          # GICS classified — inner galaxy
            rec = entity_master.get(ticker, {})
            if rec.get("cik") and not rec.get("etf") and re.fullmatch(r"^[A-Z]{1,4}$", ticker):
                return 2          # plain common stock blue chips / liquid names
            return 3              # outer universe

        candidates = [
            t for t, r in entity_master.items()
            if not r.get("mkt_cap_usd") and not r.get("etf")
        ]
        candidates.sort(key=_priority_key)

        # Apply offset for batch processing
        candidates = candidates[cap_offset:cap_offset + cap_limit]
        print(f"build_universe_gravity: enriching {len(candidates)} market caps "
              f"(offset={cap_offset}) ...")
        enriched = enrich_market_caps(entity_master, candidates)
        print(f"build_universe_gravity: {enriched} market caps fetched")

    sic_enriched = enrich_sic_for_unknowns(entity_master, sic_cache, active_tickers, limit=sic_limit)
    if sic_enriched:
        print(f"build_universe_gravity: {sic_enriched} SIC profiles fetched for unknown sectors")

    sector_enriched = enrich_unknown_sectors(entity_master, active_tickers, limit=sector_limit)
    if sector_enriched:
        print(f"build_universe_gravity: {sector_enriched} Yahoo sector profiles recovered")

    if sic_enriched or sector_enriched:
        sic_cache_path.write_text(json.dumps(sic_cache, indent=2), encoding="utf-8")
        sector_recovered, sector_sources = apply_sector_recovery(
            entity_master,
            hier,
            sector_lookup,
            sic_cache,
            bedrock_cache,
            long_tail_cache,
        )
        if sector_recovered:
            ordered = ", ".join(
                f"{source}={count}"
                for source, count in sorted(sector_sources.items(), key=lambda item: (-item[1], item[0]))
            )
            print(f"build_universe_gravity: post-enrichment sector recovery {sector_recovered} ({ordered})")

    # ── Compute gravity scores where cap is available ─────────────────────────
    promoted_sector_fields = promote_flat_sector_fields(entity_master)
    if promoted_sector_fields:
        print(f"build_universe_gravity: normalized {promoted_sector_fields} flat sector fields into gics metadata")

    if recovery_only:
        print("build_universe_gravity: recovery-only mode skipping gravity recompute")
    else:
        try:
            from gravity_engine import GravityEngine, compute_gravity_batch
            entity_master = compute_gravity_batch(entity_master)
            cap_scored = 0
            for rec in entity_master.values():
                if rec.get("mkt_cap_usd") and rec.get("gravity"):
                    rec["gravity_source"] = _cap_gravity_source(rec)
                    cap_scored += 1
            print(f"build_universe_gravity: {cap_scored} market-cap gravity scores computed")
        except ImportError:
            print("  WARN: gravity_engine.py not found — gravity scores skipped")

        fallback_counts = apply_fallback_gravity(entity_master, active_tickers)
        fallback_total = sum(fallback_counts.values())
        if fallback_total:
            ordered_sources = ", ".join(
                f"{source}={count}"
                for source, count in sorted(fallback_counts.items(), key=lambda item: (-item[1], item[0]))
            )
            print(f"build_universe_gravity: {fallback_total} persisted gravity floors ({ordered_sources})")

    if recovery_only:
        for rec in entity_master.values():
            rec["last_updated"] = TODAY

    # ── Save ──────────────────────────────────────────────────────────────────
    em_path.write_text(
        json.dumps(entity_master, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"build_universe_gravity: {len(entity_master)} entities → entity_master.json")

    # Summary
    with_gics = sum(1 for r in entity_master.values() if r.get("gics"))
    with_cap  = sum(1 for r in entity_master.values() if r.get("mkt_cap_usd"))
    with_grav = sum(1 for r in entity_master.values() if r.get("gravity"))
    etfs      = sum(1 for r in entity_master.values() if r.get("etf"))
    print(f"  GICS classified : {with_gics:,}")
    print(f"  Market cap known: {with_cap:,}")
    print(f"  Gravity scored  : {with_grav:,}")
    print(f"  ETFs (excluded) : {etfs:,}")


if __name__ == "__main__":
    import sys
    enrich = "--enrich-caps" in sys.argv
    recovery_only = "--recovery-only" in sys.argv
    limit  = int(next((a.split("=")[1] for a in sys.argv
                       if a.startswith("--cap-limit=")), "500"))
    offset = int(next((a.split("=")[1] for a in sys.argv
                       if a.startswith("--offset=")), "0"))
    sector_limit = int(next((a.split("=")[1] for a in sys.argv
                             if a.startswith("--sector-limit=")), "0"))
    sic_limit = int(next((a.split("=")[1] for a in sys.argv
                          if a.startswith("--sic-limit=")), "0"))
    main(
        enrich_caps=enrich,
        cap_limit=limit,
        cap_offset=offset,
        sector_limit=sector_limit,
        sic_limit=sic_limit,
        recovery_only=recovery_only,
    )
