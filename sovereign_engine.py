#!/usr/bin/env python3
"""sovereign_engine.py — Domain 2: Sovereign Health Layer.

Fetches GDP growth and Debt-to-GDP from the World Bank Open Data API (free,
no key required) and computes a "Sovereign Drag" multiplier for every country
where tickers in the UEM are headquartered.

Physics:
    If a country's Debt/GDP > 100% → Sovereign Drag = 0.93 (structural headwind)
    If a country's Debt/GDP > 120% → Sovereign Drag = 0.88 (systemic risk)
    If GDP growth < 0%             → Sovereign Drag × 0.95 (contraction penalty)
    If GDP growth > 4%             → Sovereign Drag × 1.05 (expansion tailwind)

HUD: Sovereign health appears as a "foundation plate" under each sector.
     Country plates sink when debt/gdp exceeds critical thresholds.

Output: sovereign_health.json
    {
      "updated": "2026-04-04",
      "countries": {
        "US": {"gdp_growth": 2.5, "debt_to_gdp": 122.3, "drag": 0.88, "signal": "risk"},
        "DE": {"gdp_growth": 0.1, "debt_to_gdp": 66.4,  "drag": 0.97, "signal": "neutral"},
        ...
      }
    }

Cached monthly — sovereign data moves on quarterly/annual timescales.

Run: python3 sovereign_engine.py [--force] [--countries=US,DE,CN,JP]
Pure stdlib — no requests/pandas.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
OUT  = ROOT / "sovereign_health.json"

# World Bank WDI indicators
_WB_BASE = "https://api.worldbank.org/v2/country/{iso}/indicator/{code}?format=json&mrv=3"
_INDICATORS = {
    "gdp_growth":  "NY.GDP.MKTP.KD.ZG",   # GDP growth rate (annual %)
    "debt_to_gdp": "GC.DOD.TOTL.GD.ZS",   # Central govt debt (% of GDP)
    "gdp_pc":      "NY.GDP.PCAP.CD",       # GDP per capita (current USD)
}

# Countries with significant ticker presence in the UEM
DEFAULT_COUNTRIES = [
    "US", "CN", "JP", "DE", "GB", "FR", "CA", "AU",
    "KR", "TW", "IN", "BR", "IL", "SE", "NL", "CH",
    "HK", "SG", "IT", "ES",
]

# Sovereign drag thresholds
_DEBT_CRITICAL  = 120.0   # drag = 0.88
_DEBT_HIGH      = 100.0   # drag = 0.93
_DEBT_MODERATE  = 80.0    # drag = 0.97
_GDP_RECESSION  = 0.0     # additional ×0.95
_GDP_EXPANSION  = 4.0     # additional ×1.05


def _fetch_wb(iso: str, indicator_key: str) -> float | None:
    code = _INDICATORS[indicator_key]
    url  = _WB_BASE.format(iso=iso, code=code)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "CatalystEdge/1.0 contact@catalystedge.com"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        # World Bank returns [metadata, [records...]]
        records = data[1] if len(data) > 1 else []
        for rec in records:
            val = rec.get("value")
            if val is not None:
                return float(val)
    except Exception as exc:
        print(f"  WARN: World Bank {iso}/{indicator_key}: {exc}")
    return None


def compute_sovereign_drag(gdp_growth: float | None,
                            debt_to_gdp: float | None) -> tuple[float, str]:
    """
    Compute the Sovereign Drag multiplier and signal for a country.

    Returns (drag_multiplier, signal_label).
    """
    drag = 1.0

    # Debt-to-GDP structural baseline
    if debt_to_gdp is not None:
        if debt_to_gdp > _DEBT_CRITICAL:
            drag = 0.88
            signal = "systemic_risk"
        elif debt_to_gdp > _DEBT_HIGH:
            drag = 0.93
            signal = "elevated_debt"
        elif debt_to_gdp > _DEBT_MODERATE:
            drag = 0.97
            signal = "moderate_debt"
        else:
            drag = 1.0
            signal = "healthy"
    else:
        signal = "unknown"

    # GDP growth modifier
    if gdp_growth is not None:
        if gdp_growth < _GDP_RECESSION:
            drag = round(drag * 0.95, 4)
            signal = "contraction" if signal == "healthy" else signal + "+contraction"
        elif gdp_growth > _GDP_EXPANSION:
            drag = round(drag * 1.05, 4)
            signal = "expansion" if signal == "healthy" else signal

    return round(drag, 4), signal


def load_sovereign_health() -> dict:
    """Load cached sovereign_health.json. Returns {} if missing."""
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_sovereign_drag(country_iso: str) -> float:
    """
    Quick lookup: return the drag multiplier for a given country ISO code.
    Used by scoring_engine.py for per-ticker sovereign adjustment.
    Returns 1.0 (neutral) if country not found.
    """
    data = load_sovereign_health()
    return data.get("countries", {}).get(country_iso.upper(), {}).get("drag", 1.0)


def main(force: bool = False, countries: list[str] | None = None) -> None:
    targets = countries or DEFAULT_COUNTRIES

    # Check if cache is fresh (monthly refresh)
    cached = load_sovereign_health()
    if not force and cached.get("updated"):
        cached_date = date.fromisoformat(cached["updated"])
        if (date.today() - cached_date).days < 28:
            print(f"sovereign_engine: cache fresh ({cached['updated']}) — skipping")
            print("  Use --force to refresh")
            return

    print(f"sovereign_engine: fetching World Bank data for {len(targets)} countries...")
    result: dict[str, dict] = {}

    for iso in targets:
        gdp   = _fetch_wb(iso, "gdp_growth")
        time.sleep(0.3)
        debt  = _fetch_wb(iso, "debt_to_gdp")
        time.sleep(0.3)
        gdppc = _fetch_wb(iso, "gdp_pc")
        time.sleep(0.3)

        drag, signal = compute_sovereign_drag(gdp, debt)
        result[iso] = {
            "gdp_growth":  round(gdp,   2) if gdp  is not None else None,
            "debt_to_gdp": round(debt,  1) if debt is not None else None,
            "gdp_per_cap": round(gdppc, 0) if gdppc is not None else None,
            "drag":        drag,
            "signal":      signal,
        }
        icon = ("🟢" if drag >= 1.0 else "🟡" if drag >= 0.93 else "🔴")
        print(f"  {iso}  {icon}  drag={drag:.4f}  GDP={gdp}%  Debt/GDP={debt}%  → {signal}")

    snap = {
        "updated":   date.today().isoformat(),
        "countries": result,
    }
    OUT.write_text(json.dumps(snap, indent=2), encoding="utf-8")

    dragged = sum(1 for c in result.values() if c["drag"] < 1.0)
    print(f"\nsovereign_engine: {len(result)} countries | "
          f"{dragged} with sovereign drag | sovereign_health.json written")


if __name__ == "__main__":
    import sys
    force    = "--force" in sys.argv
    country_arg = next((a.split("=")[1] for a in sys.argv
                        if a.startswith("--countries=")), None)
    ctry_list = [c.strip().upper() for c in country_arg.split(",")] if country_arg else None
    main(force=force, countries=ctry_list)
