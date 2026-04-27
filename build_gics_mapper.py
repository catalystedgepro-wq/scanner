#!/usr/bin/env python3
"""build_gics_mapper.py — Map pipeline tickers to GICS sectors via EDGAR SIC codes.

Reads CIKs from sec_catalyst_latest.csv filing links, fetches SIC from
EDGAR submissions API, maps SIC → GICS sector key, updates sector_lookup.json.

Run after sec_catalyst_list.py so the latest tickers are available.
Cached in .gics_sic_cache.json — only fetches new/unknown tickers.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent

# ── SIC code → GICS sector key ────────────────────────────────────────────────
# Sector keys must match sector_lookup.json existing values:
# tech, biotech, semis, financials, consumer, comms, industrials,
# staples, energy, utilities, real_estate, materials

def sic_to_gics(sic: int) -> str:
    """Map a 4-digit SIC code to a GICS sector key."""
    if      1 <= sic <=  99:  return "staples"         # Crops / Livestock
    elif  100 <= sic <= 799:  return "staples"         # Agriculture & Farming Services → Consumer Staples
    elif  800 <= sic <= 999:  return "materials"       # Forestry / Fishing → Materials
    elif 1000 <= sic <= 1499: return "materials"       # Mining
    elif 1500 <= sic <= 1799: return "industrials"     # Construction
    elif 2000 <= sic <= 2111: return "staples"         # Food & Tobacco
    elif 2100 <= sic <= 2199: return "staples"         # Tobacco
    elif 2200 <= sic <= 2390: return "consumer"        # Textiles/Apparel
    elif 2400 <= sic <= 2499: return "materials"       # Lumber
    elif 2500 <= sic <= 2590: return "consumer"        # Furniture
    elif 2600 <= sic <= 2679: return "materials"       # Paper
    elif 2700 <= sic <= 2796: return "comms"           # Publishing/Media
    elif 2800 <= sic <= 2829: return "materials"       # Chemicals
    elif 2830 <= sic <= 2836: return "biotech"         # Pharma/Biotech
    elif 2840 <= sic <= 2890: return "materials"       # Soap/Cleaners
    elif 2900 <= sic <= 2999: return "energy"          # Petroleum
    elif 3000 <= sic <= 3190: return "materials"       # Rubber/Plastics/Leather
    elif 3200 <= sic <= 3290: return "materials"       # Stone/Glass/Concrete
    elif 3300 <= sic <= 3399: return "materials"       # Primary Metals
    elif 3400 <= sic <= 3490: return "industrials"     # Fabricated Metals
    elif 3500 <= sic <= 3569: return "industrials"     # Industrial Machinery
    elif 3570 <= sic <= 3579: return "tech"            # Computer Hardware
    elif 3580 <= sic <= 3599: return "industrials"     # Industrial Machinery
    elif 3600 <= sic <= 3629: return "industrials"     # Electronic Equipment
    elif 3630 <= sic <= 3659: return "consumer"        # Household Appliances/Electronics
    elif 3660 <= sic <= 3669: return "comms"           # Communications Equipment
    elif 3670 <= sic <= 3679: return "semis"           # Semiconductors
    elif 3680 <= sic <= 3699: return "tech"            # Electronic Components
    elif 3710 <= sic <= 3716: return "consumer"        # Motor Vehicles
    elif 3720 <= sic <= 3729: return "industrials"     # Aircraft/Aerospace
    elif 3730 <= sic <= 3799: return "industrials"     # Ships/Railroad/Misc Transport Equip
    elif 3800 <= sic <= 3827: return "industrials"     # Instruments/Measurement
    elif 3826 <= sic <= 3827: return "biotech"         # Lab instruments (biotech adjacent)
    elif 3828 <= sic <= 3841: return "biotech"         # Medical Instruments
    elif 3842 <= sic <= 3851: return "biotech"         # Surgical/Medical/Optical
    elif 3860 <= sic <= 3879: return "tech"            # Photographic/Measuring
    elif 3900 <= sic <= 3999: return "consumer"        # Misc Manufacturing
    elif 4000 <= sic <= 4099: return "industrials"     # Railroads
    elif 4100 <= sic <= 4299: return "industrials"     # Transit/Trucking
    elif 4300 <= sic <= 4499: return "industrials"     # Air/Water Transport
    elif 4500 <= sic <= 4599: return "industrials"     # Air Transportation
    elif 4600 <= sic <= 4699: return "energy"          # Pipelines
    elif 4700 <= sic <= 4799: return "industrials"     # Transportation Services
    elif 4800 <= sic <= 4899: return "comms"           # Communications/Telephone
    elif 4900 <= sic <= 4991: return "utilities"       # Electric/Gas/Water Utilities
    elif 5000 <= sic <= 5199: return "consumer"        # Wholesale Trade
    elif 5200 <= sic <= 5999: return "consumer"        # Retail Trade
    elif 6000 <= sic <= 6099: return "financials"      # Banks/Savings Institutions
    elif 6100 <= sic <= 6199: return "financials"      # Credit/Lending
    elif 6200 <= sic <= 6289: return "financials"      # Security Brokers
    elif 6300 <= sic <= 6499: return "financials"      # Insurance
    elif 6500 <= sic <= 6599: return "real_estate"     # Real Estate
    elif 6600 <= sic <= 6699: return "financials"      # Combinations
    elif 6700 <= sic <= 6799: return "financials"      # Holding Companies
    elif 7000 <= sic <= 7099: return "consumer"        # Hotels/Lodging
    elif 7200 <= sic <= 7299: return "consumer"        # Personal Services
    elif 7300 <= sic <= 7369: return "industrials"     # Business Services
    elif 7370 <= sic <= 7379: return "tech"            # Computer Programming/Software/Data
    elif 7380 <= sic <= 7389: return "industrials"     # Services/Misc Business
    elif 7500 <= sic <= 7599: return "consumer"        # Auto Repair/Services
    elif 7600 <= sic <= 7699: return "consumer"        # Misc Repair Services
    elif 7800 <= sic <= 7999: return "consumer"        # Entertainment/Recreation
    elif 8000 <= sic <= 8099: return "biotech"         # Health Services (Hospitals/Clinics)
    elif 8100 <= sic <= 8199: return "industrials"     # Legal Services
    elif 8200 <= sic <= 8299: return "consumer"        # Educational Services
    elif 8300 <= sic <= 8399: return "industrials"     # Social Services
    elif 8700 <= sic <= 8742: return "industrials"     # Engineering/Mgmt Services
    elif 8742 <= sic <= 8999: return "tech"            # Management Consulting/Tech Services
    else:                      return "other"


# ── EDGAR API helpers ──────────────────────────────────────────────────────────
UA = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 contact@catalystedge.com")

def _get(url: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
            else:
                print(f"  WARN: fetch failed {url}: {exc}")
    return None


def fetch_sic(cik: str) -> int | None:
    """Return SIC int for a CIK (zero-padded to 10 digits)."""
    padded = cik.zfill(10)
    data = _get(f"https://data.sec.gov/submissions/CIK{padded}.json")
    if not data:
        return None
    try:
        return int(data.get("sic") or 0) or None
    except (ValueError, TypeError):
        return None


def cik_from_link(link: str) -> str | None:
    """Extract CIK from an EDGAR filing URL."""
    m = re.search(r"/edgar/data/(\d+)/", link)
    return m.group(1) if m else None


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
# Explicit compact-form pattern for warrants, units, rights, preferred (user spec)
_PARENT_RESOLUTION_PATTERN = re.compile(
    r"^([A-Z]{1,5})(W|-WT|\.WS|U|-U|R|-R|P|-P)$"
)
_INVALID_SECTOR_VALUES = {"", "unknown", "none", "null"}


def _normalize_sector_value(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("s") or value.get("sector") or ""
    sector = str(value or "").strip().lower()
    return sector if sector not in _INVALID_SECTOR_VALUES else None


def _base_ticker_candidates(ticker: str) -> list[str]:
    cleaned = str(ticker or "").upper().strip()
    if not cleaned:
        return []
    out: list[str] = []
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


def resolve_derivative_sector(ticker: str, lookup_function) -> str:
    """Resolve a derivative ticker by inheriting the first valid parent sector.

    Tries the explicit _PARENT_RESOLUTION_PATTERN first (warrants W/-WT/.WS,
    units U/-U, rights R/-R, preferred P/-P), then falls back to the broader
    _base_ticker_candidates chain for hyphenated / dollar-sign variants.
    """
    # Fast path: explicit compact derivative pattern (user spec)
    match = _PARENT_RESOLUTION_PATTERN.match(ticker.upper())
    if match:
        parent_ticker = match.group(1)
        parent_sector = lookup_function(parent_ticker)
        if parent_sector and str(parent_sector).upper() not in ("UNKNOWN", "NONE", "NULL", "OTHER"):
            return _normalize_sector_value(parent_sector) or "Unknown"

    # Broad fallback: strip any recognised suffix and walk the parent chain
    pending = list(_base_ticker_candidates(ticker))
    seen: set[str] = set()
    while pending:
        parent_ticker = pending.pop(0)
        if parent_ticker in seen:
            continue
        seen.add(parent_ticker)
        parent_sector = _normalize_sector_value(lookup_function(parent_ticker))
        if parent_sector and parent_sector not in ("other",):
            return parent_sector
        pending.extend(candidate for candidate in _base_ticker_candidates(parent_ticker) if candidate not in seen)
    return "Unknown"


def _load_entity_master() -> dict[str, dict]:
    em_path = ROOT / "entity_master.json"
    if not em_path.exists():
        return {}
    try:
        return json.loads(em_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _collect_pipeline_ticker_cik() -> tuple[dict[str, str], list[Path]]:
    import csv

    ticker_cik: dict[str, str] = {}
    csv_sources = sorted(ROOT.glob("sec_catalyst_*.csv"))
    for src in csv_sources:
        try:
            with open(src, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker", "").strip().upper()
                    link = row.get("link", "")
                    cik = cik_from_link(link)
                    if t and cik and t not in ticker_cik:
                        ticker_cik[t] = cik
        except Exception as exc:
            print(f"  WARN: could not read {src.name}: {exc}")
    return ticker_cik, csv_sources


def _lookup_sector(
    ticker: str,
    sector_lookup: dict[str, list[str]],
    entity_master: dict[str, dict],
    ticker_cik: dict[str, str],
    sic_cache: dict[str, int | None],
    *,
    allow_fetch: bool,
) -> str | None:
    cached_sector = _normalize_sector_value(sector_lookup.get(ticker))
    if cached_sector:
        return cached_sector

    rec = entity_master.get(ticker) or {}
    record_sector = _normalize_sector_value((rec.get("gics") or {}).get("s") or rec.get("sector"))
    if record_sector:
        return record_sector

    cik = str(ticker_cik.get(ticker) or rec.get("cik") or "").strip()
    if not cik:
        return None

    sic = sic_cache.get(cik)
    if sic is None and allow_fetch:
        time.sleep(0.12)
        sic = fetch_sic(cik)
        sic_cache[cik] = sic
    if not sic:
        return None
    return _normalize_sector_value(sic_to_gics(sic))


def refresh_derivative_sector_lookup() -> dict[str, str]:
    sl_path = ROOT / "sector_lookup.json"
    sector_lookup: dict[str, list[str]] = {}
    if sl_path.exists():
        try:
            sector_lookup = json.loads(sl_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    entity_master = _load_entity_master()
    cache_path = ROOT / ".gics_sic_cache.json"
    sic_cache: dict[str, int | None] = {}
    if cache_path.exists():
        try:
            sic_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ticker_cik, _ = _collect_pipeline_ticker_cik()
    updates: dict[str, str] = {}

    def lookup(symbol: str) -> str | None:
        return _lookup_sector(
            symbol,
            sector_lookup,
            entity_master,
            ticker_cik,
            sic_cache,
            allow_fetch=False,
        )

    for ticker in ticker_cik:
        current = _normalize_sector_value(sector_lookup.get(ticker))
        # Skip only if already well-classified (not missing and not a dead-end "other")
        if current and current not in ("other",):
            continue
        inherited = resolve_derivative_sector(ticker, lookup)
        inherited_norm = _normalize_sector_value(inherited)
        if inherited_norm and inherited_norm not in ("other",):
            sector_lookup[ticker] = [inherited_norm]
            updates[ticker] = inherited_norm
            print(f"  {ticker} → inherited {inherited_norm} via parent resolution")

    sl_path.write_text(json.dumps(sector_lookup, sort_keys=True, indent=2), encoding="utf-8")
    print(f"build_gics_mapper: derivative refresh wrote {len(updates)} sector inheritances")
    return updates


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    # Load existing sector_lookup
    sl_path = ROOT / "sector_lookup.json"
    sector_lookup: dict[str, list[str]] = {}
    if sl_path.exists():
        try:
            sector_lookup = json.loads(sl_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Load SIC cache (avoids re-hitting EDGAR for known CIKs)
    cache_path = ROOT / ".gics_sic_cache.json"
    sic_cache: dict[str, int | None] = {}
    if cache_path.exists():
        try:
            sic_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    entity_master = _load_entity_master()

    # Collect ticker → CIK from ALL available catalyst CSVs:
    # sec_catalyst_latest.csv + all dated archives (sec_catalyst_YYYY-MM-DD.csv)
    # This grows GICS coverage from ~300 (today only) toward the full ~8,000 active CIK universe.
    ticker_cik, csv_sources = _collect_pipeline_ticker_cik()
    if not csv_sources:
        print("build_gics_mapper: no catalyst CSVs found")
        return

    if not ticker_cik:
        print("build_gics_mapper: no tickers found across catalyst CSVs")
        return

    print(f"build_gics_mapper: scanned {len(csv_sources)} CSV files")

    # Identify tickers needing classification
    to_classify = {t: cik for t, cik in ticker_cik.items()
                   if t not in sector_lookup}

    print(f"build_gics_mapper: {len(ticker_cik)} pipeline tickers, "
          f"{len(sector_lookup)} already classified, "
          f"{len(to_classify)} need EDGAR lookup")

    def lookup(symbol: str) -> str | None:
        return _lookup_sector(
            symbol,
            sector_lookup,
            entity_master,
            ticker_cik,
            sic_cache,
            allow_fetch=True,
        )

    new_count = 0
    for ticker, cik in to_classify.items():
        primary_sector = None

        # Check SIC cache first
        if cik in sic_cache:
            sic = sic_cache[cik]
        else:
            time.sleep(0.12)          # ≤10 req/sec per SEC policy
            sic = fetch_sic(cik)
            sic_cache[cik] = sic

        if sic:
            sector = sic_to_gics(sic)
            if sector != "other":
                primary_sector = sector
            else:
                print(f"  {ticker} CIK={cik} SIC={sic} → (unmapped, checking parent fallback)")
        else:
            print(f"  {ticker} CIK={cik} → no SIC returned, checking parent fallback")

        if not primary_sector:
            inherited_sector = _normalize_sector_value(resolve_derivative_sector(ticker, lookup))
            if inherited_sector:
                sector_lookup[ticker] = [inherited_sector]
                new_count += 1
                print(f"  {ticker} → inherited {inherited_sector} via parent fallback")
                continue

        if primary_sector:
            sector_lookup[ticker] = [primary_sector]
            new_count += 1
            print(f"  {ticker} CIK={cik} SIC={sic} → {primary_sector}")

    # Save updated files
    sl_path.write_text(json.dumps(sector_lookup, sort_keys=True, indent=2),
                       encoding="utf-8")
    cache_path.write_text(json.dumps(sic_cache, indent=2), encoding="utf-8")

    print(f"build_gics_mapper: +{new_count} new classifications → "
          f"{len(sector_lookup)} total in sector_lookup.json")


if __name__ == "__main__":
    main()
