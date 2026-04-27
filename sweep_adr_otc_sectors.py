#!/usr/bin/env python3
"""sweep_adr_otc_sectors.py — Aggressively resolve "other"-classified entities.

Resolution chain (in order):
  1. sector_lookup.json already has a non-other entry → skip
  2. yfinance.Ticker(ticker).info → sector/industry field
  3. Company name heuristic keyword matcher (stdlib-only fallback)

Targets ALL entities with sector == "other" in entity_master.json.
Writes every resolved entry to sector_lookup.json so the API uses it immediately.

Run: python3 sweep_adr_otc_sectors.py [--dry-run] [--limit N]
Then: bash ops/deploy_cerebro_droplet.sh --stage-only && ssh cerebro "systemctl restart cerebro"
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent

# ── yfinance sector → internal sector key ─────────────────────────────────────
_YF_SECTOR_MAP: dict[str, str] = {
    "technology":                "tech",
    "information technology":    "tech",
    "healthcare":                "biotech",
    "health care":               "biotech",
    "financial services":        "financials",
    "financials":                "financials",
    "consumer cyclical":         "consumer",
    "consumer discretionary":    "consumer",
    "consumer defensive":        "staples",
    "consumer staples":          "staples",
    "communication services":    "comms",
    "communications":            "comms",
    "industrials":               "industrials",
    "basic materials":           "materials",
    "materials":                 "materials",
    "energy":                    "energy",
    "utilities":                 "utilities",
    "real estate":               "real_estate",
    "realestate":                "real_estate",
    "semiconductors":            "semis",
}

# yfinance industry keywords → sector key (used when sector field is empty)
_YF_INDUSTRY_MAP: list[tuple[str, str]] = [
    ("semiconductor",        "semis"),
    ("software",             "tech"),
    ("internet",             "tech"),
    ("cloud",                "tech"),
    ("biotechnology",        "biotech"),
    ("pharmaceutical",       "biotech"),
    ("health care",          "biotech"),
    ("medical",              "biotech"),
    ("drug",                 "biotech"),
    ("bank",                 "financials"),
    ("insurance",            "financials"),
    ("financial",            "financials"),
    ("real estate",          "real_estate"),
    ("reit",                 "real_estate"),
    ("oil",                  "energy"),
    ("gas",                  "energy"),
    ("mining",               "materials"),
    ("gold",                 "materials"),
    ("metal",                "materials"),
    ("chemical",             "materials"),
    ("telecom",              "comms"),
    ("broadcasting",         "comms"),
    ("media",                "comms"),
    ("utilities",            "utilities"),
    ("electric",             "utilities"),
    ("retail",               "consumer"),
    ("restaurant",           "consumer"),
    ("automotive",           "consumer"),
    ("food",                 "staples"),
    ("beverage",             "staples"),
    ("tobacco",              "staples"),
    ("household",            "staples"),
    ("aerospace",            "industrials"),
    ("defense",              "industrials"),
    ("industrial",           "industrials"),
    ("transportation",       "industrials"),
    ("logistics",            "industrials"),
]


def _map_yf_sector(sector: str, industry: str = "") -> str | None:
    """Map yfinance sector/industry strings to our internal sector keys."""
    s = sector.strip().lower()
    mapped = _YF_SECTOR_MAP.get(s)
    if mapped:
        return mapped
    # Try industry field as fallback
    ind = industry.strip().lower()
    for keyword, key in _YF_INDUSTRY_MAP:
        if keyword in ind:
            return key
    return None


def _yfinance_sector(ticker: str) -> str | None:
    """Return our internal sector key via yfinance, or None on failure."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        sector   = str(info.get("sector")   or "").strip()
        industry = str(info.get("industry") or "").strip()
        return _map_yf_sector(sector, industry)
    except Exception:
        return None


