#!/usr/bin/env python3
"""macro_engine.py — Real-Time Atmospheric Pressure for the Cerebro Physics Engine.

Architecture: Three-layer macro signal.

  Layer 1 (FRED Baseline) — loaded from macro_layer.json built nightly by
  build_macro_layer.py.  Captures the macro regime: Fed Funds Rate, CPI, M2,
  2Y Treasury.  Updates daily. Slow-moving "ocean floor."

  Layer 2 (Live TNX Delta) — polls ^TNX from Yahoo Finance every 15 minutes
  during market hours.  Captures the real-time 10Y yield move on top of the
  FRED baseline.  Fast-moving "atmospheric weather."

  Layer 3 (Barometer Sensors) — Yield Curve (2Y-10Y spread), Real Rate
  (r = TNX - CPI), and Recession Warning flag.  Governs global velocity caps.

Barometer Sensors:
    Monetary Sun  ($TNX)      — 10Y Treasury. Baseline for all risk.
    Yield Curve   (2Y-10Y)    — Negative spread = recessionary clouds.
    Inflation Buffer (CPI)    — Net Interest Rate Physics: r = TNX - CPI.

Combined pressure formula:
    P_sector = BaseMultiplier × LiveDeltaAdjustment

Where:
    BaseMultiplier    = macro_layer.json[sector]["multiplier"]  (FRED-driven)
    LiveDeltaAdjust   = 1 - (TNX_live_delta × rate_sensitivity[sector])
    TNX_live_delta    = (TNX_current - TNX_baseline) / 100  (% → decimal)

Final integration into Brightness:
    Brightness = Gravity × (1 + Σ Velocity_decay) × P_sector
    If recession_warning: SmallCap Velocity × 0.80 (credit tightening cap)

Spike detection:
    If TNX moves ≥ 0.15% in 15 min → write alert to macro_pressure.json
    Suppressed sectors (P < 0.90) get headwind flag
    Favored sectors   (P > 1.05) get tailwind flag

HUD visualization hints (Unreal Engine phase):
    Tech sector plate sinks 50 units when TNX spikes
    Inflation haze (red tint) when real_rate < 0
    Recession clouds dim entire map, small cap nodes suppressed

Output: macro_pressure.json
    {
      "timestamp": "2026-04-04T08:30:00",
      "tnx_live":  4.51,
      "tnx_baseline": 4.21,
      "tnx_delta": 0.30,
      "yield_curve_spread": 0.45,
      "yield_curve_inverted": false,
      "real_rate": 1.21,
      "recession_warning": false,
      "small_cap_velocity_cap": 1.0,
      "spike_alert": false,
      "pressures": {
        "tech":        {"multiplier": 0.82, "signal": "headwind"},
        "financials":  {"multiplier": 1.12, "signal": "tailwind"},
        ...
      }
    }

Run modes:
    python3 macro_engine.py              # single poll + write
    python3 macro_engine.py --watch      # continuous 15-min loop (market hours)
    python3 macro_engine.py --hourly     # hourly FRED refresh (yield curve check)
    python3 macro_engine.py --status     # print current pressure table

Pure stdlib — no numpy/pandas.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
UA   = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 contact@catalystedge.com")

# ── DXY (Dollar Strength) sensitivity per sector ─────────────────────────────
# Positive  = sector HURT when DXY rises (multinational revenue headwind)
# Negative  = sector HELPED when DXY rises (USD-denominated asset inflow)
# A rising dollar chokes multinational earnings and compresses commodity prices.
DXY_SENSITIVITY: dict[str, float] = {
    "tech":        0.60,   # AAPL/MSFT/GOOGL — largest multinational revenue drag
    "semis":       0.55,   # Major export sector; NVDA/TSMC USD pricing
    "materials":   0.50,   # Commodities priced in USD — strong dollar = lower prices
    "energy":      0.45,   # Oil/gas USD-denominated; rising dollar = demand drag
    "consumer":    0.40,   # Nike/SBUX multinational brand exposure
    "industrials": 0.35,   # Exports hurt by strong dollar
    "comms":       0.25,   # Alphabet/Meta — partial international exposure
    "biotech":     0.20,   # Mostly domestic trials/revenue
    "staples":     0.15,   # Defensive; some international (PG, KO)
    "utilities":   0.08,   # Almost entirely domestic
    "real_estate": 0.05,   # Domestic only; dollar-insensitive
    "financials": -0.30,   # USD assets appreciate; foreign capital inflow tailwind
}

# DXY baseline (long-run average) — moves relative to this determine pressure
DXY_BASELINE = 103.0   # approximate Q1 2026 DXY level

# ── Rate sensitivity per sector (10Y yield direction)  ───────────────────────
# Positive  = sector HURT when yields rise (headwind)
# Negative  = sector HELPED when yields rise (tailwind / reflation trade)
RATE_SENSITIVITY: dict[str, float] = {
    "real_estate":  0.90,   # REITs are leveraged bond-proxies — most rate-sensitive
    "tech":         0.85,   # Long-duration growth assets tank on discount rate rise
    "utilities":    0.75,   # Bond proxies — investors dump them for actual bonds
    "biotech":      0.70,   # Speculative; high-rate env raises hurdle rate for R&D
    "semis":        0.65,   # Capex-heavy; borrowing costs bite hard
    "comms":        0.50,   # AT&T-style debt burden vs. Google cash neutralizes
    "consumer":     0.35,   # Higher mortgage/auto rates squeeze discretionary spend
    "industrials":  0.30,   # Infrastructure projects get delayed but not cancelled
    "materials":    0.20,   # Commodity prices partially offset rate drag
    "energy":       0.15,   # Oil cash flows & inflation-hedge properties insulate
    "staples":      0.10,   # Defensive; consumers still buy toothpaste at 5% rates
    "financials":  -0.45,   # Net interest margin EXPANDS when yields rise — pure tailwind
}

# Bounds for the combined pressure multiplier
P_MIN = 0.60   # maximum suppression — sector at 60% normal velocity
P_MAX = 1.45   # maximum boost — sector at 145% normal velocity

# Spike threshold: TNX delta in 15 min that triggers an alert
SPIKE_THRESHOLD_PCT = 0.15  # 15 basis points

# Market hours (ET) — only poll during these hours on weekdays
MARKET_OPEN_ET  = 8   # start polling 30 min before regular open
MARKET_CLOSE_ET = 20  # stop polling 2 h after close


# ── Yahoo Finance live TNX fetch ──────────────────────────────────────────────
def _fetch_tnx_chart() -> dict:
    """Fetch ^TNX via Yahoo Finance chart API (v8). Returns meta dict."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1m&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        d = json.loads(r.read())
    return d["chart"]["result"][0]["meta"]


