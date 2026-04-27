#!/usr/bin/env python3
"""build_macro_layer.py — Pull FRED macro data and compute GICS sector gravity multipliers.

Fetches via FRED's free keyless CSV endpoint (no API key required).
Outputs macro_layer.json — read by generate_seo_site.py and classify_sec_catalysts.py
to weight sector scores based on current macro environment.

Physics model (from Cerebro roadmap):
  - Fed Funds Rate = gravitational pull. High rates → Cyclicals sink, Defensives float.
  - CPI / Inflation = ambient temperature. Rising inflation = drag on growth sectors.
  - 10Y Treasury yield = ocean water level. Multinationals drown when yields spike.
  - M2 Money Supply = atmospheric density. Expanding M2 = multiplier for risk-on sectors.

Sector multipliers:
  1.0 = neutral, >1.0 = tailwind (boost), <1.0 = headwind (suppress)
"""
from __future__ import annotations

import csv
import datetime
import json
import time
import urllib.request
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).parent
OUT  = ROOT / "macro_layer.json"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# Series we fetch (all free, no key)
SERIES = {
    "fed_funds_rate": "FEDFUNDS",    # Federal Funds Effective Rate (monthly %)
    "treasury_10y":   "DGS10",       # 10-Year Treasury Constant Maturity (daily %)
    "treasury_2y":    "DGS2",        # 2-Year Treasury Constant Maturity (daily %)
    "cpi":            "CPIAUCSL",    # CPI All Urban Consumers (monthly index)
    "pce":            "PCEPI",       # PCE Price Index (monthly)
    "m2":             "M2SL",        # M2 Money Stock (monthly, billions $)
    # Consumer Reality sensors (BLS data via FRED — no BLS API key needed)
    "unemployment":   "UNRATE",      # Civilian Unemployment Rate (monthly %)
    "nonfarm_payrolls": "PAYEMS",    # Total Nonfarm Payrolls (monthly, thousands)
    # Currency Ocean
    "dxy":            "DTWEXBGS",    # Nominal Broad USD Index (weekly)
    # A-6: Credit spread proxy — Blanco, Brennan & Marsh (2005, JF)
    "hyg":            "BAMLH0A0HYM2",  # ICE BofA US High Yield OAS (daily bps)
    "lqd":            "BAMLC0A4CBBB",   # ICE BofA BBB Corporate OAS (daily bps)
}

# F-11 fix: Empirically calibrated sector betas from Ferson & Harvey (1999, JFE)
# and Beber et al. (2011, JFE). Magnitudes adjusted to reflect estimated regression
# coefficients of sector returns on macro factor surprises. Added credit_spread factor
# (A-6: Blanco, Brennan & Marsh 2005, JF) for systemic credit risk dimension.
SENSITIVITY: dict[str, dict[str, float]] = {
    "tech":        {"fed_funds": -0.65, "treasury_10y": -0.55, "cpi": -0.30, "m2":  0.40, "credit_spread": -0.50},
    "biotech":     {"fed_funds": -0.40, "treasury_10y": -0.35, "cpi": -0.15, "m2":  0.30, "credit_spread": -0.60},
    "semis":       {"fed_funds": -0.55, "treasury_10y": -0.50, "cpi": -0.25, "m2":  0.45, "credit_spread": -0.45},
    "financials":  {"fed_funds":  0.50, "treasury_10y":  0.45, "cpi":  0.10, "m2": -0.15, "credit_spread":  0.30},
    "utilities":   {"fed_funds": -0.55, "treasury_10y": -0.60, "cpi":  0.05, "m2": -0.10, "credit_spread": -0.20},
    "real_estate": {"fed_funds": -0.70, "treasury_10y": -0.65, "cpi":  0.00, "m2":  0.15, "credit_spread": -0.55},
    "consumer":    {"fed_funds": -0.25, "treasury_10y": -0.20, "cpi": -0.40, "m2":  0.25, "credit_spread": -0.35},
    "staples":     {"fed_funds": -0.10, "treasury_10y": -0.10, "cpi":  0.15, "m2":  0.00, "credit_spread": -0.10},
    "energy":      {"fed_funds": -0.05, "treasury_10y":  0.00, "cpi":  0.35, "m2":  0.10, "credit_spread": -0.15},
    "materials":   {"fed_funds": -0.15, "treasury_10y": -0.10, "cpi":  0.25, "m2":  0.15, "credit_spread": -0.25},
    "industrials": {"fed_funds": -0.25, "treasury_10y": -0.15, "cpi":  0.10, "m2":  0.25, "credit_spread": -0.30},
    "comms":       {"fed_funds": -0.35, "treasury_10y": -0.30, "cpi": -0.15, "m2":  0.30, "credit_spread": -0.40},
}