# ── Heuristic name classifier ─────────────────────────────────────────────────
_NAME_RULES: list[tuple[list[str], str]] = [
    # Order matters — more specific first
    (["SEMICONDUCTOR", "SEMICON", "MICROCHIP", "WAFER"],                     "semis"),
    (["PHARMA", "PHARMACEUTICAL", "BIOTECH", "THERAPEUTICS", "BIOSCIENCE",
      "GENOMIC", "ONCOLOGY", "IMMUNOLOGY"],                                  "biotech"),
    (["HEALTH", "MEDICAL", "CLINIC", "HOSPITAL", "DIAGNOSTICS"],             "biotech"),
    (["SOFTWARE", "SAAS", "CLOUD", "ARTIFICIAL INTELLIGENCE", "MACHINE LEARNING",
      "CYBERSECURITY", "CYBER", "ANALYTICS", "INFORMATION TECHNOLOGY"],      "tech"),
    (["TECH", "DIGITAL", "DATA CENTER", "SEMICONDUCTOR"],                    "tech"),
    (["REIT", "REALTY", "REAL ESTATE", "PROPERTIES PLC", "PROPERTIES LTD",
      "RESIDENTIAL", "COMMERCIAL PROP"],                                      "real_estate"),
    (["GOLD", "SILVER", "COPPER", "LITHIUM", "COBALT", "URANIUM",
      "PLATINUM", "PALLADIUM", "ZINC", "NICKEL", "IRON ORE"],               "materials"),
    (["MINING", "MINERALS", "RESOURCES", "METALS", "STEEL", "CEMENT",
      "CHEMICALS", "FERTILIZER"],                                             "materials"),
    (["OIL", "GAS", "PETROLEUM", "DRILLING", "EXPLORATION", "LNG",
      "PIPELINE", "REFIN", "HYDROCARBON"],                                   "energy"),
    (["ELECTRIC UTIL", "WATER UTIL", "GAS UTIL", "UTILITY", "UTILITIES",
      "NUCLEAR POWER", "RENEWABLE ENERGY", "SOLAR", "WIND ENERGY"],         "utilities"),
    (["TELECOM", "TELECOMMUNICATIONS", "WIRELESS", "CABLE", "BROADCAST",
      "SATELLITE", "MEDIA GROUP", "PUBLISHING", "STREAMING"],               "comms"),
    (["BANCORP", "BANCSHARES", "BANQUE", "BANCO", "BANCA",
      "INSURANCE", "INSUR", "REINSUR", "CAPITAL MANAGEMENT",
      "ASSET MANAGEMENT", "INVESTMENT TRUST", "SECURITIES"],                 "financials"),
    (["BANK", "FINANCIAL", "FINANCE", "CREDIT", "LENDING",
      "MORTGAGE", "BROKERAGE", "INVESTMENT", "TRUST"],                       "financials"),
    (["AEROSPACE", "DEFENSE", "DEFENCE", "AVIATION", "AIRCRAFT",
      "RAIL", "SHIPPING", "LOGISTICS", "FREIGHT", "TRUCKING",
      "CONSTRUCTION", "ENGINEERING", "INFRASTRUCTURE"],                      "industrials"),
    (["INDUSTRIAL", "MANUFACTURING", "MACHINERY", "EQUIPMENT"],             "industrials"),
    (["FOOD", "BEVERAGE", "BEER", "SPIRITS", "WINE", "TOBACCO",
      "HOUSEHOLD PRODUCTS", "PERSONAL CARE", "COSMETIC", "HYGIENE",
      "AGRICULTURE", "AGRI", "FARM", "NUTRITION", "DAIRY", "MEAT"],         "staples"),
    (["RETAIL", "CASINO", "GAMING", "HOTEL", "RESORT", "RESTAURANT",
      "FAST FOOD", "LEISURE", "TOURISM", "TRAVEL", "FASHION",
      "APPAREL", "CLOTHING", "FOOTWEAR", "SPORTING", "AUTO", "MOTOR"],      "consumer"),
]


def heuristic_name_classification(company_name: str) -> str | None:
    """Return sector key from company name keywords, or None if no match."""
    name = company_name.upper()
    for keywords, sector_key in _NAME_RULES:
        if any(kw in name for kw in keywords):
            return sector_key
    return None