def fetch_tnx_live() -> float | None:
    """Fetch current 10Y Treasury yield from Yahoo Finance ^TNX. Returns % or None."""
    try:
        meta = _fetch_tnx_chart()
        val  = meta.get("regularMarketPrice")
        return float(val) if val is not None else None
    except Exception as exc:
        print(f"  WARN: TNX fetch failed: {exc}")
    return None


def fetch_tnx_previous_close() -> float | None:
    """Fetch TNX previous close for overnight delta calculation."""
    try:
        meta = _fetch_tnx_chart()
        val  = meta.get("previousClose") or meta.get("chartPreviousClose")
        return float(val) if val is not None else None
    except Exception:
        return None


# ── Yahoo Finance live DXY fetch ─────────────────────────────────────────────
def fetch_dxy_live() -> float | None:
    """Fetch current U.S. Dollar Index (DXY) from Yahoo Finance DX-Y.NYB."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1m&range=1d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        meta = d["chart"]["result"][0]["meta"]
        val  = meta.get("regularMarketPrice")
        return float(val) if val is not None else None
    except Exception as exc:
        print(f"  WARN: DXY fetch failed: {exc}")
    return None


# ── Load FRED baseline from existing macro_layer.json ────────────────────────
def load_macro_baseline() -> dict:
    """
    Load the FRED-driven macro state from macro_layer.json.
    Returns dict with 'tnx_baseline', 'multipliers', 'signals', 'macro'.
    """
    p = ROOT / "macro_layer.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d
        except Exception:
            pass
    # Hard fallback (Q1 2026 snapshot)
    return {
        "macro": {"treasury_10y": 4.21, "fed_funds_rate": 4.33, "cpi_yoy": 3.1},
        "multipliers": {s: 1.0 for s in RATE_SENSITIVITY},
        "signals": {s: "neutral" for s in RATE_SENSITIVITY},
    }


# ── Barometer sensor helpers ─────────────────────────────────────────────────
def compute_yield_curve(tnx_live: float | None, baseline: dict) -> dict:
    """
    Compute yield curve spread (10Y - 2Y) and recession warning flag.

    Uses live ^TNX for the 10Y leg; FRED DGS2 from baseline for the 2Y leg
    (Yahoo Finance has no clean live 2Y symbol — daily FRED precision is sufficient
    for the recession flag which moves on a multi-week timescale).

    Returns dict with spread, inverted, recession_warning, real_rate.
    """
    macro = baseline.get("macro", {})
    t2y   = macro.get("treasury_2y")   # FRED DGS2 — daily
    cpi   = macro.get("cpi_yoy")       # FRED CPI YoY

    t10y = tnx_live if tnx_live is not None else macro.get("treasury_10y")

    spread   = None
    inverted = False
    if t10y is not None and t2y is not None:
        spread   = round(t10y - t2y, 3)
        inverted = spread < 0

    # Also check baseline flag from build_macro_layer.py
    if not inverted:
        inverted = baseline.get("yield_curve_inverted", False)

    # Net Interest Rate Physics: r = 10Y nominal - CPI inflation
    real_rate = None
    if t10y is not None and cpi is not None:
        real_rate = round(t10y - cpi, 3)

    # Recession warning: yield curve inverted AND real rate elevated
    # (inverted alone can be transient; combination is the "Recession Cloud" signal)
    recession_warning = inverted

    return {
        "yield_curve_spread":   spread,
        "yield_curve_inverted": inverted,
        "real_rate":            real_rate,
        "recession_warning":    recession_warning,
        # HUD: small_cap_velocity_cap applied by scoring_engine.py
        "small_cap_velocity_cap": 0.80 if recession_warning else 1.0,
    }


def hourly_fred_refresh(baseline: dict) -> dict:
    """
    Lightweight FRED refresh — fetches only DGS10 and DGS2 to update yield curve.
    Called by --hourly mode without rebuilding the full macro_layer.json.
    Returns updated baseline dict (does NOT write macro_layer.json).
    """
    from urllib.request import Request, urlopen
    FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

    def _fetch_last(series_id: str) -> float | None:
        try:
            req = Request(FRED_CSV + series_id,
                          headers={"User-Agent": "CatalystEdge/1.0"})
            with urlopen(req, timeout=15) as r:
                lines = r.read().decode("utf-8").strip().splitlines()
            for line in reversed(lines[1:]):  # skip header, newest last
                parts = line.split(",")
                if len(parts) >= 2 and parts[1].strip() != ".":
                    try:
                        return float(parts[1].strip())
                    except ValueError:
                        continue
        except Exception as exc:
            print(f"  WARN: hourly FRED fetch {series_id}: {exc}")
        return None

    t10y = _fetch_last("DGS10")
    t2y  = _fetch_last("DGS2")

    macro = baseline.setdefault("macro", {})
    if t10y is not None:
        macro["treasury_10y"] = t10y
    if t2y is not None:
        macro["treasury_2y"] = t2y

    if t10y is not None and t2y is not None:
        spread = round(t10y - t2y, 3)
        baseline["yield_curve_spread"]   = spread
        baseline["yield_curve_inverted"] = spread < 0
        print(f"  hourly FRED: 10Y={t10y} | 2Y={t2y} | spread={spread:+.3f}"
              f" {'⚠️ INVERTED' if spread < 0 else '✓ normal'}")
    return baseline


# ── Core pressure calculator ──────────────────────────────────────────────────
def calculate_pressure(tnx_live: float, baseline: dict,
                       dxy_live: float | None = None) -> dict:
    """
    Compute real-time sector pressure multipliers.

    P_sector = BaseMultiplier × TNX_LiveAdj × DXY_LiveAdj

    TNX_LiveAdj = 1 - (TNX_delta/100 × rate_sensitivity)
    DXY_LiveAdj = 1 - (DXY_delta/DXY_baseline × dxy_sensitivity)

    Parameters
    ----------
    tnx_live : float        Current 10Y yield in % (e.g. 4.51)
    baseline : dict         Output of load_macro_baseline()
    dxy_live : float|None   Current DXY level (e.g. 104.5); None = no adjustment

    Returns
    -------
    dict with 'pressures', 'tnx_delta', 'dxy_live', 'spike_alert', alerts[]
    """
    tnx_base   = baseline.get("macro", {}).get("treasury_10y") or 4.21
    base_mults = baseline.get("multipliers", {})

    # TNX delta in percentage points (e.g., 4.51 - 4.21 = +0.30)
    tnx_delta     = round(tnx_live - tnx_base, 4)
    tnx_delta_dec = tnx_delta / 100.0

    # DXY delta as fraction of baseline (e.g., 104.5 - 103.0 = +1.5 / 103.0 = +0.0146)
    dxy_delta_frac = 0.0
    if dxy_live is not None:
        dxy_baseline_val = baseline.get("macro", {}).get("dxy") or DXY_BASELINE
        dxy_delta_frac   = (dxy_live - dxy_baseline_val) / dxy_baseline_val

    pressures: dict[str, dict] = {}
    for sector, rate_sens in RATE_SENSITIVITY.items():
        base_mult = base_mults.get(sector, 1.0)
        # TNX adjustment
        tnx_adj = 1.0 - (tnx_delta_dec * rate_sens)
        # DXY adjustment: rising dollar = additional drag for exposed sectors
        dxy_sens = DXY_SENSITIVITY.get(sector, 0.0)
        dxy_adj  = 1.0 - (dxy_delta_frac * dxy_sens)
        combined  = round(
            max(P_MIN, min(P_MAX, base_mult * tnx_adj * dxy_adj)), 4)
        live_adj  = round(tnx_adj * dxy_adj, 4)

        if combined >= 1.08:
            signal = "strong_tailwind"
        elif combined >= 1.03:
            signal = "tailwind"
        elif combined <= 0.82:
            signal = "strong_headwind"
        elif combined <= 0.92:
            signal = "headwind"
        else:
            signal = "neutral"

        pressures[sector] = {
            "multiplier":  combined,
            "base":        round(base_mult, 4),
            "live_adj":    live_adj,
            "tnx_adj":     round(tnx_adj, 4),
            "dxy_adj":     round(dxy_adj, 4),
            "signal":      signal,
            "rate_beta":   rate_sens,
            "dxy_beta":    dxy_sens,
        }

    # Spike detection
    spike = abs(tnx_delta) >= SPIKE_THRESHOLD_PCT
    alerts = []
    if spike:
        direction = "↑ surging" if tnx_delta > 0 else "↓ falling"
        affected  = [s for s, d in pressures.items()
                     if d["signal"] in ("strong_headwind", "headwind")]
        favored   = [s for s, d in pressures.items()
                     if d["signal"] in ("tailwind", "strong_tailwind")]
        alerts.append({
            "type":      "tnx_spike",
            "severity":  "high" if abs(tnx_delta) >= 0.25 else "medium",
            "message":   f"^TNX {direction} {abs(tnx_delta):.2f}% above FRED baseline "
                         f"({tnx_live:.2f}% vs {tnx_base:.2f}%)",
            "headwinds": affected,
            "tailwinds": favored,
        })

    return {
        "tnx_delta":   tnx_delta,
        "dxy_live":    dxy_live,
        "dxy_delta":   round(dxy_delta_frac * 100, 3),  # as % change
        "spike_alert": spike,
        "pressures":   pressures,
        "alerts":      alerts,
    }


# ── Write macro_pressure.json ─────────────────────────────────────────────────
def write_pressure(tnx_live: float | None, baseline: dict,
                   prev_tnx: float | None = None,
                   dxy_live: float | None = None) -> dict:
    """Compute and persist current macro pressure snapshot."""
    # Barometer sensors — computed for all modes
    barometer = compute_yield_curve(tnx_live, baseline)

    if tnx_live is None:
        # Market closed or Yahoo unavailable — use FRED baseline as-is
        pressures = {
            s: {"multiplier": baseline.get("multipliers", {}).get(s, 1.0),
                "base": baseline.get("multipliers", {}).get(s, 1.0),
                "live_adj": 1.0,
                "signal": baseline.get("signals", {}).get(s, "neutral"),
                "rate_beta": RATE_SENSITIVITY.get(s, 0)}
            for s in RATE_SENSITIVITY
        }
        snap = {
            "timestamp":             datetime.now(timezone.utc).isoformat(),
            "tnx_live":              None,
            "tnx_baseline":          baseline.get("macro", {}).get("treasury_10y"),
            "tnx_delta":             0.0,
            "dxy_live":              dxy_live,
            "dxy_baseline":          baseline.get("macro", {}).get("dxy", DXY_BASELINE),
            "yield_curve_spread":    barometer["yield_curve_spread"],
            "yield_curve_inverted":  barometer["yield_curve_inverted"],
            "real_rate":             barometer["real_rate"],
            "recession_warning":     barometer["recession_warning"],
            "small_cap_velocity_cap": barometer["small_cap_velocity_cap"],
            "spike_alert":           False,
            "pressures":             pressures,
            "alerts":                [],
            "source":                "fred_baseline_only",
        }
    else:
        result = calculate_pressure(tnx_live, baseline, dxy_live=dxy_live)
        # 15-min spike detection using previous poll value
        intraday_spike = False
        if prev_tnx is not None:
            intraday_delta = abs(tnx_live - prev_tnx)
            intraday_spike = intraday_delta >= SPIKE_THRESHOLD_PCT
            if intraday_spike:
                direction = "↑" if tnx_live > prev_tnx else "↓"
                result["alerts"].append({
                    "type":     "tnx_15min_spike",
                    "severity": "high",
                    "message":  (f"^TNX {direction} {intraday_delta:.2f}% "
                                 f"in 15 min ({prev_tnx:.2f}% → {tnx_live:.2f}%)"),
                })

        # Recession warning → add alert
        if barometer["recession_warning"]:
            spread = barometer["yield_curve_spread"]
            result["alerts"].append({
                "type":     "recession_warning",
                "severity": "high",
                "message":  (f"Yield curve inverted: 10Y-2Y = {spread:+.3f}% — "
                             f"SmallCap velocity capped at 80%"),
            })

        snap = {
            "timestamp":             datetime.now(timezone.utc).isoformat(),
            "tnx_live":              round(tnx_live, 4),
            "tnx_baseline":          baseline.get("macro", {}).get("treasury_10y"),
            "tnx_delta":             result["tnx_delta"],
            "dxy_live":              round(dxy_live, 3) if dxy_live else None,
            "dxy_baseline":          baseline.get("macro", {}).get("dxy", DXY_BASELINE),
            "dxy_delta_pct":         result.get("dxy_delta", 0.0),
            "yield_curve_spread":    barometer["yield_curve_spread"],
            "yield_curve_inverted":  barometer["yield_curve_inverted"],
            "real_rate":             barometer["real_rate"],
            "recession_warning":     barometer["recession_warning"],
            "small_cap_velocity_cap": barometer["small_cap_velocity_cap"],
            "spike_alert":           result["spike_alert"] or intraday_spike,
            "pressures":             result["pressures"],
            "alerts":                result["alerts"],
            "source":                "live_tnx",
        }

    out_path = ROOT / "macro_pressure.json"
    out_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


# ── Status display ────────────────────────────────────────────────────────────
def print_status(snap: dict) -> None:
    tnx  = snap.get("tnx_live") or "N/A"
    base = snap.get("tnx_baseline") or "N/A"
    delt = snap.get("tnx_delta", 0)
    ts   = snap.get("timestamp", "")[:19]

    yc_spread  = snap.get("yield_curve_spread")
    real_rate  = snap.get("real_rate")
    recession  = snap.get("recession_warning", False)
    sc_cap     = snap.get("small_cap_velocity_cap", 1.0)
    dxy        = snap.get("dxy_live") or "N/A"
    dxy_base   = snap.get("dxy_baseline", DXY_BASELINE)
    dxy_delta  = snap.get("dxy_delta_pct", 0.0)

    print(f"\n{'─'*60}")
    print(f"  Macro Atmosphere  [{ts} UTC]")
    print(f"{'─'*60}")
    print(f"  ^TNX Live   : {tnx}%")
    print(f"  FRED Base   : {base}%")
    print(f"  TNX Delta   : {delt:+.3f}%  "
          f"({'⚡ SPIKE ALERT' if snap.get('spike_alert') else 'within normal'})")
    dxy_str = f"{dxy:.3f}" if isinstance(dxy, float) else str(dxy)
    dxy_base_str = f"{dxy_base:.1f}" if isinstance(dxy_base, (int, float)) else "N/A"
    dxy_delta_str = f"{dxy_delta:+.2f}%" if isinstance(dxy_delta, (int, float)) else "N/A"
    print(f"  DXY Live    : {dxy_str}  (base {dxy_base_str}, Δ{dxy_delta_str})")
    yc_str = f"{yc_spread:+.3f}%" if yc_spread is not None else "N/A"
    rr_str = f"{real_rate:+.2f}%" if real_rate is not None else "N/A"
    print(f"  Yield Curve : {yc_str}  "
          f"({'⚠️ INVERTED — Recession Warning' if recession else '✓ normal'})")
    print(f"  Real Rate   : {rr_str}  (r = TNX - CPI)")
    if recession:
        print(f"  SmallCap Cap: {sc_cap:.0%}  (credit tightening active)")
    print(f"\n  {'Sector':15s}  {'Pressure':>9s}  Signal")
    print(f"  {'─'*40}")

    pressures = snap.get("pressures", {})
    for sector, d in sorted(pressures.items(),
                             key=lambda x: x[1]["multiplier"]):
        m = d["multiplier"]
        sig = d["signal"]
        icon = ("🚀" if "tailwind"  in sig else
                "⚠️" if "headwind" in sig else "◆")
        bar_len = int((m - 0.6) / 0.85 * 20)
        bar  = "█" * max(0, bar_len)
        print(f"  {sector:15s}  {m:6.4f}x   {icon}  {sig}")

    if snap.get("alerts"):
        print(f"\n  ⚡ Alerts:")
        for a in snap["alerts"]:
            print(f"    [{a['severity'].upper()}] {a['message']}")
    print(f"{'─'*60}\n")


# ── Main / watch loop ─────────────────────────────────────────────────────────
def is_market_hours() -> bool:
    """True during weekday market hours ET (UTC-4 in summer, UTC-5 in winter)."""
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    # Approximate ET offset (doesn't handle DST boundary exactly)
    hour_et = (now_utc.hour - 4) % 24
    return MARKET_OPEN_ET <= hour_et < MARKET_CLOSE_ET


def main() -> None:
    watch   = "--watch"  in sys.argv
    status  = "--status" in sys.argv
    hourly  = "--hourly" in sys.argv

    baseline = load_macro_baseline()
    prev_tnx = None

    if hourly:
        # Hourly FRED refresh — updates yield curve / recession warning without
        # rebuilding the full macro_layer.json.  Add to crontab:
        # 0 * * * 1-5 cd /opt/catalyst && python3 macro_engine.py --hourly
        print(f"macro_engine: hourly FRED refresh [{datetime.now().strftime('%H:%M')}]")
        baseline = hourly_fred_refresh(baseline)
        tnx  = fetch_tnx_live()
        snap = write_pressure(tnx, baseline)
        print_status(snap)
        return

    if status:
        # Load existing snapshot and display
        p = ROOT / "macro_pressure.json"
        if p.exists():
            snap = json.loads(p.read_text())
        else:
            tnx  = fetch_tnx_live()
            snap = write_pressure(tnx, baseline)
        print_status(snap)
        return

    if watch:
        print(f"macro_engine: watch mode — polling ^TNX + DXY every 15 min")
        print(f"  Market hours only: {MARKET_OPEN_ET}:00–{MARKET_CLOSE_ET}:00 ET weekdays")
        while True:
            if is_market_hours():
                tnx  = fetch_tnx_live()
                dxy  = fetch_dxy_live()
                snap = write_pressure(tnx, baseline, prev_tnx=prev_tnx, dxy_live=dxy)
                print_status(snap)
                if tnx:
                    prev_tnx = tnx
                # Reload baseline in case build_macro_layer.py ran overnight
                baseline = load_macro_baseline()
            else:
                print(f"  [{datetime.now().strftime('%H:%M')}] Market closed — sleeping")
            time.sleep(15 * 60)  # 15 minutes
    else:
        # Single poll
        tnx  = fetch_tnx_live()
        dxy  = fetch_dxy_live()
        snap = write_pressure(tnx, baseline, dxy_live=dxy)
        print_status(snap)
        print(f"macro_engine: macro_pressure.json updated")


if __name__ == "__main__":
    main()