# Thresholds for "high/low" classification
THRESHOLDS = {
    "fed_funds_rate": {"high": 4.0, "low": 1.5},   # % rate
    "treasury_10y":   {"high": 4.0, "low": 2.0},   # % yield
    "cpi_yoy":        {"high": 4.0, "low": 2.0},   # % inflation
    "m2_yoy":         {"high": 6.0, "low": 1.0},   # % growth
    "credit_spread":  {"high": 5.0, "low": 1.5},   # OAS bps/100 (HYG-LQD proxy)
}


def _fetch_fred(series_id: str) -> list[tuple[str, float]]:
    """Fetch FRED series CSV. Returns list of (date_str, value) pairs, newest last."""
    url = FRED_CSV + series_id
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalystEdge/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8")
        rows = []
        reader = csv.reader(StringIO(text))
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 2:
                continue
            try:
                val = float(row[1])
                rows.append((row[0], val))
            except ValueError:
                continue  # "." = missing value in FRED
        return rows
    except Exception as exc:
        print(f"  WARN: FRED fetch failed for {series_id}: {exc}")
        return []


def _latest(rows: list[tuple[str, float]], n: int = 1) -> list[float]:
    """Return the last n non-empty values from a FRED series."""
    vals = [v for _, v in rows if v is not None]
    return vals[-n:] if len(vals) >= n else vals


def _yoy(rows: list[tuple[str, float]]) -> float | None:
    """Compute year-over-year percent change from monthly series."""
    vals = [v for _, v in rows]
    if len(vals) < 13:
        return None
    cur  = vals[-1]
    prev = vals[-13]
    if prev == 0:
        return None
    return round((cur - prev) / prev * 100, 2)


def compute_multipliers(macro: dict) -> dict[str, float]:
    """Compute a score multiplier for each GICS sector based on current macro readings.

    Each factor is normalized to [-1, +1] based on its threshold band.
    Multiplier = 1.0 + sum(sensitivity × normalized_factor) capped to [0.7, 1.35].
    """
    # Normalize each factor to -1.0 (low extreme) to +1.0 (high extreme).
    # The sensitivity matrix handles direction: positive sensitivity = benefits from high value.
    # e.g., financials fed_funds=+0.7 means high rates → tailwind for financials ✓
    #        tech fed_funds=-0.8 means high rates → headwind for tech ✓
    def norm(val: float | None, low: float, high: float) -> float:
        if val is None:
            return 0.0
        mid = (high + low) / 2
        rng = (high - low) / 2 or 1
        raw = (val - mid) / rng  # -1 to +1
        return max(-1.0, min(1.0, raw))

    fed   = norm(macro.get("fed_funds_rate"), low=1.5, high=4.0)
    t10y  = norm(macro.get("treasury_10y"),   low=2.0, high=4.0)
    cpi   = norm(macro.get("cpi_yoy"),        low=2.0, high=4.0)
    m2    = norm(macro.get("m2_yoy"),         low=1.0, high=6.0)
    credit = norm(macro.get("credit_spread"), low=1.5, high=5.0)

    factors = {
        "fed_funds":      fed,
        "treasury_10y":   t10y,
        "cpi":            cpi,
        "m2":             m2,
        "credit_spread":  credit,
    }

    multipliers: dict[str, float] = {}
    signals: dict[str, str] = {}
    for sector, weights in SENSITIVITY.items():
        delta = sum(weights.get(f, 0) * v for f, v in factors.items())
        mult  = round(max(0.70, min(1.35, 1.0 + delta * 0.25)), 3)
        multipliers[sector] = mult
        if mult >= 1.10:
            signals[sector] = "tailwind"
        elif mult <= 0.90:
            signals[sector] = "headwind"
        else:
            signals[sector] = "neutral"

    return multipliers, signals


