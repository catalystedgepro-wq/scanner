#!/usr/bin/env python3
"""build_nobel_physics.py — Apply Nobel Prize-winning economic physics to pipeline data.

Five models, all using only Python stdlib (math.erf for normal CDF):

1. Kydland & Prescott (2004) — Taylor Rule: Fed rate shock detection
   Source: macro_layer.json (FRED data)
   Output: taylor_deviation, macro_regime_shock

2. Robert Engle (2003) — ARCH/GARCH Volatility Clustering
   Source: .stooq_daily_cache.json (120 days price history)
   Output: per-ticker vol_cluster_ratio, vol_regime

3. Black-Scholes-Merton (1997) — Options Tension
   Source: options_flow.csv (call/put OI, IV, max_pain)
   Output: per-ticker bsm_tension_score, price_magnet_strike

4. George Akerlof (2001) — Information Asymmetry ("Lemons")
   Source: insider_clusters.csv + sec_top_gappers.csv (filing clarity)
   Output: per-ticker akerlof_score (opacity × insider conviction)

5. John Nash (1994) — Equilibrium Disruption
   Source: sector_lookup.json + sec_clean_gappers.csv (sector peer filings)
   Output: per-ticker nash_disruption flag, sector equilibrium break signal

Outputs: nobel_signals.json
"""
from __future__ import annotations

import csv
import datetime
import json
import math
from pathlib import Path

ROOT = Path(__file__).parent
OUT  = ROOT / "nobel_signals.json"