# ── Main sweep ────────────────────────────────────────────────────────────────
def main(dry_run: bool = False, limit: int = 0) -> None:
    em_path = ROOT / "entity_master.json"
    sl_path = ROOT / "sector_lookup.json"

    entity_master: dict = {}
    if em_path.exists():
        entity_master = json.loads(em_path.read_text(encoding="utf-8"))

    sector_lookup: dict = {}
    if sl_path.exists():
        sector_lookup = json.loads(sl_path.read_text(encoding="utf-8"))

    # Collect targets: all entity_master entries with sector == "other"
    def current_sector(rec: dict) -> str:
        gics = rec.get("gics") if isinstance(rec.get("gics"), dict) else {}
        s = str((gics.get("s") if gics else "") or rec.get("sector") or "").strip().lower()
        return s

    targets: list[tuple[str, dict]] = []
    for ticker, rec in entity_master.items():
        if current_sector(rec) == "other":
            # Skip if sector_lookup already has a good answer
            sl_val = sector_lookup.get(ticker)
            if sl_val:
                existing = str(sl_val[0] if isinstance(sl_val, list) else sl_val).lower()
                if existing and existing not in ("other", "unknown", "none", "null", ""):
                    continue
            targets.append((ticker, rec))

    # Prioritise 5-letter Y/F ADR/OTC tickers, then rest
    adrs   = [(t, r) for t, r in targets if len(t) == 5 and t[-1] in ("Y", "F")]
    others = [(t, r) for t, r in targets if not (len(t) == 5 and t[-1] in ("Y", "F"))]
    ordered = adrs + others

    if limit:
        ordered = ordered[:limit]

    print(f"sweep_adr_otc_sectors: {len(targets)} targets "
          f"({len(adrs)} ADR/OTC Y/F, {len(others)} other-type)")
    if dry_run:
        print(f"  [DRY RUN] First 10 targets:")
        for t, r in ordered[:10]:
            print(f"    {t:12s}  name={r.get('name','?')[:60]}")
        return

    resolved_yf        = 0
    resolved_heuristic = 0
    skipped            = 0
    updates: dict[str, str] = {}

    for i, (ticker, rec) in enumerate(ordered):
        name = str(rec.get("name") or "").strip()

        # 1. yfinance
        sector = _yfinance_sector(ticker)
        if sector:
            resolved_yf += 1
            label = "yfinance"
        else:
            # 2. Heuristic name classifier
            sector = heuristic_name_classification(name)
            if sector:
                resolved_heuristic += 1
                label = "heuristic"
            else:
                skipped += 1
                continue

        sector_lookup[ticker] = [sector]
        updates[ticker] = sector
        print(f"  [{i+1:4d}] {ticker:12s} → {sector:15s}  ({label}) {name[:50]}")

        # Rate-limit yfinance (Yahoo Finance)
        time.sleep(0.35)

        # Checkpoint save every 50
        if (i + 1) % 50 == 0:
            sl_path.write_text(
                json.dumps(sector_lookup, sort_keys=True, separators=(",", ":")),
                encoding="utf-8"
            )
            print(f"  --- checkpoint [{i+1}/{len(ordered)}] "
                  f"yf={resolved_yf} heuristic={resolved_heuristic} skipped={skipped} ---")

    # Final save
    sl_path.write_text(
        json.dumps(sector_lookup, sort_keys=True, separators=(",", ":")),
        encoding="utf-8"
    )

    print(f"\nsweep_adr_otc_sectors: complete")
    print(f"  Resolved via yfinance  : {resolved_yf}")
    print(f"  Resolved via heuristic : {resolved_heuristic}")
    print(f"  Unresolvable (skipped) : {skipped}")
    print(f"  Total sector_lookup    : {len(sector_lookup)}")
    print(f"\nNext: bash ops/deploy_cerebro_droplet.sh --stage-only && ssh cerebro 'systemctl restart cerebro'")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    limit   = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "0"))
    main(dry_run=dry_run, limit=limit)
