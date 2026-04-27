#!/usr/bin/env python3
"""tether_engine.py — Leader-Laggard Sympathy Tether Calculator.

Formula (Cerebro Architecture Directive):
    T = (0.70 × ρ_60d) + (0.30 × GICS_Depth)

Where:
    ρ_60d      — 60-day Pearson correlation of daily returns (data fact)
    GICS_Depth — taxonomy proximity constant (structural fact):
        Same Sub-Industry  = 1.00
        Same Industry      = 0.75
        Same Industry Group = 0.50
        Same Sector        = 0.25
        Different Sector   = 0.00

Tether output: 0.0 (no connection) → 1.0 (perfect sympathy)
At T ≥ 0.80: "Supernova Tether" — AMD follows NVDA within 120s
At T ≥ 0.60: "Gravity Cable" — visible pulse in Cerebro HUD
At T < 0.30: "Ghost Link" — render as faint dotted line

Pure stdlib — no numpy/pandas.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).parent


# ── Pure-stdlib Pearson correlation ──────────────────────────────────────────
def pearson_corr(xs: list[float], ys: list[float]) -> float:
    """Pearson r between two aligned return series. Returns 0.0 if undefined."""
    n = len(xs)
    if n < 10:  # need minimum sample for meaningful correlation
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num   = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    var_x = sum((x - mx) ** 2 for x in xs)
    var_y = sum((y - my) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return num / math.sqrt(var_x * var_y)


# ── GICS hierarchy loader ──────────────────────────────────────────────────────
def _load_hier() -> dict:
    p = ROOT / "industry_hierarchy_lookup.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── Price history loader (from Stooq daily cache) ─────────────────────────────
def _load_returns(ticker: str, cache: dict, days: int = 60) -> list[float]:
    """Extract daily return series from .stooq_daily_cache.json for a ticker."""
    rows = cache.get(ticker.upper(), [])
    if not rows:
        return []
    # rows: [{"date": "YYYY-MM-DD", "close": float}, ...]
    prices = [r["close"] for r in sorted(rows, key=lambda r: r.get("date", ""))
              if r.get("close")]
    prices = prices[-days - 1:]  # need N+1 prices for N returns
    if len(prices) < 2:
        return []
    return [(prices[i] - prices[i-1]) / prices[i-1]
            for i in range(1, len(prices))]


class TetherEngine:
    """
    Calculates the weighted Tether Strength (0–1) between any two ticker nodes.

    Usage
    -----
    engine = TetherEngine()
    strength = engine.calculate_tether("NVDA", "AMD")
    """

    THRESHOLDS = {
        "supernova": 0.80,  # blazing cable — co-moves within seconds
        "gravity":   0.60,  # solid cable — strong sympathy
        "ghost":     0.30,  # faint dotted line — weak link
    }

    def __init__(self, corr_weight: float = 0.70, tax_weight: float = 0.30):
        self.w_corr = corr_weight
        self.w_tax  = tax_weight
        self._hier  = _load_hier()
        self._price_cache: dict = {}
        # Load Stooq daily cache
        stooq_path = ROOT / ".stooq_daily_cache.json"
        if stooq_path.exists():
            try:
                self._price_cache = json.loads(
                    stooq_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def gics_proximity(self, ticker_a: str, ticker_b: str) -> float:
        """Return GICS structural proximity score between two tickers."""
        ha = self._hier.get(ticker_a.upper(), {})
        hb = self._hier.get(ticker_b.upper(), {})
        if not ha or not hb:
            return 0.0
        if ha.get("si") and ha.get("si") == hb.get("si"):
            return 1.00  # same Sub-Industry
        if ha.get("i")  and ha.get("i")  == hb.get("i"):
            return 0.75  # same Industry
        if ha.get("ig") and ha.get("ig") == hb.get("ig"):
            return 0.50  # same Industry Group
        if ha.get("s")  and ha.get("s")  == hb.get("s"):
            return 0.25  # same Sector
        return 0.0

    def calculate_tether(self, ticker_a: str, ticker_b: str,
                         days: int = 60) -> dict:
        """
        Compute tether between two tickers.

        Returns
        -------
        dict with keys:
            strength    : float [0,1]
            correlation : float [-1,1]
            proximity   : float [0,1]
            label       : str  'supernova'|'gravity'|'ghost'|'none'
        """
        ret_a = _load_returns(ticker_a, self._price_cache, days)
        ret_b = _load_returns(ticker_b, self._price_cache, days)

        # Align lengths
        min_len = min(len(ret_a), len(ret_b))
        if min_len >= 10:
            corr = pearson_corr(ret_a[-min_len:], ret_b[-min_len:])
        else:
            corr = 0.0

        prox = self.gics_proximity(ticker_a, ticker_b)
        strength = round(
            (self.w_corr * max(0.0, corr)) + (self.w_tax * prox), 4)

        label = "none"
        for lbl, thresh in [("supernova", 0.80),
                             ("gravity",   0.60),
                             ("ghost",     0.30)]:
            if strength >= thresh:
                label = lbl
                break

        return {
            "a":           ticker_a.upper(),
            "b":           ticker_b.upper(),
            "strength":    strength,
            "correlation": round(corr, 4),
            "proximity":   prox,
            "label":       label,
        }

    def build_sector_tethers(self, sector_key: str,
                             min_strength: float = 0.30) -> list[dict]:
        """
        Build all pairwise tethers within a sector.
        Returns list of tether dicts sorted by strength descending.

        Only computes pairs within the same Industry Group to keep
        O(n²) manageable.
        """
        # Group tickers by Industry Group
        ig_groups: dict[str, list[str]] = {}
        for ticker, h in self._hier.items():
            if h.get("s") == sector_key and h.get("ig"):
                ig_groups.setdefault(h["ig"], []).append(ticker)

        results = []
        for ig, tickers in ig_groups.items():
            for i in range(len(tickers)):
                for j in range(i + 1, len(tickers)):
                    t = self.calculate_tether(tickers[i], tickers[j])
                    if t["strength"] >= min_strength:
                        results.append(t)

        results.sort(key=lambda x: -x["strength"])
        return results


# ── Nightly tether snapshot ───────────────────────────────────────────────────
def build_tether_snapshot(min_strength: float = 0.50,
                          top_per_ig: int = 20) -> dict:
    """
    Build a snapshot of all strong tethers across the universe.
    Writes to tether_snapshot.json for the HUD to consume.

    Only runs pairs within the same Industry Group (taxonomy-bounded search).
    min_strength: minimum T score to include (0.50 = gravity cables+)
    top_per_ig: cap tethers per IG to prevent JSON bloat
    """
    engine = TetherEngine()
    hier   = engine._hier

    # Group tickers by IG
    ig_groups: dict[str, list[str]] = {}
    for ticker, h in hier.items():
        if h.get("ig"):
            ig_groups.setdefault(h["ig"], []).append(ticker)

    all_tethers = []
    for ig, tickers in ig_groups.items():
        ig_tethers = []
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                t = engine.calculate_tether(tickers[i], tickers[j])
                if t["strength"] >= min_strength:
                    ig_tethers.append(t)
        ig_tethers.sort(key=lambda x: -x["strength"])
        all_tethers.extend(ig_tethers[:top_per_ig])

    out_path = ROOT / "tether_snapshot.json"
    out_path.write_text(json.dumps(all_tethers, indent=2), encoding="utf-8")
    print(f"tether_engine: {len(all_tethers)} tethers ≥ {min_strength:.2f} → tether_snapshot.json")
    return {"tethers": all_tethers}


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    engine = TetherEngine()

    # Test pairs
    pairs = [
        ("NVDA", "AMD"),
        ("NVDA", "INTC"),
        ("AAPL", "MSFT"),
        ("JPM",  "BAC"),
        ("HCMC", "NVDA"),
    ]

    print("Tether Calibration:")
    print(f"  {'Pair':15s}  {'Strength':>8s}  {'Corr':>7s}  {'Prox':>5s}  Label")
    print("  " + "-" * 55)
    for a, b in pairs:
        t = engine.calculate_tether(a, b)
        print(f"  {a+'↔'+b:15s}  {t['strength']:8.4f}  "
              f"{t['correlation']:7.4f}  {t['proximity']:5.2f}  {t['label']}")

    # Build full snapshot if --snapshot flag
    if "--snapshot" in sys.argv:
        print("\nBuilding nightly tether snapshot...")
        build_tether_snapshot(min_strength=0.50)
