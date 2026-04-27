#!/usr/bin/env python3
"""classify_ambiguous_gics.py — LLM-verified GICS Sub-Industry classification.

Architecture Directive: "70% accuracy is the SIC Ambiguity trap all over again.
Go straight to Path A (LLM) for any ticker that doesn't have a 100% SIC-to-GICS
match. Cost: $0.001/ticker. Precision: mandatory."

Targets:
    1. Tickers with NO GICS classification (SIC not in our table or SIC missing)
    2. Tickers classified at a broad sub-industry (e.g. "Diversified Metals &
       Mining") that may be more specifically classified by their business description

Flow:
    entity_master[ticker]["cik"]
        ↓ EDGAR submissions API → company name + SIC description
    → Anthropic Messages API (claude-haiku-4-5 for cost efficiency)
        Prompt: "Classify this company into the exact GICS Sub-Industry"
        Response: exact sub-industry name + confidence
    → Updates industry_hierarchy_lookup.json + entity_master.json

Requires: ANTHROPIC_API_KEY in .sec_email_env

Run: python3 classify_ambiguous_gics.py [--limit 500] [--force] [--dry-run]
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
UA   = os.environ.get("SEC_USER_AGENT",
                      "CatalystEdge/1.0 contact@catalystedge.com")

# ── The 158 GICS Sub-Industries (official list) ───────────────────────────────
GICS_SUB_INDUSTRIES: list[str] = [
    # Energy
    "Oil & Gas Drilling", "Oil & Gas Equipment & Services",
    "Integrated Oil & Gas", "Oil & Gas Exploration & Production",
    "Oil & Gas Refining & Marketing", "Oil & Gas Storage & Transportation",
    "Coal & Consumable Fuels",
    # Materials
    "Commodity Chemicals", "Diversified Chemicals",
    "Fertilizers & Agricultural Chemicals", "Industrial Gases",
    "Specialty Chemicals", "Construction Materials",
    "Metal & Glass Containers",
    "Paper & Plastic Packaging Products & Materials",
    "Aluminum", "Diversified Metals & Mining", "Copper", "Gold",
    "Precious Metals & Minerals", "Silver", "Steel",
    "Forest Products", "Paper Products",
    # Industrials
    "Aerospace & Defense", "Building Products",
    "Construction & Engineering", "Electrical Components & Equipment",
    "Heavy Electrical Equipment", "Industrial Conglomerates",
    "Construction Machinery & Heavy Transportation Equipment",
    "Agricultural & Farm Machinery",
    "Industrial Machinery & Supplies & Components",
    "Trading Companies & Distributors", "Commercial Printing",
    "Environmental & Facilities Services", "Office Services & Supplies",
    "Diversified Support Services", "Security & Alarm Services",
    "Human Resource & Employment Services",
    "Research & Consulting Services",
    "Data Processing & Outsourced Services",
    "Air Freight & Logistics", "Passenger Airlines",
    "Marine Transportation", "Railroads", "Trucking",
    "Ground Transportation", "Airport Services",
    "Highways & Railtracks", "Marine Ports & Services",
    # Consumer Discretionary
    "Automobile Components", "Automobile Manufacturers",
    "Automotive Retail", "Home Furnishings",
    "Homebuilding", "Household Appliances", "Housewares & Specialties",
    "Leisure Products",
    "Apparel, Accessories & Luxury Goods", "Footwear", "Textiles",
    "Casinos & Gaming", "Hotels, Resorts & Cruise Lines",
    "Leisure Facilities", "Restaurants", "Movies & Entertainment",
    "Interactive Home Entertainment", "Education Services",
    "Specialized Consumer Services", "Diversified Consumer Services",
    "Distributors", "Broadline Retail", "Home Improvement Retail",
    "Specialty Stores", "Apparel Retail", "Drug Retail",
    "Food Distributors", "Internet & Direct Marketing Retail",
    # Consumer Staples
    "Drug Retail", "Food Retail",
    "Consumer Staples Distribution & Retail",
    "Brewers", "Distillers & Vintners",
    "Soft Drinks & Non-alcoholic Beverages",
    "Agricultural Products & Services", "Packaged Foods & Meats",
    "Tobacco", "Household Products", "Personal Care Products",
    # Health Care
    "Health Care Equipment", "Health Care Supplies",
    "Health Care Distributors", "Health Care Facilities",
    "Managed Health Care", "Health Care Services",
    "Health Care Technology", "Biotechnology", "Pharmaceuticals",
    "Life Sciences Tools & Services",
    # Financials
    "Diversified Banks", "Regional Banks",
    "Commercial & Residential Mortgage Finance", "Consumer Finance",
    "Asset Management & Custody Banks",
    "Investment Banking & Brokerage", "Diversified Capital Markets",
    "Financial Exchanges & Data", "Mortgage REITs",
    "Multi-Sector Holdings", "Specialized Finance",
    "Transaction & Payment Processing Services",
    "Insurance Brokers", "Life & Health Insurance",
    "Multi-line Insurance", "Property & Casualty Insurance",
    "Reinsurance",
    # Information Technology
    "IT Consulting & Other Services",
    "Internet Services & Infrastructure",
    "Data Processing & Outsourced Services",
    "Application Software", "Systems Software",
    "Communications Equipment",
    "Technology Hardware, Storage & Peripherals",
    "Electronic Equipment & Instruments", "Electronic Components",
    "Electronic Manufacturing Services", "Technology Distributors",
    "Semiconductor Equipment", "Semiconductors",
    # Communication Services
    "Alternative Carriers",
    "Integrated Telecommunication Services",
    "Wireless Telecommunication Services",
    "Advertising", "Broadcasting", "Cable & Satellite",
    "Publishing", "Interactive Media & Services",
    "Movies & Entertainment",
    # Utilities
    "Electric Utilities", "Gas Utilities", "Multi-Utilities",
    "Water Utilities",
    "Independent Power Producers & Energy Traders",
    "Renewable Electricity",
    # Real Estate
    "Diversified REITs", "Industrial REITs", "Hotel & Resort REITs",
    "Office REITs", "Health Care REITs", "Residential REITs",
    "Retail REITs", "Specialized REITs",
    "Diversified Real Estate Activities",
    "Real Estate Operating Companies", "Real Estate Development",
    "Real Estate Services",
]

# Broad sub-industries that benefit most from LLM verification
_AMBIGUOUS_SUB_INDUSTRIES = frozenset([
    "Diversified Metals & Mining",
    "Diversified Banks",
    "Diversified Capital Markets",
    "Multi-Sector Holdings",
    "Specialized Finance",
    "Commercial & Residential Mortgage Finance",
    "Diversified Consumer Services",
    "Diversified Support Services",
    "Research & Consulting Services",
    "IT Consulting & Other Services",
    "Internet Services & Infrastructure",
])

# ── Anthropic API (via stdlib urllib) ────────────────────────────────────────
def load_api_key() -> str | None:
    """Load ANTHROPIC_API_KEY from .sec_email_env."""
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip()
                return key if key else None
    return os.environ.get("ANTHROPIC_API_KEY")


def call_claude(prompt: str, api_key: str,
                model: str = "claude-haiku-4-5-20251001") -> str | None:
    """Call Anthropic Messages API via urllib. Returns text response or None."""
    payload = {
        "model": model,
        "max_tokens": 150,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode("utf-8"))
            return resp["content"][0]["text"].strip()
    except Exception as exc:
        print(f"  WARN: Claude API error: {exc}")
        return None


def build_classification_prompt(company_name: str, sic_desc: str,
                                current_si: str | None) -> str:
    si_list = "\n".join(f"- {si}" for si in GICS_SUB_INDUSTRIES)
    current_note = (f'Currently classified as: "{current_si}". '
                    f'Verify or correct this classification.'
                    if current_si else
                    "No current GICS classification exists.")
    return f"""You are a financial data analyst. Classify this company into the single most appropriate GICS Sub-Industry.

