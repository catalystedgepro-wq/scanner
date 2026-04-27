#!/usr/bin/env python3
"""scoring_engine.py — Exponential Velocity Decay & Node Brightness Calculator.

Physics Model (Cerebro Architecture Directive):
    Brightness = Gravity × (1 + Σ BaseVelocity_i × e^(−k × t_i))

Where:
    Gravity      — static node weight (from gravity_engine.py)
    BaseVelocity — raw catalyst score at moment of filing discovery
    t            — hours elapsed since filing was discovered
    k            — decay constant (0.05 → 72-hour ember cycle)

Decay calibration at k=0.05:
    t =  0h → 100% intensity  (The Bang — 4 AM filing hit)
    t =  4h →  82% intensity  (Pre-market / Open high alert)
    t = 24h →  30% intensity  (The Glow — Day 2 follow-through)
    t = 48h →   9% intensity  (Fading signal)
    t = 72h →  2.7% intensity (The Ember — historical trail)

Multiple filings STACK — each adds its own decay curve. 10 filings in 48h
will keep a sector visibly bright long after a single-filing ticker dims.

Pure stdlib — no numpy/pandas.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

ROOT = Path(__file__).parent

# Default decay constant — tune here to adjust the ember window
DEFAULT_K = 0.05


def decay_factor(hours_elapsed: float, k: float = DEFAULT_K) -> float:
    """e^(-k*t) decay factor. Returns 1.0 at t=0, approaches 0 as t→∞."""
    return math.exp(-k * max(0.0, hours_elapsed))


def load_macro_pressure(sector: str) -> float:
    """Load the current atmospheric pressure multiplier for a sector from macro_pressure.json.
    Returns 1.0 (neutral) if the file is missing or sector not found."""
    p = ROOT / "macro_pressure.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            return d.get("pressures", {}).get(sector, {}).get("multiplier", 1.0) or 1.0
        except Exception:
            pass
    return 1.0


def load_macro_snapshot() -> dict:
    """Load the full macro_pressure.json snapshot. Returns {} if unavailable."""
    p = ROOT / "macro_pressure.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def load_collision_shock(ticker: str) -> float:
    """
    Load the Physical Shock velocity boost for a ticker from collision_alerts.json.
    Returns the maximum shock_velocity across all active Domain 3 collisions,
    or 0.0 if no collisions.
    """
    p = ROOT / "collision_alerts.json"
    if not p.exists():
        return 0.0
    try:
        d = json.loads(p.read_text())
        hits = d.get("by_ticker", {}).get(ticker.upper(), [])
        if hits:
            return max(c.get("shock_velocity", 0.0) for c in hits)
    except Exception:
        pass
    return 0.0


# Cache spark_velocities.json in memory for the scoring run
_spark_cache: dict | None = None

def load_spark_velocity(ticker: str) -> float:
    """
    Load Domain 4+6 spark velocity for a ticker from spark_velocities.json.
    Returns net velocity = patent boost + legal penalty + digital buzz/fade.
    Patent grants inject +velocity (Innovation Aura).
    Lawsuits inject -velocity (Structural Crack).
    Digital search surge/spike injects +velocity; fade injects -velocity.
    """
    global _spark_cache
    if _spark_cache is None:
        p = ROOT / "spark_velocities.json"
        if p.exists():
            try:
                _spark_cache = json.loads(p.read_text())
            except Exception:
                _spark_cache = {}
        else:
            _spark_cache = {}
    entry = _spark_cache.get(ticker.upper(), {})
    patent       = entry.get("patent",       0.0)
    legal        = entry.get("legal",        0.0)
    digital      = entry.get("digital",      0.0)
    options      = entry.get("options",      0.0)
    supply_chain = entry.get("supply_chain", 0.0)
    return round(patent + legal + digital + options + supply_chain, 4)


# Small-cap tier labels that receive the recession velocity cap
_SMALL_CAP_TIERS = frozenset({"small", "micro", "nano"})


def calculate_node_intensity(gravity_score: float,
                             catalyst_events: list[dict],
                             decay_constant: float = DEFAULT_K,
                             macro_pressure: float = 1.0,
                             cap_tier: str = "unknown",
                             macro_snap: dict | None = None,
                             ticker: str = "") -> float:
    """
    Calculate live Brightness for a ticker node.

    Parameters
    ----------
    gravity_score : float
        Static Gravity score (1–100, from GravityEngine).
    catalyst_events : list of dict
        Each dict must have:
          'score'     : float — raw catalyst/gap score at filing time
          'timestamp' : float — Unix timestamp when filing was discovered
    decay_constant : float
        k in e^(-k*t). Default 0.05 = 72h ember cycle.
    macro_pressure : float
        Atmospheric pressure multiplier for the ticker's sector (P_sector).
    cap_tier : str
        Market cap tier: 'mega','large','mid','small','micro','nano','unknown'.
        Small/micro/nano tickers get velocity capped 20% when recession_warning active.
    macro_snap : dict | None
        Full macro_pressure.json snapshot. If None, loaded on demand.

    Returns
    -------
    float  Brightness value (≥ gravity_score; no upper bound by design,
           so a cluster of filings can "supernova" a sector visually).
    """
    current_time = time.time()
    total_velocity = 0.0

    for event in catalyst_events:
        ts   = event.get("timestamp") or current_time
        base = event.get("score", 0.0)
        if base <= 0:
            continue
        hours_elapsed = (current_time - ts) / 3600.0
        decayed = base * decay_factor(hours_elapsed, decay_constant)
        total_velocity += decayed

    # Recession Warning: cap small-cap velocity by 20% (credit tightening)
    if total_velocity > 0 and cap_tier in _SMALL_CAP_TIERS:
        snap = macro_snap if macro_snap is not None else load_macro_snapshot()
        sc_cap = snap.get("small_cap_velocity_cap", 1.0)
        if sc_cap < 1.0:
            total_velocity *= sc_cap

    # Domain 3: Physical Shock — inject collision velocity boost
    # A factory inside a NOAA storm polygon gets +15 velocity immediately
    if ticker:
        shock = load_collision_shock(ticker)
        if shock > 0:
            total_velocity += shock

    # Domain 4: Innovation Spark / Legal Risk
    # Patent grants → Innovation Aura (+velocity), Lawsuits → Structural Crack (-velocity)
    if ticker:
        spark = load_spark_velocity(ticker)
        if spark != 0.0:
            total_velocity += spark

    # Final Brightness = Gravity × ln(1 + Velocity) × Atmospheric Pressure
    # F-8 fix: log-compression prevents supernova blinding in HUD.
    # Weber-Fechner law: human perception of intensity is logarithmic.
    compressed_velocity = math.log(1.0 + max(0.0, total_velocity))
    brightness = gravity_score * (1.0 + compressed_velocity) * macro_pressure
    return round(brightness, 2)


def calculate_sector_brightness(sector_key: str,
                                entity_master: dict,
                                catalyst_log: list[dict],
                                decay_constant: float = DEFAULT_K) -> float:
    """
    Aggregate brightness for an entire sector.

    Parameters
    ----------
    sector_key : str
        e.g. 'biotech', 'financials'
    entity_master : dict
        {ticker: {gravity, gics: {s, ig, i, si}, ...}}
    catalyst_log : list of dict
        All catalyst events — {ticker, score, timestamp, form}
    """
    # Filter events for tickers in this sector
    sector_tickers = {
        t for t, r in entity_master.items()
        if (r.get("gics") or {}).get("s") == sector_key
    }

    # Group events by ticker
    events_by_ticker: dict[str, list] = {}
    for ev in catalyst_log:
        t = ev.get("ticker", "").upper()
        if t in sector_tickers:
            events_by_ticker.setdefault(t, []).append(ev)

    total_brightness = 0.0
    for ticker in sector_tickers:
        g = (entity_master.get(ticker) or {}).get("gravity") or 1.0
        evs = events_by_ticker.get(ticker, [])
        total_brightness += calculate_node_intensity(g, evs, decay_constant)

    return round(total_brightness, 2)


# ── Snapshot builder — used by generate_seo_site.py ──────────────────────────
def build_brightness_snapshot(entity_master: dict,
                              catalyst_log: list[dict],
                              decay_constant: float = DEFAULT_K) -> dict[str, float]:
    """
    Return {ticker: brightness} for all tickers with at least one recent event.
    Only includes tickers active in the last 72h to keep the dict small.
    """
    cutoff = time.time() - 72 * 3600
    active_tickers = {
        ev["ticker"].upper() for ev in catalyst_log
        if ev.get("timestamp", 0) >= cutoff
    }

    out: dict[str, float] = {}
    events_by_ticker: dict[str, list] = {}
    for ev in catalyst_log:
        t = ev.get("ticker", "").upper()
        if t in active_tickers:
            events_by_ticker.setdefault(t, []).append(ev)

    for ticker in active_tickers:
        g = (entity_master.get(ticker) or {}).get("gravity") or 1.0
        out[ticker] = calculate_node_intensity(g, events_by_ticker.get(ticker, []),
                                               decay_constant)
    return out


# ── CLI demo ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import datetime

    def _ts(hours_ago: float) -> float:
        return time.time() - hours_ago * 3600

    print("Exponential Decay Calibration (k=0.05):")
    for t_h in [0, 4, 24, 48, 72, 96]:
        pct = decay_factor(t_h) * 100
        bar = "█" * int(pct / 2)
        print(f"  t={t_h:3d}h  {pct:5.1f}%  {bar}")

    print("\nNode Intensity Examples:")
    # Single 8-K just filed (t=0)
    b1 = calculate_node_intensity(50.0, [{"score": 65.0, "timestamp": _ts(0)}])
    print(f"  Gravity=50, single 8-K at t=0h        → Brightness={b1}")

    # Same 8-K 24h later
    b2 = calculate_node_intensity(50.0, [{"score": 65.0, "timestamp": _ts(24)}])
    print(f"  Gravity=50, single 8-K at t=24h       → Brightness={b2}")

    # Stacked: 3 filings over 48h (Heat Stacking)
    b3 = calculate_node_intensity(50.0, [
        {"score": 65.0, "timestamp": _ts(0)},
        {"score": 40.0, "timestamp": _ts(12)},
        {"score": 30.0, "timestamp": _ts(36)},
    ])
    print(f"  Gravity=50, 3-filing stack t=0/12/36h → Brightness={b3}")

    # HCMC rogue node: micro-cap, tiny gravity, single catalyst
    b4 = calculate_node_intensity(3.0, [{"score": 20.0, "timestamp": _ts(1)}])
    print(f"  HCMC Gravity=3, catalyst t=1h         → Brightness={b4}")

    # Load entity_master if available
    em_path = ROOT / "entity_master.json"
    cl_path = ROOT / "catalyst_log.json"
    if em_path.exists() and cl_path.exists():
        em = json.loads(em_path.read_text())
        cl = json.loads(cl_path.read_text())
        snap = build_brightness_snapshot(em, cl)
        print(f"\nLive snapshot: {len(snap)} active tickers")
        top = sorted(snap.items(), key=lambda x: -x[1])[:10]
        for t, b in top:
            g = (em.get(t) or {}).get("gravity", "?")
            print(f"  {t:8s}  G={g}  Brightness={b}")