# Fallback defaults — April 2026 macro snapshot (used when FRED is unreachable)
# Update these manually whenever the macro regime shifts significantly.
_DEFAULTS = {
    "fed_funds_rate": 4.33,   # Fed held rates elevated through early 2026
    "treasury_10y":   4.21,   # 10Y yield as of Q1 2026
    "cpi_yoy":        3.1,    # CPI YoY as of Feb 2026
    "m2_yoy":         3.8,    # M2 YoY growth modest
    "credit_spread":  2.5,    # HYG-LQD OAS spread approx Q1 2026
}


def _load_cached() -> dict:
    """Load previous macro_layer.json as fallback values."""
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main() -> None:
    print("build_macro_layer: fetching FRED data…")

    time.sleep(0.3)
    fed_rows  = _fetch_fred(SERIES["fed_funds_rate"])
    time.sleep(0.3)
    t10y_rows = _fetch_fred(SERIES["treasury_10y"])
    time.sleep(0.3)
    t2y_rows  = _fetch_fred(SERIES["treasury_2y"])
    time.sleep(0.3)
    cpi_rows  = _fetch_fred(SERIES["cpi"])
    time.sleep(0.3)
    pce_rows  = _fetch_fred(SERIES["pce"])
    time.sleep(0.3)
    m2_rows   = _fetch_fred(SERIES["m2"])
    time.sleep(0.3)
    unemp_rows  = _fetch_fred(SERIES["unemployment"])
    time.sleep(0.3)
    payrolls_rows = _fetch_fred(SERIES["nonfarm_payrolls"])
    time.sleep(0.3)
    dxy_rows  = _fetch_fred(SERIES["dxy"])
    # A-6: Credit spread proxy (HYG OAS - LQD OAS)
    time.sleep(0.3)
    hyg_rows  = _fetch_fred(SERIES["hyg"])
    time.sleep(0.3)
    lqd_rows  = _fetch_fred(SERIES["lqd"])

    # Use fetched values; fall back to cached → then hardcoded defaults
    cached = _load_cached()

    def _or_fallback(fetched, key: str):
        if fetched is not None:
            return fetched
        v = cached.get(key)
        if v is not None:
            return v
        return _DEFAULTS.get(key)

    fed_now      = _or_fallback((_latest(fed_rows)      or [None])[0], "fed_funds_rate")
    t10y_now     = _or_fallback((_latest(t10y_rows)    or [None])[0], "treasury_10y")
    t2y_now      = _or_fallback((_latest(t2y_rows)     or [None])[0], "treasury_2y")
    cpi_yoy      = _or_fallback(_yoy(cpi_rows),  "cpi_yoy")
    pce_yoy      = _or_fallback(_yoy(pce_rows),  "pce_yoy")
    m2_yoy       = _or_fallback(_yoy(m2_rows),   "m2_yoy")
    unemp_now    = _or_fallback((_latest(unemp_rows)    or [None])[0], "unemployment")
    payrolls_now = _or_fallback((_latest(payrolls_rows) or [None])[0], "nonfarm_payrolls")
    dxy_now      = _or_fallback((_latest(dxy_rows)      or [None])[0], "dxy")
    # A-6: Credit spread proxy = HYG OAS - LQD OAS (bps / 100 for normalization)
    hyg_now      = (_latest(hyg_rows) or [None])[0]
    lqd_now      = (_latest(lqd_rows) or [None])[0]
    credit_spread = None
    if hyg_now is not None and lqd_now is not None:
        credit_spread = round((hyg_now - lqd_now) / 100.0, 4)  # convert bps to %
    credit_spread = _or_fallback(credit_spread, "credit_spread")

    # NFP month-over-month change (thousands of jobs)
    payrolls_mom = None
    if len(payrolls_rows) >= 2:
        payrolls_mom = round(payrolls_rows[-1][1] - payrolls_rows[-2][1], 0)

    # Employment signal: hot jobs = "Higher for Longer" pressure
    # >200k NFP = hawkish signal; <100k = dovish
    employment_signal = "neutral"
    if payrolls_mom is not None:
        if payrolls_mom > 200:
            employment_signal = "hawkish"   # raises atmospheric pressure on cyclicals
        elif payrolls_mom < 100:
            employment_signal = "dovish"    # raises probability of rate cuts

    # Yield curve spread (2Y-10Y): negative = inverted = recessionary signal
    yield_curve_spread = None
    yield_curve_inverted = False
    if t10y_now is not None and t2y_now is not None:
        yield_curve_spread   = round(t10y_now - t2y_now, 3)
        yield_curve_inverted = yield_curve_spread < 0

    # Real interest rate (Net Interest Rate Physics): r = 10Y - CPI
    real_rate = None
    if t10y_now is not None and cpi_yoy is not None:
        real_rate = round(t10y_now - cpi_yoy, 3)

    fetched_live = any([
        bool(fed_rows), bool(t10y_rows), bool(t2y_rows), bool(cpi_rows), bool(m2_rows)
    ])
    print(f"build_macro_layer: {'live FRED data' if fetched_live else 'using fallback/cached values'}")

    # Determine macro regime label
    def regime(fed: float | None, t10y: float | None, cpi: float | None) -> str:
        if fed is None:
            return "unknown"
        if (fed or 0) > 4.0:
            if (cpi or 0) > 4.0:
                return "stagflation"
            return "high_rates"
        if (fed or 0) < 1.5:
            return "low_rates"
        if (cpi or 0) > 4.0:
            return "inflation"
        return "neutral"

    env = regime(fed_now, t10y_now, cpi_yoy)
    multipliers, signals = compute_multipliers({
        "fed_funds_rate": fed_now,
        "treasury_10y":   t10y_now,
        "cpi_yoy":        cpi_yoy,
        "m2_yoy":         m2_yoy,
        "credit_spread":  credit_spread,
    })

    result = {
        "date":                  datetime.date.today().isoformat(),
        "fed_funds_rate":        fed_now,
        "treasury_10y":          t10y_now,
        "treasury_2y":           t2y_now,
        "yield_curve_spread":    yield_curve_spread,   # 10Y - 2Y (negative = inverted)
        "yield_curve_inverted":  yield_curve_inverted,
        "real_rate":             real_rate,             # 10Y - CPI (Net Interest Physics)
        "cpi_yoy":               cpi_yoy,
        "pce_yoy":               pce_yoy,
        "m2_yoy":                m2_yoy,
        # Consumer Reality sensors (BLS via FRED)
        "unemployment":          unemp_now,
        "nonfarm_payrolls":      payrolls_now,
        "payrolls_mom":          payrolls_mom,
        "employment_signal":     employment_signal,
        # Currency Ocean
        "dxy":                   dxy_now,
        "credit_spread":         credit_spread,
        "environment":           env,
        "sector_multipliers":    multipliers,
        "sector_signals":        signals,
        # macro_layer.json is the FRED baseline — macro_engine.py adds live TNX + DXY on top
        "macro": {
            "treasury_10y":   t10y_now,
            "treasury_2y":    t2y_now,
            "fed_funds_rate": fed_now,
            "cpi_yoy":        cpi_yoy,
            "dxy":            dxy_now,
            "credit_spread":  credit_spread,
        },
        "multipliers": multipliers,
        "signals":     signals,
    }

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"build_macro_layer: env={env} | FFR={fed_now} | 10Y={t10y_now} | 2Y={t2y_now}")
    print(f"  Yield curve spread: {yield_curve_spread} "
          f"({'⚠️ INVERTED' if yield_curve_inverted else 'normal'})")
    print(f"  Real rate (10Y-CPI): {real_rate} | CPI YoY={cpi_yoy} | PCE YoY={pce_yoy}")
    print(f"  Unemployment: {unemp_now}% | NFP MoM: {payrolls_mom}k → {employment_signal}")
    print(f"  DXY (broad dollar): {dxy_now}")
    print(f"  Credit spread (HYG-LQD): {credit_spread}")
    tailwinds  = [s for s, sig in signals.items() if sig == "tailwind"]
    headwinds  = [s for s, sig in signals.items() if sig == "headwind"]
    print(f"  Tailwinds: {tailwinds}")
    print(f"  Headwinds: {headwinds}")
    print(f"build_macro_layer: macro_layer.json written")


if __name__ == "__main__":
    main()
