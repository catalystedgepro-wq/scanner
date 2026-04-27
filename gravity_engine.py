#!/usr/bin/env python3
"""gravity_engine.py — Compute the static Gravity score for each ticker node.

Formula (from Cerebro Architecture Directive):
    G = (0.40 × log10(MarketCap) / 13.0) + (0.60 × Σ ETF_weights)
    Normalized to 1–100 scale.

Logarithmic normalization prevents trillion-dollar nodes (NVDA) from visually
dominating the HUD. log10($10T) = 13, so the denominator anchors the scale.

Institutional weight (0.60) reflects passive capital flow — the "cables" that
physically tether a ticker to index funds. This matters more than raw size.

Pure stdlib — no numpy/pandas required.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).parent


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """Linear interpolation — equivalent to np.interp for single scalar."""
    if x1 == x0:
        return y0
    t = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
    return y0 + t * (y1 - y0)


class GravityEngine:
    """
    Calculates the Ticker's Gravity Score (Node Size in the Cerebro HUD).

    Parameters
    ----------
    mc_weight : float
        Weight for log-scaled Market Cap (default 0.40 — "The Mass")
    inst_weight : float
        Weight for Institutional ETF anchor (default 0.60 — "The Pull")
    max_log_cap : float
        log10 of the maximum plausible market cap ($10T = 13.0)
    """

    def __init__(self, mc_weight: float = 0.40, inst_weight: float = 0.60,
                 max_log_cap: float = 13.0):
        self.w_mc   = mc_weight
        self.w_inst = inst_weight
        self.max_log_cap = max_log_cap

    def calculate_gravity(self, mkt_cap_usd: float,
                          etf_weights_sum: float = 0.0) -> float:
        """
        Parameters
        ----------
        mkt_cap_usd : float
            Market cap in USD (e.g. 3.0e12 for NVDA, 1e7 for HCMC).
        etf_weights_sum : float
            Sum of percentage weights across major ETFs (e.g. 0.25 = 25%).
            Use 0.0 if unknown — gravity will be driven by market cap alone.

        Returns
        -------
        float  Gravity score in [1, 100].
        """
        if mkt_cap_usd <= 0:
            return 1.0

        # 1. Logarithmic scaling of market cap (prevents trillion-dollar
        #    dominance: NVDA at $3T → log10(3e12)≈12.5 → 12.5/13 ≈ 0.96)
        mass_score = math.log10(mkt_cap_usd) / self.max_log_cap
        mass_score = max(0.0, min(1.0, mass_score))

        # 2. Institutional anchor — direct ETF weighting, clamped 0–1
        pull_score = max(0.0, min(1.0, etf_weights_sum))

        # 3. Weighted combination
        raw = (self.w_mc * mass_score) + (self.w_inst * pull_score)

        # 4. Normalize to 1–100 (raw spans ~0 → 0.6 for most real tickers)
        return round(_lerp(raw, 0.0, 0.6, 1.0, 100.0), 2)

    # ── Convenience tier classifier ───────────────────────────────────────────
    @staticmethod
    def market_cap_tier(mkt_cap_usd: float) -> str:
        """Classify ticker into size tier for HUD rendering."""
        if   mkt_cap_usd >= 200e9:  return "mega"
        elif mkt_cap_usd >= 10e9:   return "large"
        elif mkt_cap_usd >= 2e9:    return "mid"
        elif mkt_cap_usd >= 300e6:  return "small"
        elif mkt_cap_usd >= 50e6:   return "micro"
        else:                       return "nano"


# ── Batch utility ─────────────────────────────────────────────────────────────
def compute_gravity_batch(entity_master: dict,
                          engine: GravityEngine | None = None) -> dict:
    """
    Compute or refresh gravity scores for all tickers in entity_master.

    Reads 'mkt_cap_usd' and 'etf_weights_sum' from each entity record.
    Updates the record in-place and returns the updated master dict.
    """
    if engine is None:
        engine = GravityEngine()

    updated = 0
    for ticker, rec in entity_master.items():
        cap = rec.get("mkt_cap_usd") or 0
        # F-7 fix: ETFs get zero etf_weights_sum to prevent self-referential gravity.
        # Ben-David et al. (2018, JF): ETFs are not investable catalysts.
        is_etf = bool(rec.get("etf"))
        etf = 0.0 if is_etf else (rec.get("etf_weights_sum") or 0.0)
        if cap > 0:
            rec["gravity"] = engine.calculate_gravity(cap, etf)
            rec["mkt_cap_tier"] = GravityEngine.market_cap_tier(cap)
            updated += 1
        else:
            rec.setdefault("gravity", None)
            rec.setdefault("mkt_cap_tier", "unknown")

    return entity_master


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = GravityEngine()

    # Calibration check (matches Gemini reference values)
    tests = [
        ("NVDA",  3.0e12, 0.20, "Dominant Planet"),
        ("AAPL",  3.5e12, 0.25, "Dominant Planet"),
        ("BLK",   120e9,  0.08, "Large Planet"),
        ("SPY",   500e9,  0.40, "Index Anchor"),
        ("HCMC",  1e7,    0.00, "Rogue Node"),
        ("AEON",  5e6,    0.00, "Dust Particle"),
    ]
    print("Gravity Calibration:")
    for name, cap, etf, label in tests:
        g = engine.calculate_gravity(cap, etf)
        tier = GravityEngine.market_cap_tier(cap)
        print(f"  {name:6s} cap=${cap:.0e}  etf={etf:.0%}  G={g:6.2f}  [{tier}] {label}")

    # Batch update entity_master if it exists
    em_path = ROOT / "entity_master.json"
    if em_path.exists():
        em = json.loads(em_path.read_text())
        em = compute_gravity_batch(em, engine)
        em_path.write_text(json.dumps(em, indent=2))
        scored = sum(1 for r in em.values() if r.get("gravity") is not None)
        print(f"\ngravity_engine: {scored}/{len(em)} entities scored → entity_master.json")