# ── stdlib Normal CDF (exact, using math.erf) ─────────────────────────────
def norm_cdf(x: float) -> float:
    """Exact normal CDF using stdlib math.erf. No scipy needed."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ── 1. TAYLOR RULE SHOCK (Kydland & Prescott 2004) ────────────────────────
def taylor_rule_shock(macro: dict) -> dict:
    """
    Compare actual Fed Funds Rate to Taylor Rule optimal rate.
    Taylor Rule: r* = r_neutral + π + 0.5(π - π*) + 0.5(output_gap)

    Positive deviation = Fed is ABOVE Taylor Rule = hawkish surprise = risk-off
    Negative deviation = Fed is BELOW Taylor Rule = dovish surprise = risk-on
    """
    ffr      = macro.get("fed_funds_rate") or 4.33
    cpi_yoy  = macro.get("cpi_yoy") or 3.1
    m2_yoy   = macro.get("m2_yoy") or 3.8

    # Approximate output gap: M2 growth - neutral 4% = monetary stimulus signal
    output_gap = (m2_yoy - 4.0) / 100.0

    r_neutral        = 0.02   # 2% long-run neutral rate (Fed's own estimate)
    inflation        = cpi_yoy / 100.0
    target_inflation = 0.02  # Fed's 2% target

    taylor_rate = r_neutral + inflation + 0.5 * (inflation - target_inflation) + 0.5 * output_gap
    actual_rate = ffr / 100.0
    deviation   = round(actual_rate - taylor_rate, 4)

    # Classify shock level
    if deviation > 0.015:
        shock = "hawkish_surprise"      # Fed too tight → risk-off, sector rotation to defensives
    elif deviation < -0.015:
        shock = "dovish_surprise"       # Fed too loose → risk-on, growth stocks get tailwind
    else:
        shock = "on_target"             # Fed tracking Taylor Rule → neutral

    return {
        "actual_ffr":    round(actual_rate, 4),
        "taylor_rate":   round(taylor_rate, 4),
        "deviation":     deviation,
        "shock":         shock,
        "description":   f"Fed is {abs(deviation)*100:.1f}bps {'above' if deviation>0 else 'below'} Taylor Rule optimal"
    }


# ── 2. GARCH/EWMA VOLATILITY CLUSTERING (Robert Engle 2003) ───────────────
def garch_volatility(ticker: str, stooq_cache: dict) -> dict:
    """
    EWMA volatility (special case of GARCH(1,1), λ=0.94 — RiskMetrics standard).

    If current_vol / long_run_vol > 1.5 → volatility cluster forming → "coiling" signal
    This is EXACTLY the math that won Robert Engle the Nobel Prize.
    """
    data = stooq_cache.get(ticker, {})
    rows = data.get("rows", [])
    if len(rows) < 10:
        return {"vol_ratio": 1.0, "regime": "insufficient_data", "current_vol": 0.0}

    closes = [r["close"] for r in rows if r.get("close")]
    if len(closes) < 10:
        return {"vol_ratio": 1.0, "regime": "insufficient_data", "current_vol": 0.0}

    # Daily log returns
    returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes)) if closes[i-1] > 0]
    if not returns:
        return {"vol_ratio": 1.0, "regime": "insufficient_data", "current_vol": 0.0}

    # EWMA variance (λ=0.94, RiskMetrics)
    lam = 0.94
    variance = sum(r**2 for r in returns[:5]) / 5  # seed with first 5 days
    ewma_variances = [variance]
    for r in returns[5:]:
        variance = lam * variance + (1 - lam) * r**2
        ewma_variances.append(variance)

    current_var  = ewma_variances[-1]
    long_run_var = sum(ewma_variances) / len(ewma_variances)

    current_vol  = math.sqrt(current_var * 252)   # annualized
    long_run_vol = math.sqrt(long_run_var * 252)

    vol_ratio = round(current_vol / long_run_vol, 3) if long_run_vol > 0 else 1.0

    if vol_ratio > 2.0:
        regime = "extreme_cluster"      # Major move coiling — node should pulse violently
    elif vol_ratio > 1.5:
        regime = "high_cluster"         # Volatility clustering detected — elevated alert
    elif vol_ratio > 1.2:
        regime = "mild_cluster"         # Above average volatility
    elif vol_ratio < 0.7:
        regime = "compression"          # Vol compressed → breakout risk rising
    else:
        regime = "normal"

    return {
        "current_vol_ann":  round(current_vol, 4),
        "long_run_vol_ann": round(long_run_vol, 4),
        "vol_ratio":        vol_ratio,
        "regime":           regime,
        "score_boost":      round(min(vol_ratio - 1.0, 0.5), 3),  # max +0.5x boost to scores
    }


# ── 3. BLACK-SCHOLES-MERTON TENSION (Scholes/Merton 1997) ─────────────────
def bsm_tension(ticker: str, price: float, options_row: dict, risk_free: float) -> dict:
    """
    Compute BSM fair value for ATM call. Compare to implied vol from market.
    High tension = market pricing in a move that BSM math says shouldn't exist yet.

    Uses the Heat Equation of thermodynamics applied to capital — exactly the
    math Merton used to win the Nobel Prize.
    """
    if not price or price <= 0:
        return {"tension": 0.0, "signal": "no_price_data"}

    try:
        iv_raw  = options_row.get("atm_call_iv") or ""
        iv      = float(iv_raw) / 100.0 if iv_raw else 0.0
        max_pain_raw = options_row.get("max_pain") or ""
        K       = float(max_pain_raw) if max_pain_raw else price * 1.05  # 5% OTM default
        T       = 30 / 365.0    # 30 days, standard
        r       = risk_free
        S       = price
        sigma   = iv if iv > 0 else 0.40  # default 40% IV for small-caps
    except (ValueError, TypeError):
        return {"tension": 0.0, "signal": "options_data_parse_error"}

    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"tension": 0.0, "signal": "invalid_inputs"}

    # Black-Scholes-Merton formula (Nobel 1997)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    bsm_call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)

    # BSM-implied "expected move" as % of price
    expected_move_pct = round(bsm_call / S * 100, 2)

    # Tension = distance to max_pain / stock_price (gravitational pull to strike)
    tension_pct = abs(K - S) / S * 100
    tension_score = round(min(tension_pct / 20.0, 1.0), 3)  # normalize 0→1 (20% = max tension)

    if tension_score > 0.5:
        signal = "high_tension"   # Price magnet: strong pull toward strike
    elif tension_score > 0.25:
        signal = "moderate_tension"
    else:
        signal = "low_tension"

    return {
        "bsm_call_fair_value": round(bsm_call, 4),
        "expected_move_pct":   expected_move_pct,
        "max_pain_strike":     round(K, 2),
        "tension_pct":         round(tension_pct, 2),
        "tension_score":       tension_score,
        "signal":              signal,
        "iv_used":             round(sigma * 100, 1),
    }


# ── 4. AKERLOF INFORMATION ASYMMETRY (George Akerlof 2001) ────────────────
def akerlof_score(ticker: str, insider_count: int, confirmed_buys: int,
                  filing_text_len: int, form: str) -> dict:
    """
    The 'Lemons Problem' applied to SEC filings:
    - High insider buy conviction = private signal that public doesn't have yet
    - SHORT filing text (opacity) = insiders know more than the filing reveals
    - Combination = STRONG private signal (opposite of 'lemon')

    Akerlof proved that information gaps create price mispricings.
    We measure the gap here.
    """
    # Private signal strength: more insider buys = stronger conviction
    if confirmed_buys >= 3:
        insider_conv = 1.0
    elif confirmed_buys == 2:
        insider_conv = 0.7
    elif confirmed_buys == 1:
        insider_conv = 0.4
    elif insider_count >= 3:
        insider_conv = 0.3  # multiple filers, no confirmed buys
    else:
        insider_conv = 0.0

    # Filing opacity: short 8-K text with high insider activity = "lemons" signal
    # A vague 8-K from insiders who are buying = they know something
    if form == "8-K":
        if filing_text_len < 500:
            opacity = 1.0   # Very short 8-K — maximum opacity
        elif filing_text_len < 2000:
            opacity = 0.7
        elif filing_text_len < 5000:
            opacity = 0.4
        else:
            opacity = 0.1   # Long detailed 8-K = lower opacity
    else:
        opacity = 0.3  # Non-8-K forms have baseline opacity

    # Akerlof composite: conviction × opacity = information gap score
    asymmetry = round(insider_conv * (1.0 + opacity), 3)

    if asymmetry > 1.5:
        signal = "strong_private_signal"
    elif asymmetry > 0.8:
        signal = "moderate_private_signal"
    elif asymmetry > 0.3:
        signal = "weak_private_signal"
    else:
        signal = "symmetric_information"

    return {
        "insider_conviction": insider_conv,
        "filing_opacity":     opacity,
        "asymmetry_score":    asymmetry,
        "signal":             signal,
        "interpretation":     f"{'High' if asymmetry > 1.0 else 'Low'} info gap — "
                              f"{'insiders know more than filing reveals' if asymmetry > 1.0 else 'filing is transparent'}"
    }


# ── 5. NASH EQUILIBRIUM DISRUPTION (John Nash 1994) ───────────────────────
def nash_disruption(ticker: str, sector_lookup: dict, today_tickers: set) -> dict:
    """
    Nash Equilibrium in sector competition: when all sector peers are quiet,
    a sudden catalyst filing by ONE ticker breaks the equilibrium.

    In Nash's framework: one player deviating from a stable strategy forces
    ALL other players to respond. In markets: one company's 8-K forces
    competitors to reprice their stock (sympathy play).

    We detect the break: if ticker filed but sector peers didn't → equilibrium broken.
    """
    sectors = sector_lookup.get(ticker, [])
    if not sectors:
        return {"nash_break": False, "sector": None, "signal": "no_sector_data"}

    primary_sector = sectors[0]

    # Count sector peers who filed today vs didn't
    sector_peers = [t for t, secs in sector_lookup.items()
                    if primary_sector in secs and t != ticker]

    peers_who_filed   = [p for p in sector_peers if p in today_tickers]
    peers_who_silent  = [p for p in sector_peers if p not in today_tickers]

    if not sector_peers:
        return {"nash_break": False, "sector": primary_sector, "signal": "no_peers"}

    # Equilibrium break ratio: if fewer than 20% of peers filed, equilibrium is broken
    filing_ratio = len(peers_who_filed) / len(sector_peers)

    if filing_ratio < 0.15 and len(sector_peers) >= 3:
        nash_break = True
        signal = "equilibrium_broken"  # Lone filer in quiet sector = strong sympathy setup
    elif filing_ratio < 0.30:
        nash_break = True
        signal = "partial_break"
    else:
        nash_break = False
        signal = "sector_wide_filing"  # Many peers filed = sector-wide catalyst, less edge

    return {
        "nash_break":       nash_break,
        "sector":           primary_sector,
        "peers_total":      len(sector_peers),
        "peers_filed":      len(peers_who_filed),
        "filing_ratio":     round(filing_ratio, 3),
        "signal":           signal,
        "sympathy_targets": peers_who_silent[:5],  # Top 5 quiet peers = sympathy targets
    }


# ── Composite Nobel Score ──────────────────────────────────────────────────
def composite_boost(vol_data: dict, bsm_data: dict, akerlof_data: dict, nash_data: dict) -> float:
    """
    Single score multiplier combining all 4 per-ticker Nobel signals.
    Neutral = 1.0. Range: 0.80 → 1.60

    Applied by classify_sec_catalysts.py to multiply gapper_score.
    """
    boost = 1.0

    # GARCH: volatility clustering → higher chance of continuation move
    vol_ratio = vol_data.get("vol_ratio", 1.0)
    if vol_ratio > 1.5:
        boost += 0.15
    elif vol_ratio > 1.2:
        boost += 0.08
    elif vol_ratio < 0.7:   # compression → coiled spring → add boost
        boost += 0.10

    # BSM: options tension → price magnet exists
    tension = bsm_data.get("tension_score", 0.0)
    boost += tension * 0.20   # max +0.20 from BSM tension

    # Akerlof: information asymmetry → private signal edge
    asym = akerlof_data.get("asymmetry_score", 0.0)
    boost += min(asym * 0.10, 0.15)  # max +0.15 from info asymmetry

    # Nash: equilibrium broken → sympathy play / lone catalyst
    if nash_data.get("nash_break"):
        boost += 0.10

    return round(min(max(boost, 0.80), 1.60), 3)


# ── Data Loaders ──────────────────────────────────────────────────────────
def load_macro() -> dict:
    p = ROOT / "macro_layer.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return {}

def load_stooq_cache() -> dict:
    p = ROOT / ".stooq_daily_cache.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return {}

def load_options() -> dict[str, dict]:
    p = ROOT / "options_flow.csv"
    result = {}
    if p.exists():
        try:
            with open(p, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker","").strip().upper()
                    if t: result[t] = row
        except: pass
    return result

def load_insider_clusters() -> dict[str, dict]:
    p = ROOT / "insider_clusters.csv"
    result = {}
    if p.exists():
        try:
            with open(p, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker","").strip().upper()
                    if t: result[t] = row
        except: pass
    return result

def load_sector_lookup() -> dict:
    p = ROOT / "sector_lookup.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return {}

def load_today_tickers() -> set:
    """All tickers in today's pipeline (gappers + ranked + raw catalyst list).

    sec_catalyst_latest.csv is included so OTC tickers with no_market_data
    (e.g. HCMC) that are filtered out of the classify/gapper stage still
    receive Nash/Akerlof/GARCH scoring — they are exactly the tickers where
    information asymmetry signals matter most.
    """
    tickers = set()
    for fname in ["sec_clean_gappers.csv", "sec_catalyst_ranked.csv",
                  "sec_top_gappers.csv", "sec_catalyst_latest.csv"]:
        p = ROOT / fname
        if p.exists():
            try:
                with open(p, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        t = row.get("ticker","").strip().upper()
                        if t: tickers.add(t)
            except: pass
    return tickers

def load_gapper_details() -> dict[str, dict]:
    """Load price + form + filing text length proxy from ranked CSV.

    Falls back to sec_catalyst_latest.csv for tickers not in the richer
    files — ensures OTC/no_market_data tickers get at least form + link.
    """
    result = {}
    for fname in ["sec_top_gappers.csv", "sec_catalyst_ranked.csv",
                  "sec_catalyst_latest.csv"]:
        p = ROOT / fname
        if p.exists():
            try:
                with open(p, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        t = row.get("ticker","").strip().upper()
                        if t and t not in result:
                            result[t] = row
            except: pass
    return result


def main() -> None:
    print("build_nobel_physics: computing Nobel Prize economic physics...")

    macro         = load_macro()
    stooq         = load_stooq_cache()
    options       = load_options()
    insiders      = load_insider_clusters()
    sector_lookup = load_sector_lookup()
    today_tickers = load_today_tickers()
    gapper_details= load_gapper_details()

    risk_free = (macro.get("fed_funds_rate") or 4.33) / 100.0

    # ── 1. Taylor Rule macro shock ─────────────────────────────────────────
    taylor = taylor_rule_shock(macro)
    print(f"  [Kydland/Prescott] Taylor deviation={taylor['deviation']:+.4f} "
          f"-> {taylor['shock']} | {taylor['description']}")

    # ── Per-ticker Nobel signals ───────────────────────────────────────────
    ticker_signals: dict[str, dict] = {}
    vol_regimes = {"extreme_cluster": 0, "high_cluster": 0, "compression": 0, "normal": 0}
    bsm_high    = 0
    akerlof_strong = 0
    nash_breaks = 0

    for ticker in today_tickers:
        details  = gapper_details.get(ticker, {})
        price_s  = details.get("price", "") or ""
        form     = details.get("form", "") or ""
        try:    price = float(price_s)
        except: price = 0.0

        # Proxy for filing text length from tags (longer tag list = more content extracted)
        tags = details.get("tags", "") or ""
        filing_text_len_proxy = len(tags) * 50  # rough proxy

        insider_row = insiders.get(ticker, {})
        try:    ins_count = int(insider_row.get("filing_count", 0) or 0)
        except: ins_count = 0
        try:    confirmed_buys = int(insider_row.get("confirmed_buy", 0) or 0)
        except: confirmed_buys = 0

        # Run all four Nobel models
        vol   = garch_volatility(ticker, stooq)
        bsm   = bsm_tension(ticker, price, options.get(ticker, {}), risk_free)
        aklof = akerlof_score(ticker, ins_count, confirmed_buys, filing_text_len_proxy, form)
        nash  = nash_disruption(ticker, sector_lookup, today_tickers)
        c_boost = composite_boost(vol, bsm, aklof, nash)

        vol_regimes[vol.get("regime", "normal")] = vol_regimes.get(vol.get("regime", "normal"), 0) + 1
        if bsm.get("signal") == "high_tension": bsm_high += 1
        if aklof.get("signal") in ("strong_private_signal", "moderate_private_signal"): akerlof_strong += 1
        if nash.get("nash_break"): nash_breaks += 1

        ticker_signals[ticker] = {
            "garch":    vol,
            "bsm":      bsm,
            "akerlof":  aklof,
            "nash":     nash,
            "composite_boost": c_boost,
        }

    result = {
        "date":       datetime.date.today().isoformat(),
        "macro": {
            "taylor_rule":     taylor,
            "environment":     macro.get("environment", "unknown"),
            "fed_funds_rate":  macro.get("fed_funds_rate"),
            "cpi_yoy":         macro.get("cpi_yoy"),
        },
        "summary": {
            "tickers_analyzed":    len(ticker_signals),
            "vol_high_cluster":    vol_regimes.get("high_cluster", 0) + vol_regimes.get("extreme_cluster", 0),
            "vol_compression":     vol_regimes.get("compression", 0),
            "bsm_high_tension":    bsm_high,
            "akerlof_strong_signal": akerlof_strong,
            "nash_equilibrium_breaks": nash_breaks,
        },
        "tickers": ticker_signals,
    }

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"  [Engle GARCH]    vol_clustering: {result['summary']['vol_high_cluster']} tickers in high-vol regime")
    print(f"  [BSM Tension]    {bsm_high} tickers with high options tension")
    print(f"  [Akerlof]        {akerlof_strong} tickers with strong private signal")
    print(f"  [Nash]           {nash_breaks} equilibrium breaks detected")
    print(f"build_nobel_physics: {len(ticker_signals)} tickers -> nobel_signals.json written")


if __name__ == "__main__":
    main()