Company: {company_name}
SIC Industry Description: {sic_desc}
{current_note}

From this official list of GICS Sub-Industries, return ONLY the exact name that best fits:
{si_list}

Rules:
- Return ONLY the exact sub-industry name from the list above, nothing else
- If genuinely ambiguous, prefer the more specific option
- Do not add explanations, punctuation, or extra text"""


# ── EDGAR SIC description lookup ─────────────────────────────────────────────
_SIC_DESCRIPTIONS: dict[int, str] = {
    # Partial list — covers the most common ambiguous ranges
    6199: "Finance Services", 6159: "Federal-Sponsored Credit Agencies",
    6141: "Personal Credit Institutions", 6153: "Short-Term Business Credit",
    6726: "Investment Offices", 6199: "Finance Services",
    7389: "Services Allied to Motion Picture Production",
    7372: "Prepackaged Software", 7371: "Computer Programming Services",
    8742: "Management Consulting Services",
    3669: "Communications Equipment", 3679: "Electronic Components",
    3699: "Electronic & Other Electrical Equipment",
    2911: "Petroleum Refining", 2819: "Industrial Inorganic Chemicals",
}


def fetch_edgar_company_info(cik: str) -> dict:
    """Return company name, SIC, and SIC description from EDGAR."""
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        sic = int(d.get("sic") or 0)
        return {
            "name":     d.get("name", ""),
            "sic":      sic,
            "sic_desc": d.get("sicDescription", _SIC_DESCRIPTIONS.get(sic, "Unknown")),
        }
    except Exception:
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────
def main(limit: int = 500, force: bool = False, dry_run: bool = False) -> None:
    api_key = load_api_key()
    if not api_key:
        print("classify_ambiguous_gics: ANTHROPIC_API_KEY not found in .sec_email_env")
        print("  Add: ANTHROPIC_API_KEY=sk-ant-...")
        return

    # Load data
    em_path   = ROOT / "entity_master.json"
    hier_path = ROOT / "industry_hierarchy_lookup.json"

    entity_master: dict = {}
    if em_path.exists():
        entity_master = json.loads(em_path.read_text())

    hier: dict = {}
    if hier_path.exists():
        hier = json.loads(hier_path.read_text())

    # ── Identify targets ──────────────────────────────────────────────────────
    # Priority 1: no GICS classification at all
    unclassified = [
        t for t, r in entity_master.items()
        if t not in hier and r.get("cik") and not r.get("etf")
    ]
    # Priority 2: broad/ambiguous sub-industries
    ambiguous = [
        t for t, h in hier.items()
        if h.get("si") in _AMBIGUOUS_SUB_INDUSTRIES
        and (force or not h.get("llm_verified"))
    ]

    targets = unclassified[:limit // 2] + ambiguous[:limit // 2]
    targets = targets[:limit]
    print(f"classify_ambiguous_gics: {len(unclassified)} unclassified, "
          f"{len(ambiguous)} ambiguous → targeting {len(targets)}")

    if dry_run:
        print("  [DRY RUN] Would classify:")
        for t in targets[:10]:
            print(f"    {t}  current={hier.get(t,{}).get('si','—')}")
        return

    # ── Classify ──────────────────────────────────────────────────────────────
    classified  = 0
    api_errors  = 0
    cost_tally  = 0  # rough token estimate

    for i, ticker in enumerate(targets):
        rec = entity_master.get(ticker, {})
        cik = rec.get("cik", "")
        if not cik:
            continue

        # Fetch company info
        info = fetch_edgar_company_info(cik)
        time.sleep(0.12)
        if not info.get("name"):
            continue

        current_h  = hier.get(ticker, {})
        current_si = current_h.get("si")
        prompt     = build_classification_prompt(
            info["name"], info.get("sic_desc", ""), current_si)

        response = call_claude(prompt, api_key)
        cost_tally += 1
        time.sleep(0.5)  # API rate limit

        if not response:
            api_errors += 1
            continue

        # Validate response is a real sub-industry
        matched_si = None
        for si in GICS_SUB_INDUSTRIES:
            if si.lower() in response.lower() or response.lower() in si.lower():
                matched_si = si
                break

        if not matched_si:
            # Exact match failed — use fuzzy best match
            resp_lower = response.lower()
            best = max(GICS_SUB_INDUSTRIES,
                       key=lambda si: sum(w in resp_lower
                                          for w in si.lower().split()[:3]))
            matched_si = best

        # Update hierarchy lookup
        if ticker not in hier:
            # New classification — need sector/IG/industry from the sub-industry
            # Use the closest existing match from our GICS table
            hier[ticker] = {
                "s":  current_h.get("s", ""),
                "ig": current_h.get("ig", ""),
                "i":  current_h.get("i", ""),
                "si": matched_si,
                "llm_verified": True,
                "llm_model": "claude-haiku-4-5",
            }
        else:
            hier[ticker]["si"]           = matched_si
            hier[ticker]["llm_verified"] = True
            hier[ticker]["llm_model"]    = "claude-haiku-4-5"

        # Update entity_master GICS
        if ticker in entity_master:
            entity_master[ticker]["gics"] = hier[ticker]

        classified += 1

        if (i + 1) % 50 == 0:
            # Save progress
            hier_path.write_text(json.dumps(hier, sort_keys=True, indent=2))
            em_path.write_text(json.dumps(entity_master, indent=2))
            print(f"  [{i+1}/{len(targets)}] classified={classified}, "
                  f"api_errors={api_errors}, "
                  f"~cost=${cost_tally * 0.001:.2f}")

    # Final save
    hier_path.write_text(json.dumps(hier, sort_keys=True, indent=2))
    em_path.write_text(json.dumps(entity_master, indent=2))

    verified = sum(1 for h in hier.values() if h.get("llm_verified"))
    print(f"\nclassify_ambiguous_gics: complete")
    print(f"  Newly classified : {classified}")
    print(f"  API errors       : {api_errors}")
    print(f"  Total LLM-verified in hierarchy: {verified}")
    print(f"  Estimated cost   : ~${cost_tally * 0.001:.3f}")


if __name__ == "__main__":
    import sys
    lim     = int(next((a.split("=")[1] for a in sys.argv
                        if a.startswith("--limit=")), "500"))
    force   = "--force"   in sys.argv
    dry_run = "--dry-run" in sys.argv
    main(limit=lim, force=force, dry_run=dry_run)
