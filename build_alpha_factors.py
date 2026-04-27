#!/usr/bin/env python3
"""build_alpha_factors.py — Compute per-ticker alpha factors from price/volume data.

New alpha factors from Feynman math audit:
  A-2:  Volatility Ratio (vol expansion/compression regime detection)
        Bollerslev et al. (2018, JFE): vol clustering is the most robust stylized fact.
  A-3:  Abnormal Volume Z-Score
        Campbell, Grossman & Wang (1993, JFE): abnormal volume predicts short-term moves.
  A-12: Amihud Illiquidity Ratio
        Amihud (2002, JFM): illiquidity is a priced risk factor.

Inputs:  Yahoo Finance v8 chart API (60d daily OHLCV, no auth required)
Outputs: alpha_factors.csv — keyed by ticker, consumed by classify_sec_catalysts.py
         and build_convergence_score.py for scoring bonuses/penalties.

Pure stdlib — no numpy/pandas required.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
OUTPUT_CSV = ROOT / "alpha_factors.csv"
CACHE_PATH = ROOT / ".alpha_factors_cache.json"

YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range=60d&interval=1d"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
CACHE_TTL = 6 * 3600  # 6 hours


def _fetch_chart(symbol: str) -> dict[str, Any]:
    """Fetch 60d daily OHLCV from Yahoo Finance chart API."""
    url = YAHOO_CHART_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
        if enc == "gzip":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    results = data.get("chart", {}).get("result") or []
    if not results:
        return {}
    r = results[0]
    quotes = (r.get("indicators", {}).get("quote") or [{}])[0]
    closes = [float(c) for c in (quotes.get("close") or []) if c is not None]
    volumes = [float(v) for v in (quotes.get("volume") or []) if v is not None]
    highs = [float(h) for h in (quotes.get("high") or []) if h is not None]
    lows = [float(l) for l in (quotes.get("low") or []) if l is not None]
    return {"closes": closes, "volumes": volumes, "highs": highs, "lows": lows}


# ── A-2: Volatility Ratio ────────────────────────────────────────────────────
def volatility_ratio(closes: list[float], short: int = 5, long: int = 20) -> float:
    """Short-term vol / long-term vol. >2.0 = expansion, <0.5 = compression.
    Bollerslev et al. (2018, JFE): vol clustering is the most robust stylized fact."""
    if len(closes) < long + 1:
        return 1.0
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    if len(returns) < long:
        return 1.0
    short_rets = returns[-short:]
    long_rets = returns[-long:]
    try:
        short_vol = statistics.stdev(short_rets)
        long_vol = statistics.stdev(long_rets)
    except statistics.StatisticsError:
        return 1.0
    if long_vol <= 0:
        return 1.0
    return round(short_vol / long_vol, 4)


# ── A-3: Abnormal Volume Z-Score ─────────────────────────────────────────────
def volume_zscore(volumes: list[float], window: int = 20) -> float:
    """Z_vol = (V_today - V_bar_20) / sigma_V_20.
    Campbell, Grossman & Wang (1993, JFE): abnormal volume predicts moves."""
    if len(volumes) < window + 1:
        return 0.0
    recent = volumes[-window - 1:-1]  # 20-day window excluding today
    today = volumes[-1]
    try:
        mean_v = statistics.fmean(recent)
        std_v = statistics.stdev(recent)
    except (statistics.StatisticsError, ZeroDivisionError):
        return 0.0
    if std_v <= 0:
        return 0.0
    return round((today - mean_v) / std_v, 4)


# ── A-12: Amihud Illiquidity Ratio ───────────────────────────────────────────
def amihud_illiquidity(closes: list[float], volumes: list[float],
                       window: int = 20) -> float:
    """ILLIQ = mean(|r_d| / DollarVolume_d) over window days.
    Amihud (2002, JFM): illiquidity is a priced risk factor."""
    n = min(len(closes) - 1, len(volumes) - 1, window)
    if n < 5:
        return 0.0
    ratios: list[float] = []
    for i in range(-n, 0):
        c_prev = closes[i - 1]
        c_curr = closes[i]
        vol = volumes[i]
        if c_prev <= 0 or vol <= 0:
            continue
        ret = abs(c_curr / c_prev - 1)
        dollar_vol = c_curr * vol
        if dollar_vol > 0:
            ratios.append(ret / dollar_vol)
    if not ratios:
        return 0.0
    # Scale up by 1e9 to make readable (Amihud is typically very small)
    return round(statistics.fmean(ratios) * 1e9, 4)


# ── Scoring helpers ──────────────────────────────────────────────────────────
def vol_ratio_gapper_bonus(vr: float) -> int:
    """A-2: +5 gapper pts when vol expanding (regime transition)."""
    if vr >= 2.5: return 5
    if vr >= 2.0: return 3
    return 0


def vol_ratio_squeeze_bonus(vr: float) -> int:
    """A-2: +5 squeeze pts when vol compressing (coiling)."""
    if vr <= 0.3: return 5
    if vr <= 0.5: return 3
    return 0


def volume_z_gapper_bonus(z: float) -> int:
    """A-3: High abnormal volume → stronger gapper signal."""
    if z >= 4.0: return 8
    if z >= 3.0: return 6
    if z >= 2.0: return 4
    if z >= 1.5: return 2
    return 0


def amihud_penalty(illiq: float) -> int:
    """A-12: Illiquid stocks are harder to exit → penalty."""
    if illiq >= 100: return -5   # extremely illiquid micro/nano
    if illiq >= 50:  return -3
    if illiq >= 20:  return -2
    return 0


# ── Cache ────────────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    print("build_alpha_factors: computing A-2/A-3/A-12 for active tickers...")

    # Collect tickers from combined_priority and sec_catalyst_latest
    tickers: set[str] = set()
    for fname in ("combined_priority.csv", "sec_catalyst_latest.csv",
                   "squeeze_candidates.csv"):
        path = ROOT / fname
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("ticker") or "").strip().upper()
                if t:
                    tickers.add(t)

    print(f"  {len(tickers)} unique tickers to score")
    cache = _load_cache()
    now = int(time.time())
    results: list[dict[str, Any]] = []
    fetched = 0

    for ticker in sorted(tickers):
        entry = cache.get(ticker, {})
        if entry and now - int(entry.get("ts", 0)) <= CACHE_TTL:
            chart = entry.get("chart", {})
        else:
            chart = _fetch_chart(ticker)
            cache[ticker] = {"ts": now, "chart": chart}
            fetched += 1
            if fetched % 50 == 0:
                print(f"    fetched {fetched} charts...")
                time.sleep(0.5)

        closes = chart.get("closes", [])
        volumes = chart.get("volumes", [])

        vr = volatility_ratio(closes)
        vz = volume_zscore(volumes)
        illiq = amihud_illiquidity(closes, volumes)

        results.append({
            "ticker": ticker,
            "vol_ratio": vr,
            "vol_ratio_regime": (
                "EXPANDING" if vr >= 2.0 else
                "COMPRESSING" if vr <= 0.5 else
                "NORMAL"
            ),
            "vol_z_score": vz,
            "amihud_illiq": illiq,
            "gapper_vol_bonus": vol_ratio_gapper_bonus(vr),
            "gapper_volz_bonus": volume_z_gapper_bonus(vz),
            "squeeze_vol_bonus": vol_ratio_squeeze_bonus(vr),
            "illiq_penalty": amihud_penalty(illiq),
        })

    _save_cache(cache)

    fieldnames = [
        "ticker", "vol_ratio", "vol_ratio_regime", "vol_z_score",
        "amihud_illiq", "gapper_vol_bonus", "gapper_volz_bonus",
        "squeeze_vol_bonus", "illiq_penalty",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    expanding = sum(1 for r in results if r["vol_ratio_regime"] == "EXPANDING")
    compressing = sum(1 for r in results if r["vol_ratio_regime"] == "COMPRESSING")
    high_vol = sum(1 for r in results if r["vol_z_score"] >= 2.0)
    illiq_count = sum(1 for r in results if r["illiq_penalty"] < 0)

    print(f"\n  Wrote {len(results)} rows to {OUTPUT_CSV.name}")
    print(f"  A-2 Vol regime: {expanding} expanding, {compressing} compressing")
    print(f"  A-3 Abnormal volume (Z>=2): {high_vol} tickers")
    print(f"  A-12 Illiquidity penalty: {illiq_count} tickers")
    print(f"  Charts fetched: {fetched} (rest from cache)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
