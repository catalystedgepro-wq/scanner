#!/usr/bin/env python3
"""build_gics_hierarchy.py — Map pipeline tickers to the full GICS 4-level taxonomy.

Uses .gics_sic_cache.json (CIK→SIC, built by build_gics_mapper.py) and
sec_catalyst_*.csv (ticker→CIK) to classify each ticker across all 4 GICS levels:
  Sector (11) → Industry Group (24) → Industry (69) → Sub-Industry (158)

Output: industry_hierarchy_lookup.json
  { "AAPL": {"s":"tech","ig":"Technology Hardware & Equipment",
              "i":"Technology Hardware, Storage & Peripherals",
              "si":"Technology Hardware, Storage & Peripherals"} }

Run after build_gics_mapper.py so the SIC cache is populated.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent


# ── GICS Full Taxonomy Table ──────────────────────────────────────────────────
# Each row: (sic_lo, sic_hi, sector_key, industry_group, industry, sub_industry)
# More-specific ranges MUST appear before broader catch-all ranges.
# sector_keys match sector_lookup.json values:
#   tech, biotech, semis, financials, consumer, comms,
#   industrials, staples, energy, utilities, real_estate, materials

_GICS: list[tuple[int, int, str, str, str, str]] = [

    # ── ENERGY ────────────────────────────────────────────────────────────────
    (1380, 1389, "energy", "Energy Equipment & Services",
        "Oil & Gas Equipment & Services", "Oil & Gas Equipment & Services"),
    (1311, 1311, "energy", "Oil, Gas & Consumable Fuels",
        "Oil & Gas Exploration & Production", "Oil & Gas Exploration & Production"),
    (1300, 1379, "energy", "Oil, Gas & Consumable Fuels",
        "Oil & Gas Exploration & Production", "Oil & Gas Exploration & Production"),
    (1390, 1399, "energy", "Oil, Gas & Consumable Fuels",
        "Oil & Gas Exploration & Production", "Oil & Gas Exploration & Production"),
    (1200, 1299, "energy", "Oil, Gas & Consumable Fuels",
        "Coal & Consumable Fuels", "Coal & Consumable Fuels"),
    (2911, 2919, "energy", "Oil, Gas & Consumable Fuels",
        "Oil & Gas Refining & Marketing", "Oil & Gas Refining & Marketing"),
    (2920, 2999, "energy", "Oil, Gas & Consumable Fuels",
        "Coal & Consumable Fuels", "Coal & Consumable Fuels"),
    (4610, 4699, "energy", "Oil, Gas & Consumable Fuels",
        "Oil & Gas Storage & Transportation", "Oil & Gas Storage & Transportation"),

    # ── MATERIALS ─────────────────────────────────────────────────────────────
    # Metals & Mining — specific ores first
    (1040, 1040, "materials", "Metals & Mining", "Metals & Mining", "Gold"),
    (1044, 1044, "materials", "Metals & Mining", "Metals & Mining", "Silver"),
    (1020, 1029, "materials", "Metals & Mining", "Metals & Mining", "Copper"),
    (1000, 1019, "materials", "Metals & Mining", "Metals & Mining", "Diversified Metals & Mining"),
    (1030, 1039, "materials", "Metals & Mining", "Metals & Mining", "Diversified Metals & Mining"),
    (1041, 1043, "materials", "Metals & Mining", "Metals & Mining", "Gold"),
    (1045, 1099, "materials", "Metals & Mining", "Metals & Mining", "Diversified Metals & Mining"),
    (1400, 1499, "materials", "Metals & Mining", "Metals & Mining", "Diversified Metals & Mining"),
    # Paper & Forest Products
    (2410, 2499, "materials", "Paper & Forest Products",
        "Paper & Forest Products", "Forest Products"),
    (2610, 2621, "materials", "Paper & Forest Products",
        "Paper & Forest Products", "Paper Products"),
    # Containers & Packaging
    (2650, 2679, "materials", "Containers & Packaging",
        "Containers & Packaging", "Paper & Plastic Packaging Products & Materials"),
    (3000, 3089, "materials", "Containers & Packaging",
        "Containers & Packaging", "Paper & Plastic Packaging Products & Materials"),
    (3090, 3190, "materials", "Containers & Packaging",
        "Containers & Packaging", "Metal & Glass Containers"),
    # Chemicals — specific first
    (2870, 2879, "materials", "Chemicals", "Chemicals",
        "Fertilizers & Agricultural Chemicals"),
    (2840, 2844, "staples", "Household & Personal Products",
        "Household Products", "Household Products"),     # soap/cleaners → staples
    (2845, 2859, "materials", "Chemicals", "Chemicals", "Specialty Chemicals"),
    (2860, 2869, "materials", "Chemicals", "Chemicals", "Specialty Chemicals"),
    (2880, 2899, "materials", "Chemicals", "Chemicals", "Specialty Chemicals"),
    (2820, 2829, "materials", "Chemicals", "Chemicals", "Specialty Chemicals"),
    (2810, 2819, "materials", "Chemicals", "Chemicals", "Commodity Chemicals"),
    (2800, 2809, "materials", "Chemicals", "Chemicals", "Commodity Chemicals"),
    # Construction Materials
    (3200, 3290, "materials", "Construction Materials",
        "Construction Materials", "Construction Materials"),
    # Metals — steel, copper, aluminum, other
    (3310, 3317, "materials", "Metals & Mining", "Metals & Mining", "Steel"),
    (3318, 3329, "materials", "Metals & Mining", "Metals & Mining", "Steel"),
    (3330, 3334, "materials", "Metals & Mining", "Metals & Mining", "Aluminum"),
    (3335, 3341, "materials", "Metals & Mining", "Metals & Mining", "Copper"),
    (3350, 3357, "materials", "Metals & Mining", "Metals & Mining", "Aluminum"),
    (3360, 3399, "materials", "Metals & Mining", "Metals & Mining",
        "Diversified Metals & Mining"),

    # ── HEALTH CARE ───────────────────────────────────────────────────────────
    (2836, 2836, "biotech", "Pharmaceuticals, Biotech & Life Sciences",
        "Biotechnology", "Biotechnology"),
    (2833, 2835, "biotech", "Pharmaceuticals, Biotech & Life Sciences",
        "Pharmaceuticals", "Pharmaceuticals"),
    (2830, 2832, "biotech", "Pharmaceuticals, Biotech & Life Sciences",
        "Pharmaceuticals", "Pharmaceuticals"),
    (3826, 3827, "biotech", "Pharmaceuticals, Biotech & Life Sciences",
        "Life Sciences Tools & Services", "Life Sciences Tools & Services"),
    (3828, 3841, "biotech", "Health Care Equipment & Services",
        "Health Care Equipment & Supplies", "Health Care Equipment"),
    (3842, 3851, "biotech", "Health Care Equipment & Services",
        "Health Care Equipment & Supplies", "Health Care Supplies"),
    (8000, 8049, "biotech", "Health Care Equipment & Services",
        "Health Care Providers & Services", "Health Care Facilities"),
    (8050, 8059, "biotech", "Health Care Equipment & Services",
        "Health Care Providers & Services", "Health Care Facilities"),
    (8060, 8069, "biotech", "Health Care Equipment & Services",
        "Health Care Providers & Services", "Managed Health Care"),
    (8070, 8099, "biotech", "Health Care Equipment & Services",
        "Health Care Technology", "Health Care Technology"),

    # ── INDUSTRIALS ───────────────────────────────────────────────────────────
    # Capital Goods
    (1500, 1799, "industrials", "Capital Goods",
        "Construction & Engineering", "Construction & Engineering"),
    (3523, 3524, "industrials", "Capital Goods",
        "Machinery", "Agricultural & Farm Machinery"),
    (3530, 3537, "industrials", "Capital Goods",
        "Machinery", "Construction Machinery & Heavy Transportation Equipment"),
    (3400, 3499, "industrials", "Capital Goods",
        "Machinery", "Industrial Machinery & Supplies & Components"),
    (3500, 3529, "industrials", "Capital Goods",
        "Machinery", "Industrial Machinery & Supplies & Components"),
    (3538, 3569, "industrials", "Capital Goods",
        "Machinery", "Industrial Machinery & Supplies & Components"),
    (3580, 3599, "industrials", "Capital Goods",
        "Machinery", "Industrial Machinery & Supplies & Components"),
    (3600, 3629, "industrials", "Capital Goods",
        "Electrical Equipment", "Electrical Components & Equipment"),
    (3720, 3729, "industrials", "Capital Goods",
        "Aerospace & Defense", "Aerospace & Defense"),
    (3760, 3769, "industrials", "Capital Goods",
        "Aerospace & Defense", "Aerospace & Defense"),
    (3730, 3759, "industrials", "Capital Goods",
        "Machinery", "Construction Machinery & Heavy Transportation Equipment"),
    (3770, 3799, "industrials", "Capital Goods",
        "Machinery", "Industrial Machinery & Supplies & Components"),
    (3800, 3825, "industrials", "Capital Goods",
        "Electrical Equipment", "Electrical Components & Equipment"),
    # Transportation
    (4011, 4099, "industrials", "Transportation",
        "Ground Transportation", "Railroads"),
    (4000, 4010, "industrials", "Transportation",
        "Ground Transportation", "Railroads"),
    (4100, 4215, "industrials", "Transportation",
        "Ground Transportation", "Trucking"),
    (4216, 4299, "industrials", "Transportation",
        "Ground Transportation", "Ground Transportation"),
    (4400, 4499, "industrials", "Transportation",
        "Marine Transportation", "Marine Transportation"),
    (4510, 4512, "industrials", "Transportation",
        "Passenger Airlines", "Passenger Airlines"),
    (4513, 4519, "industrials", "Transportation",
        "Air Freight & Logistics", "Air Freight & Logistics"),
    (4520, 4599, "industrials", "Transportation",
        "Passenger Airlines", "Passenger Airlines"),
    (4700, 4789, "industrials", "Transportation",
        "Air Freight & Logistics", "Air Freight & Logistics"),
    (4790, 4799, "industrials", "Transportation",
        "Transportation Infrastructure", "Transportation Infrastructure"),
    # Commercial & Professional Services
    (7310, 7319, "industrials", "Commercial & Professional Services",
        "Professional Services", "Research & Consulting Services"),
    (7320, 7329, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Diversified Support Services"),
    (7330, 7339, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Office Services & Supplies"),
    (7340, 7349, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Environmental & Facilities Services"),
    (7350, 7359, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Diversified Support Services"),
    (7360, 7369, "industrials", "Commercial & Professional Services",
        "Professional Services", "Human Resource & Employment Services"),
    (7380, 7382, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Security & Alarm Services"),
    (7383, 7389, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Diversified Support Services"),
    (7300, 7309, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Diversified Support Services"),
    (8100, 8199, "industrials", "Commercial & Professional Services",
        "Professional Services", "Research & Consulting Services"),
    (8300, 8399, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Diversified Support Services"),
    (8700, 8742, "industrials", "Commercial & Professional Services",
        "Professional Services", "Research & Consulting Services"),
    (4950, 4953, "industrials", "Commercial & Professional Services",
        "Commercial Services & Supplies", "Environmental & Facilities Services"),

    # ── CONSUMER STAPLES ──────────────────────────────────────────────────────
    (2082, 2082, "staples", "Food, Beverage & Tobacco", "Beverages", "Brewers"),
    (2080, 2089, "staples", "Food, Beverage & Tobacco",
        "Beverages", "Soft Drinks & Non-alcoholic Beverages"),
    (2000, 2079, "staples", "Food, Beverage & Tobacco",
        "Food Products", "Packaged Foods & Meats"),
    (2090, 2099, "staples", "Food, Beverage & Tobacco",
        "Food Products", "Packaged Foods & Meats"),
    (2100, 2199, "staples", "Food, Beverage & Tobacco", "Tobacco", "Tobacco"),
    # Consumer Staples Distribution
    (5400, 5411, "staples", "Consumer Staples Distribution & Retail",
        "Consumer Staples Distribution & Retail", "Food Retail"),
    (5412, 5499, "staples", "Consumer Staples Distribution & Retail",
        "Consumer Staples Distribution & Retail", "Food Retail"),

    # ── CONSUMER DISCRETIONARY ────────────────────────────────────────────────
    (2200, 2390, "consumer", "Consumer Durables & Apparel",
        "Textiles, Apparel & Luxury Goods", "Apparel, Accessories & Luxury Goods"),
    (2500, 2590, "consumer", "Consumer Durables & Apparel",
        "Household Durables", "Home Furnishings"),
    (3630, 3639, "consumer", "Consumer Durables & Apparel",
        "Household Durables", "Household Appliances"),
    (3640, 3659, "consumer", "Consumer Durables & Apparel",
        "Leisure Products", "Leisure Products"),
    (3710, 3713, "consumer", "Automobiles & Components",
        "Automobiles", "Automobile Manufacturers"),
    (3714, 3716, "consumer", "Automobiles & Components",
        "Automobile Components", "Automotive Parts & Equipment"),
    (3900, 3999, "consumer", "Consumer Durables & Apparel",
        "Household Durables", "Household Durables"),
    (5000, 5099, "consumer", "Consumer Discretionary Distribution & Retail",
        "Distributors", "Distributors"),
    (5100, 5199, "consumer", "Consumer Discretionary Distribution & Retail",
        "Distributors", "Distributors"),
    (5200, 5299, "consumer", "Consumer Discretionary Distribution & Retail",
        "Specialty Retail", "Home Improvement Retail"),
    (5300, 5399, "consumer", "Consumer Discretionary Distribution & Retail",
        "Broadline Retail", "Broadline Retail"),
    (5500, 5599, "consumer", "Automobiles & Components",
        "Automobile Components", "Automotive Retail"),
    (5600, 5699, "consumer", "Consumer Discretionary Distribution & Retail",
        "Specialty Retail", "Apparel Retail"),
    (5700, 5799, "consumer", "Consumer Discretionary Distribution & Retail",
        "Specialty Retail", "Specialty Stores"),
    (5800, 5812, "consumer", "Consumer Services",
        "Hotels, Restaurants & Leisure", "Restaurants"),
    (5813, 5999, "consumer", "Consumer Discretionary Distribution & Retail",
        "Specialty Retail", "Specialty Stores"),
    (7000, 7099, "consumer", "Consumer Services",
        "Hotels, Restaurants & Leisure", "Hotels, Resorts & Cruise Lines"),
    (7200, 7299, "consumer", "Consumer Services",
        "Diversified Consumer Services", "Diversified Consumer Services"),
    (7500, 7549, "consumer", "Automobiles & Components",
        "Automobile Components", "Automotive Retail"),
    (7550, 7699, "consumer", "Consumer Services",
        "Diversified Consumer Services", "Diversified Consumer Services"),
    (7800, 7819, "consumer", "Consumer Services",
        "Hotels, Restaurants & Leisure", "Movies & Entertainment"),
    (7820, 7999, "consumer", "Consumer Services",
        "Hotels, Restaurants & Leisure", "Casinos & Gaming"),
    (8200, 8299, "consumer", "Consumer Services",
        "Diversified Consumer Services", "Education Services"),

    # ── FINANCIALS ────────────────────────────────────────────────────────────
    (6000, 6019, "financials", "Banks", "Banks", "Diversified Banks"),
    (6020, 6029, "financials", "Banks", "Banks", "Diversified Banks"),
    (6030, 6099, "financials", "Banks", "Banks", "Regional Banks"),
    (6100, 6119, "financials", "Financial Services",
        "Financial Services", "Specialized Finance"),
    (6120, 6139, "financials", "Financial Services",
        "Financial Services", "Commercial & Residential Mortgage Finance"),
    (6140, 6153, "financials", "Financial Services",
        "Consumer Finance", "Consumer Finance"),
    (6154, 6199, "financials", "Financial Services",
        "Financial Services", "Commercial & Residential Mortgage Finance"),
    (6200, 6211, "financials", "Financial Services",
        "Capital Markets", "Investment Banking & Brokerage"),
    (6212, 6289, "financials", "Financial Services",
        "Capital Markets", "Asset Management & Custody Banks"),
    (6300, 6309, "financials", "Insurance", "Insurance", "Multi-line Insurance"),
    (6310, 6319, "financials", "Insurance", "Insurance", "Life & Health Insurance"),
    (6320, 6329, "financials", "Insurance", "Insurance", "Life & Health Insurance"),
    (6330, 6339, "financials", "Insurance", "Insurance",
        "Property & Casualty Insurance"),
    (6340, 6411, "financials", "Insurance", "Insurance", "Insurance Brokers"),

    # ── REAL ESTATE ───────────────────────────────────────────────────────────
    (6500, 6510, "real_estate", "Equity REITs & Real Estate Mgmt",
        "Real Estate Management & Development", "Real Estate Operating Companies"),
    (6511, 6552, "real_estate", "Equity REITs & Real Estate Mgmt",
        "Equity Real Estate Investment Trusts (REITs)", "Diversified REITs"),
    (6552, 6599, "real_estate", "Equity REITs & Real Estate Mgmt",
        "Equity Real Estate Investment Trusts (REITs)", "Diversified REITs"),

    # ── FINANCIALS (holding companies) ───────────────────────────────────────
    (6600, 6726, "financials", "Financial Services",
        "Financial Services", "Multi-Sector Holdings"),
    (6726, 6799, "financials", "Financial Services",
        "Financial Services", "Specialized Finance"),

    # ── INFORMATION TECHNOLOGY ────────────────────────────────────────────────
    (3570, 3579, "tech", "Technology Hardware & Equipment",
        "Technology Hardware, Storage & Peripherals",
        "Technology Hardware, Storage & Peripherals"),
    # Semiconductors — most specific first
    (3672, 3672, "semis", "Semiconductors & Semiconductor Equipment",
        "Semiconductors & Semiconductor Equipment", "Semiconductors"),
    (3674, 3674, "semis", "Semiconductors & Semiconductor Equipment",
        "Semiconductors & Semiconductor Equipment", "Semiconductors"),
    (3670, 3671, "semis", "Semiconductors & Semiconductor Equipment",
        "Semiconductors & Semiconductor Equipment", "Semiconductor Equipment"),
    (3673, 3673, "semis", "Semiconductors & Semiconductor Equipment",
        "Semiconductors & Semiconductor Equipment", "Semiconductors"),
    (3675, 3679, "semis", "Semiconductors & Semiconductor Equipment",
        "Semiconductors & Semiconductor Equipment", "Semiconductors"),
    (3680, 3699, "tech", "Technology Hardware & Equipment",
        "Electronic Equipment, Instruments & Components",
        "Electronic Equipment & Instruments"),
    (3860, 3879, "tech", "Technology Hardware & Equipment",
        "Electronic Equipment, Instruments & Components",
        "Electronic Equipment & Instruments"),
    # Software — most specific SIC first
    (7371, 7371, "tech", "Software & Services", "Software", "Systems Software"),
    (7372, 7372, "tech", "Software & Services", "Software", "Application Software"),
    (7373, 7374, "tech", "Software & Services",
        "IT Services", "Data Processing & Outsourced Services"),
    (7375, 7379, "tech", "Software & Services",
        "IT Services", "Internet Services & Infrastructure"),
    (7370, 7370, "tech", "Software & Services",
        "IT Services", "IT Consulting & Other Services"),
    (8742, 8742, "tech", "Software & Services",
        "IT Services", "IT Consulting & Other Services"),
    (8743, 8999, "tech", "Software & Services",
        "IT Services", "Internet Services & Infrastructure"),

    # ── COMMUNICATION SERVICES ────────────────────────────────────────────────
    (2700, 2796, "comms", "Media & Entertainment", "Media", "Publishing"),
    (3660, 3669, "comms", "Media & Entertainment", "Media", "Broadcasting"),
    (4812, 4812, "comms", "Telecommunication Services",
        "Wireless Telecommunication Services",
        "Wireless Telecommunication Services"),
    (4810, 4811, "comms", "Telecommunication Services",
        "Diversified Telecommunication Services",
        "Integrated Telecommunication Services"),
    (4813, 4813, "comms", "Telecommunication Services",
        "Diversified Telecommunication Services",
        "Integrated Telecommunication Services"),
    (4814, 4829, "comms", "Telecommunication Services",
        "Diversified Telecommunication Services", "Alternative Carriers"),
    (4830, 4833, "comms", "Media & Entertainment", "Media", "Broadcasting"),
    (4840, 4841, "comms", "Media & Entertainment", "Media", "Cable & Satellite"),
    (4800, 4809, "comms", "Telecommunication Services",
        "Diversified Telecommunication Services",
        "Integrated Telecommunication Services"),
    (4890, 4899, "comms", "Telecommunication Services",
        "Diversified Telecommunication Services", "Alternative Carriers"),

    # ── UTILITIES ─────────────────────────────────────────────────────────────
    (4910, 4919, "utilities", "Utilities", "Electric Utilities", "Electric Utilities"),
    (4920, 4931, "utilities", "Utilities", "Gas Utilities", "Gas Utilities"),
    (4932, 4939, "utilities", "Utilities", "Multi-Utilities", "Multi-Utilities"),
    (4940, 4949, "utilities", "Utilities", "Water Utilities", "Water Utilities"),
    (4960, 4989, "utilities", "Utilities", "Multi-Utilities", "Multi-Utilities"),
    (4990, 4991, "utilities", "Utilities",
        "Independent Power Producers & Energy Traders",
        "Independent Power Producers & Energy Traders"),
    (4992, 4999, "utilities", "Utilities",
        "Independent Power Producers & Energy Traders",
        "Renewable Electricity"),
    (4900, 4909, "utilities", "Utilities", "Multi-Utilities", "Multi-Utilities"),
]


def sic_to_gics(sic: int) -> dict:
    """Return full GICS classification for a 4-digit SIC code.

    Returns dict with keys s, ig, i, si (sector, industry_group, industry, sub_industry).
    Returns {} if unmapped.
    """
    for lo, hi, s, ig, i, si in _GICS:
        if lo <= sic <= hi:
            return {"s": s, "ig": ig, "i": i, "si": si}
    return {}


def cik_from_link(link: str) -> str | None:
    m = re.search(r"/edgar/data/(\d+)/", link)
    return m.group(1) if m else None


def main() -> None:
    # Load SIC cache (CIK → SIC int)
    cache_path = ROOT / ".gics_sic_cache.json"
    sic_cache: dict[str, int | None] = {}
    if cache_path.exists():
        try:
            sic_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: could not load SIC cache: {exc}")

    if not sic_cache:
        print("build_gics_hierarchy: no SIC cache — run build_gics_mapper.py first")
        return

    # Build ticker → CIK from all catalyst CSVs
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

    if not ticker_cik:
        print("build_gics_hierarchy: no tickers found in catalyst CSVs")
        return

    # Classify each ticker
    out: dict[str, dict] = {}
    unmapped = 0
    for ticker, cik in ticker_cik.items():
        sic = sic_cache.get(cik)
        if not sic:
            unmapped += 1
            continue
        gics = sic_to_gics(sic)
        if gics:
            out[ticker] = gics

    out_path = ROOT / "industry_hierarchy_lookup.json"
    out_path.write_text(json.dumps(out, sort_keys=True, indent=2), encoding="utf-8")

    print(
        f"build_gics_hierarchy: {len(ticker_cik)} tickers → "
        f"{len(out)} classified, {unmapped} no SIC data"
    )
    # Distribution by sub-industry
    si_dist = Counter(v["si"] for v in out.values())
    ig_dist = Counter(v["ig"] for v in out.values())
    print(f"\nTop 10 Industry Groups:")
    for ig, cnt in ig_dist.most_common(10):
        print(f"  {cnt:4d}  {ig}")
    print(f"\nTop 15 Sub-Industries:")
    for si, cnt in si_dist.most_common(15):
        print(f"  {cnt:4d}  {si}")


if __name__ == "__main__":
    main()
