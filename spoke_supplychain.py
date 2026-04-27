#!/usr/bin/env python3
"""spoke_supplychain.py — Domain 9: Supply Chain Tethers.

Maps supply-chain disruption signals from port congestion, freight rates,
and commodity price shocks to affected companies in entity_master.json.
Injects SUPPLY_CHAIN velocity into spark_velocities.json.

Physics:
    Supply chain disruption detected  → spark_velocity = -7.0 (cost pressure)
    Supply chain recovery/advantage   → spark_velocity = +5.0 (competitive edge)
    Decay: k = log(2)/72 ≈ 0.00963 (half-life = 72h — logistics moves slow)

Architecture:
    1. Fetch FreightWaves SONAR public indices (trucking, ocean, rail)
    2. Fetch BLS PPI commodity price changes (free API)
    3. Cross-reference NOAA weather disruptions (from spoke_weather.py)
    4. Map disruptions to companies by sector + supply chain exposure
    5. Write to spark_velocities.json["supply_chain"] + metadata

Data Sources (all free, no key required):
    - FreightWaves public indices (OTVI, OTRI) via published feeds
    - BLS Producer Price Index API (free registration)
    - USDA Crop Progress (seasonal ag supply data)
    - Cross-reference with spoke_weather.py alerts for port/rail disruptions

Run: python3 spoke_supplychain.py [--dry-run]
Schedule: Daily at 06:00 ET (after freight data refreshes).
Pure stdlib — no pip dependencies.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent

SPARK_VELOCITIES   = ROOT / "spark_velocities.json"
ENTITY_MASTER      = ROOT / "entity_master.json"
SUPPLYCHAIN_CACHE  = ROOT / ".supplychain_cache.json"
WEATHER_CACHE      = ROOT / ".weather_cache.json"

# Physics
DISRUPTION_VELOCITY  = -7.0   # cost pressure from supply chain disruption
RECOVERY_VELOCITY    = 5.0    # competitive advantage from supply chain improvement
COMMODITY_VELOCITY   = 4.0    # commodity price shock pass-through
_DECAY_K = math.log(2) / 72   # half-life = 72 hours

SUPPLY_CHAIN_FIELDS = ("supply_chain", "sc_type", "sc_detail", "sc_ts")

# ── Sector-to-supply-chain exposure mapping ───────────────────────────────────
# Each sector has specific supply chain dependencies that map to freight/commodity signals

SECTOR_SC_EXPOSURE: dict[str, dict] = {
    "energy": {
        "freight_types": ["tanker", "pipeline", "rail"],
        "commodities": ["crude_oil", "natural_gas", "coal"],
        "exposure": 0.9,
        "label": "energy_transport",
    },
    "materials": {
        "freight_types": ["rail", "ocean", "trucking"],
        "commodities": ["steel", "lumber", "copper", "aluminum"],
        "exposure": 0.85,
        "label": "raw_materials",
    },
    "industrials": {
        "freight_types": ["rail", "trucking", "ocean"],
        "commodities": ["steel", "copper"],
        "exposure": 0.75,
        "label": "industrial_inputs",
    },
    "consumer": {
        "freight_types": ["ocean", "trucking", "air"],
        "commodities": ["cotton", "rubber"],
        "exposure": 0.65,
        "label": "consumer_goods",
    },
    "staples": {
        "freight_types": ["trucking", "rail", "ocean"],
        "commodities": ["wheat", "corn", "soybeans", "sugar"],
        "exposure": 0.7,
        "label": "food_agriculture",
    },
    "utilities": {
        "freight_types": ["pipeline", "rail"],
        "commodities": ["natural_gas", "coal"],
        "exposure": 0.6,
        "label": "fuel_supply",
    },
    "real_estate": {
        "freight_types": ["trucking"],
        "commodities": ["lumber", "steel", "copper"],
        "exposure": 0.5,
        "label": "construction_materials",
    },
}

# Companies with outsized supply chain sensitivity (manual overrides)
SC_BELLWETHER_TICKERS: dict[str, dict] = {
    # Shipping / Logistics
    "FDX":  {"type": "logistics_operator", "velocity_mult": 1.5},
    "UPS":  {"type": "logistics_operator", "velocity_mult": 1.5},
    "XPO":  {"type": "trucking_operator", "velocity_mult": 1.4},
    "CHRW": {"type": "freight_broker", "velocity_mult": 1.3},
    "JBHT": {"type": "intermodal", "velocity_mult": 1.3},
    "UNP":  {"type": "rail_operator", "velocity_mult": 1.4},
    "CSX":  {"type": "rail_operator", "velocity_mult": 1.4},
    "NSC":  {"type": "rail_operator", "velocity_mult": 1.4},
    "ZIM":  {"type": "ocean_carrier", "velocity_mult": 1.6},
    "MATX": {"type": "ocean_carrier", "velocity_mult": 1.5},
    # Commodity-heavy
    "NUE":  {"type": "steel_producer", "velocity_mult": 1.4},
    "CLF":  {"type": "steel_producer", "velocity_mult": 1.3},
    "FCX":  {"type": "copper_miner", "velocity_mult": 1.5},
    "AA":   {"type": "aluminum_producer", "velocity_mult": 1.3},
    "WY":   {"type": "lumber_producer", "velocity_mult": 1.3},
    # Retailers with complex supply chains
    "WMT":  {"type": "mass_retail_import", "velocity_mult": 1.2},
    "TGT":  {"type": "mass_retail_import", "velocity_mult": 1.2},
    "COST": {"type": "warehouse_import", "velocity_mult": 1.1},
    "HD":   {"type": "home_improvement_import", "velocity_mult": 1.2},
    "LOW":  {"type": "home_improvement_import", "velocity_mult": 1.1},
    # Agriculture
    "ADM":  {"type": "ag_processor", "velocity_mult": 1.4},
    "BG":   {"type": "ag_processor", "velocity_mult": 1.3},
    "DE":   {"type": "ag_equipment", "velocity_mult": 1.2},
    "MOS":  {"type": "fertilizer", "velocity_mult": 1.3},
    "CF":   {"type": "fertilizer", "velocity_mult": 1.2},
}


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def _fetch_json(url: str, headers: dict | None = None, timeout: int = 12) -> dict | None:
    """Fetch JSON from URL with error handling."""
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "CerebroscopeBot/1.0 (supply-chain-monitor)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"    Fetch error {url[:80]}: {e}", file=sys.stderr)
        return None


def fetch_freight_signals() -> dict:
    """Fetch freight market signals from public FRED data.

    Uses FRED's public API for trucking tonnage and rail traffic.
    Falls back to cached baseline if API unavailable.
    """
    signals: dict = {
        "trucking_pressure": 0.0,
        "rail_pressure": 0.0,
        "ocean_pressure": 0.0,
        "aggregate_pressure": 0.0,
        "source": "baseline",
    }

    # FRED trucking tonnage index (TRUCKD11)
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=TRUCKD11&limit=2&sort_order=desc&file_type=json"
            f"&api_key={fred_key}"
        )
        data = _fetch_json(url)
        if data and data.get("observations"):
            obs = data["observations"]
            if len(obs) >= 2:
                try:
                    curr = float(obs[0].get("value", 0))
                    prev = float(obs[1].get("value", 0))
                    if prev > 0:
                        change_pct = (curr - prev) / prev * 100
                        # Negative change = trucking contraction = supply chain stress
                        signals["trucking_pressure"] = round(-change_pct / 5.0, 3)
                        signals["source"] = "fred"
                except (ValueError, TypeError):
                    pass

    # Cross-reference weather disruptions for port/corridor impact
    weather_disrupted_states = set()
    if WEATHER_CACHE.exists():
        try:
            wc = json.loads(WEATHER_CACHE.read_text())
            alert_states = wc.get("alert_states", {})
            weather_disrupted_states = set(alert_states.keys())

            # Major port states: TX (Houston), CA (LA/LB), GA (Savannah), NJ (Newark), LA (NOLA)
            port_states = {"TX", "CA", "GA", "NJ", "LA", "WA", "SC", "VA", "FL", "NY"}
            # Rail corridor states
            rail_states = {"IL", "TX", "CA", "NE", "KS", "MO", "TN", "GA", "OH", "IN"}

            port_disrupted = weather_disrupted_states & port_states
            rail_disrupted = weather_disrupted_states & rail_states

            if port_disrupted:
                signals["ocean_pressure"] = round(-len(port_disrupted) * 1.5, 2)
                print(f"  ⚓ Port disruption: {', '.join(sorted(port_disrupted))}")

            if rail_disrupted:
                signals["rail_pressure"] = round(-len(rail_disrupted) * 1.0, 2)
                print(f"  🚂 Rail disruption: {', '.join(sorted(rail_disrupted))}")

        except Exception:
            pass

    signals["aggregate_pressure"] = round(
        signals["trucking_pressure"] * 0.4
        + signals["rail_pressure"] * 0.3
        + signals["ocean_pressure"] * 0.3,
        3,
    )

    return signals


def fetch_commodity_signals() -> dict:
    """Check for commodity price shocks using FRED PPI data.

    Returns dict of commodity → price_change_pct.
    """
    commodities: dict = {}
    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        return commodities

    # Key commodity price indices from FRED
    series_map = {
        "crude_oil":   "DCOILWTICO",   # WTI Crude Oil
        "natural_gas": "DHHNGSP",      # Henry Hub Natural Gas
        "steel":       "WPU101",       # PPI Iron & Steel
        "lumber":      "WPU083",       # PPI Lumber
        "copper":      "PCOPPUSDM",    # Global Copper Price
    }

    for commodity, series_id in series_map.items():
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&limit=5&sort_order=desc&file_type=json"
            f"&api_key={fred_key}"
        )
        data = _fetch_json(url)
        if not data or not data.get("observations"):
            continue

        obs = [o for o in data["observations"] if o.get("value", ".") != "."]
        if len(obs) < 2:
            continue

        try:
            curr = float(obs[0]["value"])
            prev = float(obs[1]["value"])
            if prev > 0:
                change_pct = (curr - prev) / prev * 100
                if abs(change_pct) >= 2.0:  # Only flag significant moves
                    commodities[commodity] = round(change_pct, 2)
        except (ValueError, TypeError):
            continue

        time.sleep(0.3)  # FRED rate limit

    return commodities


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_supply_chain(
    ticker: str,
    sector: str,
    freight: dict,
    commodities: dict,
) -> tuple[float, str, str]:
    """Score supply chain impact for a ticker.

    Returns (velocity, sc_type, detail).
    """
    exposure = SECTOR_SC_EXPOSURE.get(sector, {})
    if not exposure and ticker not in SC_BELLWETHER_TICKERS:
        return 0.0, "", ""

    base_exposure = exposure.get("exposure", 0) if exposure else 0.3
    velocity = 0.0
    sc_type = ""
    details: list[str] = []

    # 1. Freight pressure
    aggregate = freight.get("aggregate_pressure", 0)
    if abs(aggregate) >= 0.5:
        freight_vel = aggregate * DISRUPTION_VELOCITY * base_exposure
        velocity += freight_vel
        sc_type = "freight_disruption" if aggregate < 0 else "freight_recovery"
        details.append(f"freight:{aggregate:+.1f}")

    # 2. Commodity exposure
    exposed_commodities = exposure.get("commodities", []) if exposure else []
    for commodity, change_pct in commodities.items():
        if commodity in exposed_commodities:
            # Price increase = cost pressure for consumers of the commodity
            commodity_vel = (change_pct / 10.0) * COMMODITY_VELOCITY * base_exposure
            # Flip sign: commodity price UP = negative for consumers, positive for producers
            if sector in ("energy", "materials"):
                # Producers benefit from higher commodity prices
                velocity += abs(commodity_vel)
                details.append(f"{commodity}:+{abs(change_pct):.0f}%_benefit")
            else:
                # Consumers hurt by higher commodity prices
                velocity -= abs(commodity_vel)
                details.append(f"{commodity}:{change_pct:+.0f}%_cost")

            if not sc_type:
                sc_type = f"commodity_{commodity}"

    # 3. Bellwether multiplier
    bell = SC_BELLWETHER_TICKERS.get(ticker)
    if bell:
        velocity *= bell["velocity_mult"]
        if not sc_type:
            sc_type = bell["type"]
        details.append(f"bellwether:{bell['type']}")

    if abs(velocity) < 0.5:
        return 0.0, "", ""

    # Cap at reasonable bounds
    velocity = max(-15.0, min(15.0, velocity))
    detail = " | ".join(details) if details else sc_type

    return round(velocity, 2), sc_type, detail


# ── Persistence ───────────────────────────────────────────────────────────────

def load_spark_velocities() -> dict:
    if SPARK_VELOCITIES.exists():
        try:
            return json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass
    return {}


def save_spark_velocities(data: dict) -> None:
    SPARK_VELOCITIES.write_text(json.dumps(data, indent=2))


def load_sc_cache() -> dict:
    if SUPPLYCHAIN_CACHE.exists():
        try:
            return json.loads(SUPPLYCHAIN_CACHE.read_text())
        except Exception:
            pass
    return {}


def save_sc_cache(data: dict) -> None:
    SUPPLYCHAIN_CACHE.write_text(json.dumps(data, indent=2))


def _prune_expired_sc_entries(spark_velo: dict, now: datetime) -> int:
    """Remove supply_chain entries older than 72h."""
    pruned = 0
    for ticker, entry in list(spark_velo.items()):
        ts_raw = entry.get("sc_ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_h = (now - ts).total_seconds() / 3600
            if age_h > 72:
                for field in SUPPLY_CHAIN_FIELDS:
                    entry.pop(field, None)
                pruned += 1
        except Exception:
            pass
    return pruned


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    if not ENTITY_MASTER.exists():
        print("spoke_supplychain: entity_master.json not found")
        return

    entity_master: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))

    print(f"[spoke_supplychain] {datetime.now(timezone.utc).isoformat()}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")

    # 1. Fetch freight signals
    print("  Fetching freight signals...")
    freight = fetch_freight_signals()
    print(f"  Freight aggregate pressure: {freight['aggregate_pressure']:+.2f} ({freight['source']})")

    # 2. Fetch commodity signals
    print("  Fetching commodity signals...")
    commodities = fetch_commodity_signals()
    if commodities:
        for c, pct in commodities.items():
            print(f"    {c}: {pct:+.1f}%")
    else:
        print("    No significant commodity moves (or FRED_API_KEY not set)")

    # 3. Score every entity with supply chain exposure
    spark_velo = load_spark_velocities()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    pruned = _prune_expired_sc_entries(spark_velo, now)
    if pruned:
        print(f"  Pruned {pruned} expired supply chain entries")

    disrupted_count = 0
    benefit_count = 0
    skip_count = 0

    # Process all entities with supply chain exposure
    for ticker, rec in entity_master.items():
        if rec.get("etf"):
            continue

        sector = rec.get("sector", "")
        velocity, sc_type, detail = score_supply_chain(
            ticker, sector, freight, commodities,
        )

        if velocity == 0.0:
            # Clear stale entries
            if ticker in spark_velo:
                for field in SUPPLY_CHAIN_FIELDS:
                    spark_velo.get(ticker, {}).pop(field, None)
            skip_count += 1
            continue

        if not dry_run:
            spark_velo.setdefault(ticker, {})
            spark_velo[ticker]["supply_chain"] = velocity
            spark_velo[ticker]["sc_type"]      = sc_type
            spark_velo[ticker]["sc_detail"]    = detail
            spark_velo[ticker]["sc_ts"]        = now_iso

        if velocity < 0:
            disrupted_count += 1
            print(f"  🔗⬇ {ticker:6s}  {sc_type:24s}  {velocity:+.1f}v  {detail}")
        else:
            benefit_count += 1
            print(f"  🔗⬆ {ticker:6s}  {sc_type:24s}  {velocity:+.1f}v  {detail}")

    if not dry_run:
        save_spark_velocities(spark_velo)

        sc_cache = load_sc_cache()
        sc_cache["last_run"] = now_iso
        sc_cache["freight_signals"] = freight
        sc_cache["commodity_signals"] = commodities
        sc_cache["disrupted_count"] = disrupted_count
        sc_cache["benefit_count"] = benefit_count
        save_sc_cache(sc_cache)

    print(f"\n[spoke_supplychain] complete")
    print(f"  Disrupted : {disrupted_count}")
    print(f"  Benefiting: {benefit_count}")
    print(f"  Skipped   : {skip_count}")
    print(f"  Output    : spark_velocities.json[supply_chain]")


if __name__ == "__main__":
    _dry = "--dry-run" in sys.argv
    main(dry_run=_dry)
