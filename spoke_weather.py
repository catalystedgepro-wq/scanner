#!/usr/bin/env python3
"""spoke_weather.py — Domain 3: Physical Reality (NOAA Weather Shockwave Layer).

Polls NOAA CAP/Atom feeds for Severe/Extreme weather alerts, maps them to
affected company HQ coordinates (from SEC filing cache), and injects
WEATHER_SHOCKWAVE velocity events into spark_velocities.json.

Physics:
    Disrupted node (HQ in storm polygon):   -10 velocity  (WEATHER_DISRUPTION)
    Recovery beneficiary ($HD, $GNRC etc):  +8  velocity  (WEATHER_RECOVERY)
    Decay: k = log(2)/24 (half-life = 24h — acute event signal)

Architecture:
    1. Fetch NOAA alerts API (free, no key) → filter Extreme/Severe
    2. Extract affected area (SAME geocodes → state/county)
    3. Load HQ state data from .sec_filing_text_cache.json
    4. Score disruption (HQ in alert zone) and recovery (RECOVERY_TICKERS list)
    5. Write to spark_velocities.json["weather"]

Run: python3 spoke_weather.py [--dry-run] [--state=FL]
Schedule: Every 30 minutes during storm season; hourly otherwise.
Pure stdlib — no pip dependencies.
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent

SPARK_VELOCITIES  = ROOT / "spark_velocities.json"
FILING_CACHE      = ROOT / ".sec_filing_text_cache.json"
WEATHER_CACHE     = ROOT / ".weather_cache.json"
HQ_STATES_CACHE   = ROOT / ".hq_states_cache.json"
ENTITY_MASTER     = ROOT / "entity_master.json"
WEATHER_MAX_AGE   = timedelta(hours=36)
WEATHER_FIELDS    = ("weather", "weather_event", "weather_state", "weather_severity", "weather_ts")

_CIK_IN_URL = re.compile(r"/edgar/data/(\d+)/")

NOAA_ALERTS_URL = "https://api.weather.gov/alerts/active?severity=Extreme,Severe&status=actual&message_type=alert"

# Tickers that benefit from disaster recovery demand
RECOVERY_TICKERS = {
    "HD":   "home_improvement",
    "LOW":  "home_improvement",
    "GNRC": "generators",
    "POOL": "outdoor_repair",
    "WM":   "waste_cleanup",
    "RSG":  "waste_cleanup",
    "URI":  "equipment_rental",
    "TREX": "building_materials",
    "MAS":  "building_materials",
    "SHW":  "coatings_repair",
}

# Sectors with physical supply-chain / infrastructure exposure to severe weather.
# Digital-first sectors (fintech, SaaS, media) are excluded — a typhoon doesn't
# disrupt a neobank's loan book or a streaming service's CDN.
WEATHER_SENSITIVE_SECTORS = {
    "energy", "utilities", "industrials", "materials",
    "consumer", "staples", "real_estate",
}

# State abbreviation → FIPS prefix for SAME geocode matching
FIPS_PREFIX = {
    "AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09",
    "DE":"10","FL":"12","GA":"13","HI":"15","ID":"16","IL":"17","IN":"18",
    "IA":"19","KS":"20","KY":"21","LA":"22","ME":"23","MD":"24","MA":"25",
    "MI":"26","MN":"27","MS":"28","MO":"29","MT":"30","NE":"31","NV":"32",
    "NH":"33","NJ":"34","NM":"35","NY":"36","NC":"37","ND":"38","OH":"39",
    "OK":"40","OR":"41","PA":"42","RI":"44","SC":"45","SD":"46","TN":"47",
    "TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54","WI":"55",
    "WY":"56",
}
FIPS_TO_STATE = {v: k for k, v in FIPS_PREFIX.items()}


def fetch_noaa_alerts(state_filter: str | None = None) -> list[dict]:
    url = NOAA_ALERTS_URL
    if state_filter:
        url += f"&area={state_filter.upper()}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "CerebroWeatherSpoke/1.0 (catalystedgescanner.com)",
            "Accept": "application/geo+json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("features", [])
    except Exception as e:
        print(f"  NOAA fetch error: {e}", file=sys.stderr)
        return []


def extract_affected_states(alert: dict) -> set[str]:
    """Extract affected US state abbreviations from a NOAA alert feature."""
    states = set()
    props = alert.get("properties", {})

    # Method 1: areaDesc field (e.g., "Miami-Dade; Broward; Palm Beach")
    area_desc = props.get("areaDesc", "")

    # Method 2: geocode SAME codes (6-digit: SSFIPS where SS=state FIPS)
    same_codes = props.get("geocode", {}).get("SAME", [])
    for code in same_codes:
        if len(code) >= 2:
            fips = code[:2]
            state = FIPS_TO_STATE.get(fips)
            if state:
                states.add(state)

    # Method 3: affectedZones URLs contain state code
    for zone_url in props.get("affectedZones", []):
        # URL pattern: .../zones/county/TXC001 — TX is state
        parts = zone_url.rstrip("/").split("/")
        if parts:
            zone_id = parts[-1]
            if len(zone_id) >= 2:
                state_code = zone_id[:2].upper()
                if state_code in FIPS_PREFIX:
                    states.add(state_code)

    return states


def _build_cik_ticker_map() -> dict[str, str]:
    """Build {cik_str: ticker} from entity_master, preferring common stock (no '-')."""
    if not ENTITY_MASTER.exists():
        return {}
    try:
        em = json.loads(ENTITY_MASTER.read_text())
    except Exception:
        return {}
    cik_map: dict[str, str] = {}
    for ticker, rec in em.items():
        cik_raw = rec.get("cik")
        if not cik_raw:
            continue
        cik = str(cik_raw).lstrip("0")
        # Prefer common stock (no dash) over preferred shares / warrants
        if cik not in cik_map or "-" in cik_map[cik]:
            cik_map[cik] = ticker
    return cik_map


def _fetch_edgar_state(cik: str) -> str:
    """Fetch company HQ state from EDGAR submissions API. Returns '' on failure."""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "CerebroWeatherSpoke/1.0 (catalystedgescanner.com)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # EDGAR returns stateOrCountry in addresses.business
        state = (data.get("addresses", {})
                     .get("business", {})
                     .get("stateOrCountry", ""))
        if state and len(state) == 2 and state.upper() in FIPS_PREFIX:
            return state.upper()
    except Exception:
        pass
    return ""


def load_hq_states() -> dict[str, str]:
    """Return {ticker: hq_state} from the pre-built .hq_states_cache.json.

    Cache is built by running: python3 spoke_weather.py --build-hq-cache
    (one-time setup, fetches EDGAR submissions API for all active filers)
    """
    if not HQ_STATES_CACHE.exists():
        print("  WARN: .hq_states_cache.json missing — run with --build-hq-cache first.")
        return {}

    try:
        hq_cache: dict[str, str] = json.loads(HQ_STATES_CACHE.read_text())
    except Exception:
        return {}

    cik_ticker = _build_cik_ticker_map()

    hq_map: dict[str, str] = {}
    for cik, state in hq_cache.items():
        if not state:
            continue
        ticker = cik_ticker.get(cik)
        if ticker:
            hq_map[ticker] = state

    return hq_map


def build_hq_cache() -> None:
    """One-time batch: fetch HQ state for all CIKs in the filing cache.

    Writes results to .hq_states_cache.json. Takes ~3 min on first run.
    Re-run periodically to add newly cached CIKs.
    """
    if not FILING_CACHE.exists():
        print("No filing cache found — run sec_catalyst_list.py first.")
        return

    try:
        filing_cache = json.loads(FILING_CACHE.read_text())
    except Exception:
        print("Could not read filing cache.")
        return

    cik_ticker = _build_cik_ticker_map()

    # Load existing cache
    hq_cache: dict[str, str] = {}
    if HQ_STATES_CACHE.exists():
        try:
            hq_cache = json.loads(HQ_STATES_CACHE.read_text())
        except Exception:
            pass

    # Find CIKs we know about but haven't fetched yet
    to_fetch: list[str] = []
    for url in filing_cache:
        m = _CIK_IN_URL.search(url)
        if m:
            cik = m.group(1).lstrip("0")
            if cik in cik_ticker and cik not in hq_cache:
                to_fetch.append(cik)

    to_fetch = list(set(to_fetch))
    print(f"[build-hq-cache] {len(hq_cache)} CIKs already cached, {len(to_fetch)} to fetch.")

    if not to_fetch:
        print("  Cache is up to date.")
        return

    for i, cik in enumerate(to_fetch):
        state = _fetch_edgar_state(cik)
        hq_cache[cik] = state
        ticker = cik_ticker.get(cik, "?")
        if state:
            print(f"  [{i+1}/{len(to_fetch)}] CIK={cik} {ticker:8s} → {state}")
        # Save checkpoint every 50 and rate limit
        if (i + 1) % 50 == 0:
            HQ_STATES_CACHE.write_text(json.dumps(hq_cache, indent=2))
            print(f"  Checkpoint saved. Sleeping...")
            time.sleep(1.0)
        elif (i + 1) % 5 == 0:
            time.sleep(0.3)

    HQ_STATES_CACHE.write_text(json.dumps(hq_cache, indent=2))
    filled = sum(1 for v in hq_cache.values() if v)
    print(f"\n[build-hq-cache] Done. {filled}/{len(hq_cache)} CIKs have US state data.")
    print(f"  Output: {HQ_STATES_CACHE}")


def load_spark_velocities() -> dict:
    if SPARK_VELOCITIES.exists():
        try:
            return json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass
    return {}


def save_spark_velocities(data: dict) -> None:
    SPARK_VELOCITIES.write_text(json.dumps(data, indent=2))


def load_weather_cache() -> dict:
    if WEATHER_CACHE.exists():
        try:
            return json.loads(WEATHER_CACHE.read_text())
        except Exception:
            pass
    return {}


def save_weather_cache(data: dict) -> None:
    WEATHER_CACHE.write_text(json.dumps(data, indent=2))


def _parse_weather_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clear_weather_fields(entry: dict) -> bool:
    changed = False
    for key in WEATHER_FIELDS:
        if key in entry:
            entry.pop(key, None)
            changed = True
    return changed


def _prune_expired_weather_entries(spark_velo: dict, now: datetime) -> int:
    pruned = 0
    for entry in spark_velo.values():
        weather_ts = _parse_weather_ts(entry.get("weather_ts"))
        has_weather = any(key in entry for key in WEATHER_FIELDS)
        if not has_weather:
            continue
        if weather_ts is None or (now - weather_ts) > WEATHER_MAX_AGE:
            if _clear_weather_fields(entry):
                pruned += 1
    return pruned


def _clear_inactive_weather_entries(spark_velo: dict, active_tickers: set[str]) -> int:
    cleared = 0
    for ticker, entry in spark_velo.items():
        if ticker in active_tickers:
            continue
        if _clear_weather_fields(entry):
            cleared += 1
    return cleared


def severity_to_velocity(severity: str, event: str) -> float:
    """Map NOAA severity + event type to disruption velocity magnitude."""
    base = {"Extreme": 10.0, "Severe": 7.0, "Moderate": 4.0}.get(severity, 3.0)
    # Hurricanes/tornadoes hit harder than winter storms for supply chain
    multipliers = {
        "Hurricane": 1.5, "Typhoon": 1.5, "Tornado": 1.3,
        "Blizzard": 1.1, "Ice Storm": 1.0, "Flood": 1.2,
        "Wildfire": 1.3, "Earthquake": 1.4,
    }
    for keyword, mult in multipliers.items():
        if keyword.lower() in event.lower():
            return round(base * mult, 1)
    return base


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    state_filter = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--state=")), None)

    print(f"[spoke_weather] {datetime.now(timezone.utc).isoformat()}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}"
          + (f" | Filter: {state_filter}" if state_filter else ""))

    spark_velo = load_spark_velocities()
    weather_cache = load_weather_cache()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    stale_pruned = _prune_expired_weather_entries(spark_velo, now)
    if stale_pruned:
        print(f"  Pruned {stale_pruned} expired weather spark entries")

    # Fetch active alerts
    alerts = fetch_noaa_alerts(state_filter)
    print(f"  NOAA alerts fetched: {len(alerts)}")

    if not alerts:
        print("  No active severe/extreme alerts — no shockwaves today.")
        weather_cache["last_run"] = now_iso
        weather_cache["alert_states"] = {}
        if not dry_run:
            cleared = _clear_inactive_weather_entries(spark_velo, set())
            if cleared:
                print(f"  Cleared {cleared} inactive weather spark entries")
            save_spark_velocities(spark_velo)
            save_weather_cache(weather_cache)
        return

    # Build affected states set across all alerts
    alert_states: dict[str, dict] = {}  # state → worst alert info
    for alert in alerts:
        props = alert.get("properties", {})
        severity = props.get("severity", "Unknown")
        event    = props.get("event", "Weather Alert")
        headline = props.get("headline", event)
        affected = extract_affected_states(alert)
        for state in affected:
            existing = alert_states.get(state, {})
            # Keep the most severe alert per state
            if not existing or severity == "Extreme":
                alert_states[state] = {
                    "severity": severity,
                    "event":    event,
                    "headline": headline,
                    "velocity": severity_to_velocity(severity, event),
                }

    if not alert_states:
        print("  Could not extract state data from alerts.")
        return

    print(f"  Affected states: {', '.join(sorted(alert_states.keys()))}")

    # Load HQ map + entity_master for sector filtering
    hq_map = load_hq_states()
    print(f"  HQ state mappings loaded: {len(hq_map)} tickers")

    em_sectors: dict[str, str] = {}
    if ENTITY_MASTER.exists():
        try:
            _em = json.loads(ENTITY_MASTER.read_text())
            em_sectors = {t: r.get("sector", "") for t, r in _em.items()}
        except Exception:
            pass

    disrupted_count  = 0
    skipped_sector   = 0
    recovery_count   = 0
    any_active_alert = bool(alert_states)
    active_weather_tickers: set[str] = set()

    # Score disrupted tickers (only weather-sensitive sectors)
    for ticker, hq_state in hq_map.items():
        if hq_state not in alert_states:
            continue
        sector = em_sectors.get(ticker, "")
        if sector and sector not in WEATHER_SENSITIVE_SECTORS:
            skipped_sector += 1
            continue
        alert_info = alert_states[hq_state]
        vel = -alert_info["velocity"]  # negative = disruption

        if not dry_run:
            spark_velo.setdefault(ticker, {})
            spark_velo[ticker]["weather"]          = vel
            spark_velo[ticker]["weather_event"]    = alert_info["event"]
            spark_velo[ticker]["weather_state"]    = hq_state
            spark_velo[ticker]["weather_severity"] = alert_info["severity"]
            spark_velo[ticker]["weather_ts"]       = now_iso
        active_weather_tickers.add(ticker)

        disrupted_count += 1
        print(f"  🌩 DISRUPTED  {ticker:6s} HQ={hq_state}  {alert_info['event']}  {vel:+.1f}v")

    # Score recovery beneficiaries when any major alert is active
    if any_active_alert:
        # Find the most severe event for the headline
        worst = max(alert_states.values(), key=lambda a: a["velocity"])
        for ticker, reason in RECOVERY_TICKERS.items():
            vel = +8.0
            if not dry_run:
                spark_velo.setdefault(ticker, {})
                spark_velo[ticker]["weather"]          = vel
                spark_velo[ticker]["weather_event"]    = f"RECOVERY_{reason.upper()}"
                spark_velo[ticker]["weather_state"]    = "NATIONAL"
                spark_velo[ticker]["weather_severity"] = worst["severity"]
                spark_velo[ticker]["weather_ts"]       = now_iso
            active_weather_tickers.add(ticker)
            recovery_count += 1
            print(f"  🟢 RECOVERY   {ticker:6s} ({reason})  {vel:+.1f}v")

    # Save weather cache for dedup
    weather_cache["last_run"]     = now_iso
    weather_cache["alert_states"] = alert_states

    if not dry_run:
        cleared = _clear_inactive_weather_entries(spark_velo, active_weather_tickers)
        if cleared:
            print(f"  Cleared {cleared} inactive weather spark entries")
        save_spark_velocities(spark_velo)
        save_weather_cache(weather_cache)

    print(f"\n  Summary: {disrupted_count} disrupted | {recovery_count} recovery | {skipped_sector} skipped (non-physical sector)")
    print(f"  Output: spark_velocities.json[weather]")


if __name__ == "__main__":
    if "--build-hq-cache" in sys.argv:
        build_hq_cache()
    else:
        main()
