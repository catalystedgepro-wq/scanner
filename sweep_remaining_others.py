#!/usr/bin/env python3
"""sweep_remaining_others.py — Second-pass sweep for still-unresolved "other" entities.

Strategy (for the ~320 that sweep_adr_otc_sectors.py couldn't resolve):
  1. EDGAR SIC lookup for entities with known CIKs → sic_to_gics
  2. Expanded name heuristic (more keywords, foreign telco, fund types, etc.)

Run AFTER sweep_adr_otc_sectors.py. Writes to sector_lookup.json.
Then deploy + restart.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
UA   = "CatalystEdge/1.0 contact@catalystedge.com"


# ── SIC → sector key (from build_gics_mapper.py) ─────────────────────────────
def sic_to_sector(sic: int) -> str | None:
    if      1 <= sic <=  99:  return "staples"
    elif  100 <= sic <= 799:  return "staples"
    elif  800 <= sic <= 999:  return "materials"
    elif 1000 <= sic <= 1499: return "materials"
    elif 1500 <= sic <= 1799: return "industrials"
    elif 2000 <= sic <= 2111: return "staples"
    elif 2100 <= sic <= 2199: return "staples"
    elif 2200 <= sic <= 2390: return "consumer"
    elif 2400 <= sic <= 2499: return "materials"
    elif 2500 <= sic <= 2590: return "consumer"
    elif 2600 <= sic <= 2679: return "materials"
    elif 2700 <= sic <= 2796: return "comms"
    elif 2800 <= sic <= 2829: return "materials"
    elif 2830 <= sic <= 2836: return "biotech"
    elif 2840 <= sic <= 2890: return "materials"
    elif 2900 <= sic <= 2999: return "energy"
    elif 3000 <= sic <= 3190: return "materials"
    elif 3200 <= sic <= 3290: return "materials"
    elif 3300 <= sic <= 3399: return "materials"
    elif 3400 <= sic <= 3490: return "industrials"
    elif 3500 <= sic <= 3569: return "industrials"
    elif 3570 <= sic <= 3579: return "tech"
    elif 3580 <= sic <= 3599: return "industrials"
    elif 3600 <= sic <= 3629: return "industrials"
    elif 3630 <= sic <= 3659: return "consumer"
    elif 3660 <= sic <= 3669: return "comms"
    elif 3670 <= sic <= 3679: return "semis"
    elif 3680 <= sic <= 3699: return "tech"
    elif 3710 <= sic <= 3716: return "consumer"
    elif 3720 <= sic <= 3729: return "industrials"
    elif 3730 <= sic <= 3799: return "industrials"
    elif 3800 <= sic <= 3827: return "industrials"
    elif 3826 <= sic <= 3827: return "biotech"
    elif 3828 <= sic <= 3851: return "biotech"
    elif 3842 <= sic <= 3851: return "biotech"
    elif 3860 <= sic <= 3879: return "tech"
    elif 3900 <= sic <= 3999: return "consumer"
    elif 4000 <= sic <= 4099: return "industrials"
    elif 4100 <= sic <= 4299: return "industrials"
    elif 4300 <= sic <= 4499: return "industrials"
    elif 4500 <= sic <= 4599: return "industrials"
    elif 4600 <= sic <= 4699: return "energy"
    elif 4700 <= sic <= 4799: return "industrials"
    elif 4800 <= sic <= 4899: return "comms"
    elif 4900 <= sic <= 4991: return "utilities"
    elif 5000 <= sic <= 5199: return "consumer"
    elif 5200 <= sic <= 5999: return "consumer"
    elif 6000 <= sic <= 6099: return "financials"
    elif 6100 <= sic <= 6199: return "financials"
    elif 6200 <= sic <= 6289: return "financials"
    elif 6300 <= sic <= 6499: return "financials"
    elif 6500 <= sic <= 6599: return "real_estate"
    elif 6600 <= sic <= 6699: return "financials"
    elif 6700 <= sic <= 6799: return "financials"
    elif 7000 <= sic <= 7099: return "consumer"
    elif 7200 <= sic <= 7299: return "consumer"
    elif 7300 <= sic <= 7369: return "industrials"
    elif 7370 <= sic <= 7379: return "tech"
    elif 7380 <= sic <= 7389: return "industrials"
    elif 7500 <= sic <= 7599: return "consumer"
    elif 7600 <= sic <= 7699: return "consumer"
    elif 7800 <= sic <= 7999: return "consumer"
    elif 8000 <= sic <= 8099: return "biotech"
    elif 8100 <= sic <= 8199: return "industrials"
    elif 8200 <= sic <= 8299: return "consumer"
    elif 8300 <= sic <= 8399: return "industrials"
    elif 8700 <= sic <= 8742: return "industrials"
    elif 8742 <= sic <= 8999: return "tech"
    return None  # explicitly "other" in SIC table — don't store as resolved


def fetch_sic(cik: str) -> int | None:
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        sic = int(d.get("sic") or 0)
        return sic or None
    except Exception:
        return None


# ── Expanded heuristic name classifier ───────────────────────────────────────
_NAME_RULES: list[tuple[list[str], str]] = [
    # Semis — before generic tech
    (["SEMICONDUCTOR", "SEMICON", "MICROCHIP", "WAFER", "CHIP MAKER"],   "semis"),
    # Biotech / Healthcare
    (["PHARMA", "PHARMACEUTICAL", "BIOTECH", "THERAPEUTICS", "BIOSCIENCE",
      "GENOMIC", "ONCOLOGY", "IMMUNOLOGY", "GENOME", "BIOPHARMA"],       "biotech"),
    (["HEALTH CARE", "HEALTHCARE", "MEDICAL", "CLINIC", "HOSPITAL",
      "DIAGNOSTICS", "DENTAL", "OPTOMETRY", "OPHTHALM", "SURGICAL",
      "SENIOR LIVING", "SENIOR CARE", "ASSISTED LIVING", "NURSING HOME",
      "AGED CARE", "ELDER CARE", "REHABILITATION", "LIFE SCIENCES"],     "biotech"),
    # Tech
    (["SOFTWARE", "SAAS", "CLOUD", "ARTIFICIAL INTELLIGENCE",
      "MACHINE LEARNING", "CYBERSECURITY", "CYBER", "ANALYTICS",
      "INFORMATION TECHNOLOGY", "IT SERVICES", "IT CONSULTING",
      "COMPUTER SYSTEM", "COMPUTER SERVICE", "ENTERPRISE SOFTWARE",
      "DIGITAL TRANSFORMATION", "ECOMMERCE", "E-COMMERCE",
      "ONLINE MARKETPLACE", "FINTECH", "INSURTECH"],                     "tech"),
    (["TECH", "DIGITAL", "DATA CENTER", "INTERNET SERVICES",
      "WEB SERVICES", "PC PARTNER", "SEMICONDUCTOR"],                    "tech"),
    # Real estate
    (["REIT", "REALTY", "REAL ESTATE", "PROPERTIES PLC", "PROPERTIES LTD",
      "PROPERTIES CO", "RESIDENTIAL PROP", "COMMERCIAL PROP",
      "PROPERTY TRUST", "PROPERTY GROUP", "PROPERTY FUND",
      "LAND DEVELOPER", "DEVELOPER", "PATTANA"],                         "real_estate"),
    # Materials — precious metals first
    (["GOLD CORP", "GOLD MINES", "SILVER CORP", "SILVER MINES",
      "RARE EARTH", "RARE EARTHS", "RARE METAL",
      "LITHIUM", "COBALT", "URANIUM", "PLATINUM", "PALLADIUM",
      "ZINC", "NICKEL", "IRON ORE", "VANADIUM", "TUNGSTEN"],             "materials"),
    (["GOLD", "SILVER", "COPPER", "MINING", "MINERALS", "RESOURCES",
      "METALS", "STEEL", "CEMENT", "CHEMICALS", "FERTILIZER",
      "BAKELITE", "PLASTICS", "RUBBER", "PAPER", "PACKAGING",
      "FOREST PRODUCT", "PULP", "TIMBER", "METALLIUM", "METALLURG"],    "materials"),
    # Energy
    (["OIL", "GAS", "PETROLEUM", "DRILLING", "EXPLORATION", "LNG",
      "PIPELINE", "REFIN", "HYDROCARBON", "FUEL", "FUELS",
      "GASLOG", "MIDSTREAM", "UPSTREAM", "DOWNSTREAM",
      "RENEWABLE ENERGY", "SOLAR ENERGY", "WIND ENERGY",
      "CLEAN ENERGY", "GREEN ENERGY"],                                   "energy"),
    # Utilities (after energy to avoid solar/wind overlap)
    (["ELECTRIC UTIL", "WATER UTIL", "GAS UTIL", "UTILITY", "UTILITIES",
      "NUCLEAR POWER", "HYDRO POWER", "POWER GRID", "GRID",
      "WATER WORKS", "SEWAGE"],                                          "utilities"),
    # Comms / Media
    (["TELECOM", "TELECOMMUNICATIONS", "TELEKOMUNIKASI", "TELEKOMUNIK",
      "WIRELESS", "CABLE", "BROADCAST", "SATELLITE", "STREAMING",
      "MEDIA GROUP", "PUBLISHING", "PUBLISHER", "NEWSPAPER",
      "MAGAZINE", "ENTERTAINMENT MEDIA", "STUDIO", "MOVIES",
      "ANIMATION", "SPRINGER NATURE", "SPRINGER"],                      "comms"),
    # Financials — investment funds & BDCs first
    (["EQUITY FUND", "HIGH YIELD FUND", "BOND FUND", "INCOME FUND",
      "STRATEGIES FUND", "INNOVATION FUND", "HEDGE FUND",
      "CLOSED-END FUND", "CLOSED END FUND", "INTERVAL FUND",
      "BDC", "BUSINESS DEVELOPMENT", "UNICORN FUND",
      "JAPAN EQUITY", "EMERGING MARKET"],                               "financials"),
    (["BANCORP", "BANCSHARES", "BANQUE", "BANCO", "BANCA",
      "INSURANCE", "INSUR", "REINSUR", "REINSURANCE",
      "CAPITAL MANAGEMENT", "ASSET MANAGEMENT", "INVESTMENT TRUST",
      "INVESTMENT MANAGEMENT", "SECURITIES", "BROKERAGE",
      "CAPITAL PARTNERS", "CAPITAL GROUP", "CAPITAL PLC",
      "PERSHING", "FUNDRISE"],                                          "financials"),
    (["BANK", "FINANCIAL", "FINANCE", "CREDIT", "LENDING",
      "MORTGAGE", "INVESTMENT", "TRUST COMPANY",
      "WEALTH MANAGEMENT", "CAPITAL"],                                  "financials"),
    # Industrials
    (["AEROSPACE", "DEFENSE", "DEFENCE", "AVIATION", "AIRCRAFT",
      "SHIPBUILDING", "SHIP BUILDING", "SHIPYARD", "MARINE VESSEL",
      "RAIL", "SHIPPING", "LOGISTICS", "FREIGHT", "TRUCKING",
      "CONSTRUCTION", "ENGINEERING", "INFRASTRUCTURE",
      "FIRE PROTECTION", "SAFETY SYSTEM", "ALARM", "MINIMAX"],         "industrials"),
    (["INDUSTRIAL", "MANUFACTURING", "MACHINERY", "EQUIPMENT",
      "AUTOMATION", "ROBOTICS", "TOOLS", "COMPONENTS",
      "BEARINGS", "SPRINGS", "SCHAEFFLER", "NHK SPRING"],              "industrials"),
    # Staples
    (["FOOD", "BEVERAGE", "BEER", "SPIRITS", "WINE", "TOBACCO",
      "HOUSEHOLD PRODUCTS", "PERSONAL CARE", "COSMETIC", "HYGIENE",
      "AGRICULTURE", "AGRI", "FARM", "NUTRITION", "DAIRY", "MEAT",
      "SUPERMARKET", "GROCERY", "PACKAGED FOOD", "GUZMAN"],            "staples"),
    # Consumer discretionary
    (["CANNABIS", "CANNABIST", "MARIJUANA", "CBD", "HEMP"],            "consumer"),
    (["RETAIL", "CASINO", "GAMING", "HOTEL", "RESORT", "RESTAURANT",
      "FAST FOOD", "LEISURE", "TOURISM", "TRAVEL", "FASHION",
      "APPAREL", "CLOTHING", "FOOTWEAR", "SPORTING", "AUTO", "MOTOR",
      "ELECTRONICS RETAIL", "CONSUMER ELECTRONICS",
      "ENTERTAINMENT", "AMUSEMENT", "THEME PARK",
      "FREELANCER", "MARKETPLACE"],                                    "consumer"),
]


def heuristic_name_classification(company_name: str) -> str | None:
    name = company_name.upper()
    for keywords, sector_key in _NAME_RULES:
        if any(kw in name for kw in keywords):
            return sector_key
    return None


# ── Main ─────────────────────────────────────────────────────────────────────
def main(dry_run: bool = False) -> None:
    em_path    = ROOT / "entity_master.json"
    sl_path    = ROOT / "sector_lookup.json"
    cache_path = ROOT / ".gics_sic_cache.json"

    entity_master: dict = json.loads(em_path.read_text(encoding="utf-8")) if em_path.exists() else {}
    sector_lookup: dict = json.loads(sl_path.read_text(encoding="utf-8")) if sl_path.exists() else {}
    sic_cache: dict     = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    def current_sl(ticker: str) -> str | None:
        v = sector_lookup.get(ticker)
        if not v:
            return None
        s = str(v[0] if isinstance(v, list) else v).strip().lower()
        return s if s and s not in ("other", "unknown", "none", "null", "") else None

    def current_em_sector(rec: dict) -> str:
        gics = rec.get("gics") if isinstance(rec.get("gics"), dict) else {}
        return str((gics.get("s") if gics else "") or rec.get("sector") or "").strip().lower()

    # Collect still-unresolved "other" targets
    targets = [
        (t, rec)
        for t, rec in entity_master.items()
        if current_em_sector(rec) == "other" and not current_sl(t)
    ]

    print(f"sweep_remaining_others: {len(targets)} still-unresolved targets")

    if dry_run:
        print("  [DRY RUN] First 10:")
        for t, r in targets[:10]:
            print(f"    {t:12s}  CIK={r.get('cik','—'):12s}  {r.get('name','')[:50]}")
        return

    resolved_sic       = 0
    resolved_heuristic = 0
    unresolvable       = 0

    for i, (ticker, rec) in enumerate(targets):
        name = str(rec.get("name") or "").strip()
        cik  = str(rec.get("cik") or "").strip()
        sector = None

        # 1. EDGAR SIC lookup
        if cik:
            sic = sic_cache.get(cik)
            if sic is None:
                time.sleep(0.12)
                sic = fetch_sic(cik)
                sic_cache[cik] = sic

            if sic:
                sector = sic_to_sector(sic)
                if sector:
                    resolved_sic += 1
                    label = f"edgar_sic({sic})"

        # 2. Expanded heuristic
        if not sector:
            sector = heuristic_name_classification(name)
            if sector:
                resolved_heuristic += 1
                label = "heuristic"

        if sector:
            sector_lookup[ticker] = [sector]
            print(f"  [{i+1:4d}] {ticker:12s} → {sector:15s}  ({label}) {name[:50]}")
        else:
            unresolvable += 1
            print(f"  [{i+1:4d}] {ticker:12s}   UNRESOLVABLE  {name[:50]}")

        # Checkpoint every 50
        if (i + 1) % 50 == 0:
            sl_path.write_text(
                json.dumps(sector_lookup, sort_keys=True, separators=(",", ":")),
                encoding="utf-8"
            )
            cache_path.write_text(json.dumps(sic_cache, indent=2), encoding="utf-8")
            print(f"  --- checkpoint [{i+1}/{len(targets)}] "
                  f"sic={resolved_sic} heuristic={resolved_heuristic} "
                  f"unresolvable={unresolvable} ---")

    # Final save
    sl_path.write_text(
        json.dumps(sector_lookup, sort_keys=True, separators=(",", ":")),
        encoding="utf-8"
    )
    cache_path.write_text(json.dumps(sic_cache, indent=2), encoding="utf-8")

    print(f"\nsweep_remaining_others: complete")
    print(f"  Resolved via EDGAR SIC : {resolved_sic}")
    print(f"  Resolved via heuristic : {resolved_heuristic}")
    print(f"  Still unresolvable     : {unresolvable}")
    print(f"  Total sector_lookup    : {len(sector_lookup)}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
