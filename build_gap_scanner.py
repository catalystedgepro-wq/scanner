#!/usr/bin/env python3
"""build_gap_scanner.py — Penny gap-up + accumulation scanner.

Ports both ThinkorSwim scanners to Python:
  1. Gap-Up Scanner     — detects significant overnight + intraday gaps
  2. Accumulation Scanner — volume surge confirms institutional accumulation

Filters: price $0.50–$10, gap ≥1%, gap > 1.5×ATR, volume > 50K,
         ATR > 1% of price. Ranks by composite gap+accumulation score.

Scans the SEC filer universe (sec_catalyst_tickers.txt).

Outputs:
  gap_scanner.csv       — all qualifying tickers
  gap_scanner_top.csv   — top 10 for newsletter
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent

# ── Load tuned config (falls back to ThinkorSwim defaults) ───────────────
def _load_config() -> dict:
    cfg_path = ROOT / "gap_scanner_config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

_cfg = _load_config()

GAP_THRESHOLD     = _cfg.get("gap_threshold_pct", 1.0) / 100   # convert % → ratio
MIN_VOLUME        = int(_cfg.get("min_volume", 50_000))
ATR_LENGTH        = 14
ATR_MULTIPLIER    = 1.5
VOLATILITY_FILTER = 1.0

# ── Penny stock price range ───────────────────────────────────────────────
MIN_PRICE = float(_cfg.get("min_price", 0.50))
MAX_PRICE = float(_cfg.get("max_price", 10.00))

# ── Paths ─────────────────────────────────────────────────────────────────
QUOTE_CACHE        = ROOT / ".gap_scanner_cache.json"
LIVE_PRICE_CACHE   = ROOT / ".gap_scanner_live_cache.json"
CACHE_TTL_SEC      = 4 * 3600
LIVE_CACHE_TTL_SEC = 5 * 60   # refresh live prices every 5 minutes
PENNY_UNIVERSE = ROOT / "penny_universe.txt"      # broad universe (preferred)
TICKER_FILE    = ROOT / "sec_catalyst_tickers.txt" # fallback: SEC filers only
OUT_CSV        = ROOT / "gap_scanner.csv"
OUT_TOP_CSV    = ROOT / "gap_scanner_top.csv"

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1d&range=60d"
)
YAHOO_LIVE_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1m&range=1d&includePrePost=true"
)


# ── Cache helpers ─────────────────────────────────────────────────────────

def load_cache() -> dict:
    if not QUOTE_CACHE.exists():
        return {}
    try:
        return json.loads(QUOTE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    QUOTE_CACHE.write_text(json.dumps(cache), encoding="utf-8")


def load_live_cache() -> dict:
    if not LIVE_PRICE_CACHE.exists():
        return {}
    try:
        return json.loads(LIVE_PRICE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_live_cache(cache: dict) -> None:
    LIVE_PRICE_CACHE.write_text(json.dumps(cache), encoding="utf-8")


def fetch_live_price(symbol: str) -> float | None:
    """Fetch current price including premarket/afterhours from Yahoo Finance 1m chart."""
    url = YAHOO_LIVE_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0].get("close", [])
        # Walk back from the end to find the last non-None close
        for v in reversed(closes):
            if v is not None:
                return float(v)
    except Exception:
        pass
    return None


def get_live_price(symbol: str, cache: dict) -> float | None:
    now_ts = int(dt.datetime.now().timestamp())
    entry = cache.get(symbol.upper())
    if entry and now_ts - int(entry.get("ts", 0)) <= LIVE_CACHE_TTL_SEC:
        return entry.get("price")
    price = fetch_live_price(symbol)
    cache[symbol.upper()] = {"ts": now_ts, "price": price}
    return price


# ── Yahoo Finance fetch ───────────────────────────────────────────────────

def fetch_daily(symbol: str) -> list[dict]:
    url = YAHOO_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        q = result["indicators"]["quote"][0]
        rows: list[dict] = []
        for i, ts in enumerate(timestamps):
            try:
                d  = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
                o  = q["open"][i]
                h  = q["high"][i]
                l  = q["low"][i]
                c  = q["close"][i]
                v  = q["volume"][i] or 0
                if None in (o, h, l, c):
                    continue
                rows.append({
                    "date":   d.isoformat(),
                    "open":   float(o),
                    "high":   float(h),
                    "low":    float(l),
                    "close":  float(c),
                    "volume": float(v),
                })
            except (TypeError, IndexError):
                continue
        return rows
    except Exception:
        return []


def get_series(symbol: str, cache: dict) -> list[dict]:
    now_ts = int(dt.datetime.now().timestamp())
    entry  = cache.get(symbol.upper())
    if entry and now_ts - int(entry.get("ts", 0)) <= CACHE_TTL_SEC:
        return entry.get("rows", [])
    rows = fetch_daily(symbol)
    cache[symbol.upper()] = {"ts": now_ts, "rows": rows}
    return rows


# ── ATR calculation (SMA of True Range — matches ThinkorSwim default) ─────

def calc_atr_series(rows: list[dict]) -> list[float | None]:
    trs: list[float] = []
    for i, r in enumerate(rows):
        if i == 0:
            trs.append(r["high"] - r["low"])
        else:
            pc = rows[i - 1]["close"]
            trs.append(max(
                r["high"] - r["low"],
                abs(r["high"] - pc),
                abs(r["low"]  - pc),
            ))
    atrs: list[float | None] = []
    for i in range(len(trs)):
        if i < ATR_LENGTH - 1:
            atrs.append(None)
        else:
            atrs.append(statistics.fmean(trs[i - ATR_LENGTH + 1 : i + 1]))
    return atrs


# ── Core scanner logic ────────────────────────────────────────────────────

def analyze(symbol: str, rows: list[dict]) -> dict | None:
    """Apply gap-up + accumulation logic. Returns scored dict or None."""
    if len(rows) < ATR_LENGTH + 2:
        return None

    today = rows[-1]
    prev  = rows[-2]

    # Price filter
    price = today["close"]
    if not (MIN_PRICE <= price <= MAX_PRICE):
        return None

    # Volume filter
    if today["volume"] < MIN_VOLUME:
        return None

    # ATR
    atr = calc_atr_series(rows)[-1]
    if not atr or atr <= 0:
        return None

    # Volatility condition: ATR > 1% of close
    if atr <= price * (VOLATILITY_FILTER / 100):
        return None

    # ── Gap calculation ───────────────────────────────────────────────────
    # Overnight gap: today open vs yesterday close  (core signal)
    overnight_gap   = today["open"] - prev["close"]
    overnight_pct   = overnight_gap / prev["close"] if prev["close"] > 0 else 0

    # Intraday extension from open (sessionHigh logic in TOS)
    intraday_ext    = today["high"] - today["open"]
    intraday_pct    = intraday_ext / today["open"] if today["open"] > 0 else 0

    # Effective gap: whichever is larger
    effective_gap_pct  = max(overnight_pct, intraday_pct)
    effective_gap_size = max(overnight_gap, intraday_ext)

    if effective_gap_pct < GAP_THRESHOLD:
        return None

    # Significant gap: must exceed ATR × multiplier
    if effective_gap_size <= atr * ATR_MULTIPLIER:
        return None

    # ── Accumulation score (Scanner 2 layer) ─────────────────────────────
    # Volume ratio vs 20-day avg — high ratio = institutional accumulation
    recent_vols = [r["volume"] for r in rows[-21:-1] if r["volume"] > 0]
    avg_vol     = statistics.fmean(recent_vols) if recent_vols else 1
    vol_ratio   = today["volume"] / avg_vol

    # Volume trend: is volume building over last 3 days? (accumulation pattern)
    vol_3d = [r["volume"] for r in rows[-4:-1]]
    vol_building = all(vol_3d[i] <= vol_3d[i + 1] for i in range(len(vol_3d) - 1))

    # Consecutive up-closes (momentum confirmation)
    consec_up = 0
    for r in reversed(rows[-5:]):
        if r["close"] >= r["open"]:
            consec_up += 1
        else:
            break

    # Gap-to-ATR ratio (explosiveness)
    gap_atr_ratio = effective_gap_size / atr

    # ── Composite score (0–100) ───────────────────────────────────────────
    score = min(100, round(
        (effective_gap_pct * 100 * 2.5)        # gap % magnitude
        + (gap_atr_ratio   * 8)                # ATR significance
        + (min(vol_ratio, 6) * 6)              # accumulation (capped at 6×)
        + (consec_up * 4)                      # momentum streak
        + (5 if vol_building else 0)           # volume build pattern
    ))

    # Accumulation label
    if vol_ratio >= 5:
        accum_label = "HEAVY"
    elif vol_ratio >= 2:
        accum_label = "ELEVATED"
    elif vol_ratio >= 1.2:
        accum_label = "MODERATE"
    else:
        accum_label = "NORMAL"

    return {
        "ticker":          symbol.upper(),
        "price":           round(price, 2),
        "prev_close":      round(prev["close"], 2),
        "overnight_gap_pct":  round(overnight_pct * 100, 2),
        "intraday_ext_pct":   round(intraday_pct * 100, 2),
        "effective_gap_pct":  round(effective_gap_pct * 100, 2),
        "atr":             round(atr, 4),
        "gap_atr_ratio":   round(gap_atr_ratio, 2),
        "volume":          int(today["volume"]),
        "avg_volume":      int(avg_vol),
        "vol_ratio":       round(vol_ratio, 2),
        "vol_building":    "1" if vol_building else "0",
        "accum_label":     accum_label,
        "consec_up_days":  consec_up,
        "gap_score":       score,
        "date":            today["date"],
    }


# ── Ticker loader ─────────────────────────────────────────────────────────

def load_tickers() -> list[str]:
    # Use broad penny universe if available, fall back to SEC filers only
    source = PENNY_UNIVERSE if PENNY_UNIVERSE.exists() else TICKER_FILE
    if not source.exists():
        print(f"gap_scanner: no ticker file found — skipping")
        return []
    seen: set[str] = set()
    out:  list[str] = []
    with source.open(encoding="utf-8") as f:
        for line in f:
            t = line.strip().upper()
            if t and t not in seen:
                out.append(t)
                seen.add(t)
    label = "broad penny universe" if source == PENNY_UNIVERSE else "SEC filers only"
    print(f"gap_scanner: loaded {len(out)} tickers from {label}")
    return out


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    tickers = load_tickers()
    if not tickers:
        return 0

    print(f"gap_scanner: scanning {len(tickers)} SEC filers for penny gaps...")
    cache      = load_cache()
    live_cache = load_live_cache()
    results: list[dict] = []
    skipped = 0

    for ticker in tickers:
        rows = get_series(ticker, cache)
        if not rows:
            skipped += 1
            continue
        r = analyze(ticker, rows)
        if r:
            results.append(r)

    save_cache(cache)
    results.sort(key=lambda x: -x["gap_score"])

    # Override price with live/premarket quote — top 25 only, 60s budget
    top_for_live = results[:25]
    print(f"gap_scanner: fetching live prices for top {len(top_for_live)} candidates...")
    deadline = time.time() + 60
    for r in top_for_live:
        if time.time() > deadline:
            print("  live price budget exhausted — remaining tickers keep last-close price")
            break
        live = get_live_price(r["ticker"], live_cache)
        if live and live > 0:
            r["price"] = round(live, 2)

    save_live_cache(live_cache)

    fieldnames = [
        "ticker", "price", "prev_close",
        "overnight_gap_pct", "intraday_ext_pct", "effective_gap_pct",
        "atr", "gap_atr_ratio",
        "volume", "avg_volume", "vol_ratio",
        "vol_building", "accum_label", "consec_up_days",
        "gap_score", "date",
    ]

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)

    with OUT_TOP_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results[:10])

    top = results[0]["ticker"] if results else "none"
    print(f"  penny gap candidates: {len(results)}  |  top: {top}")
    print(f"  no-data skips: {skipped}")
    print(f"  saved → {OUT_CSV.name}, {OUT_TOP_CSV.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
