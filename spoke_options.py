#!/usr/bin/env python3
"""spoke_options.py — Domain 5: Options Activity Engine (Unusual Flow Detector).

Scans option chains for institutional signals — Sweeps, Gamma Magnets, and
directional flow — then injects velocity into scoring_engine.py.

Physics:
    Sweep detected (Vol/OI > 3.0):           +15 velocity  (OPTIONS_SWEEP)
    Directional call/put flow bias (>1.5x):  +8  velocity  (BULLISH_FLOW)
                                             -8  velocity  (BEARISH_FLOW)
    All options velocity decays over 24h (short-term signal).

Detectors:
    1. The Sweep   — Vol/OI > 3.0 on any strike
    2. The Flow    — CallVolume / PutVolume sentiment ratio
    3. The Anchor  — Top strike by volume (Gamma Magnet position)

Data Sources (priority order):
    1. Yahoo Finance via yfinance — public options chain fallback
    2. Alpaca Markets REST API — free paper account, ALPACA_API_KEY in .sec_email_env
    3. Tradier sandbox — developer sandbox token

Scan Filter ("50ms Rule"):
    Only scans tickers with score > 15 in sec_catalyst_ranked.csv or
    spark_velocities["options_score"] > 0 — avoids burning time on dead tickers.

Output: spark_velocities.json["options"] per ticker (read by scoring_engine.py)
        options_activity.json — full chain snapshot for HUD

Run: python3 spoke_options.py [--limit=50] [--dry-run] [--ticker=AAPL]
Schedule: Every 15 minutes during market hours (9:30–16:00 ET, M–F)
Uses stdlib plus optional yfinance fallback when installed.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional runtime dependency
    yf = None

ROOT = Path(__file__).parent

ENTITY_MASTER    = ROOT / "entity_master.json"
SPARK_VELOCITIES = ROOT / "spark_velocities.json"
OPTIONS_ACTIVITY = ROOT / "options_activity.json"

# Physics constants
SWEEP_VELOCITY      = 15.0   # Vol/OI > 3x — institutional sweep
FLOW_BULL_VELOCITY  = 8.0    # Call/Put ratio > 1.5
FLOW_BEAR_VELOCITY  = -8.0   # Put/Call ratio > 1.5
OPTIONS_DECAY_HOURS = 24.0   # Options signals are short-term

# Detection thresholds
SWEEP_RATIO_MIN  = 3.0   # Vol/OI threshold for sweep flag
FLOW_RATIO_MIN   = 1.5   # Call/Put or Put/Call ratio for directional bias
MIN_VOLUME       = 100   # Ignore low-liquidity strikes
SCORE_THRESHOLD  = 15.0  # Only scan tickers above this gap score
MAX_ACTIVITY_AGE = timedelta(hours=36)

_YF_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Safari/537.36")
_OPTIONABLE_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


# ── Key loader ────────────────────────────────────────────────────────────────
def _load_key(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return ""


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get(url: str, headers: dict | None = None, timeout: int = 15) -> bytes | None:
    h = {"User-Agent": _YF_UA}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  WARN: {exc}")
    return None


def _likely_optionable(symbol: str) -> bool:
    ticker = str(symbol or "").strip().upper()
    return bool(_OPTIONABLE_TICKER_RE.fullmatch(ticker))


def _parse_activity_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_fresh_activity(data: dict, *, now: datetime | None = None) -> bool:
    ts = _parse_activity_ts(data.get("ts"))
    if not ts:
        return False
    reference = now or datetime.now(timezone.utc)
    return (reference - ts) <= MAX_ACTIVITY_AGE


def _prune_options_state(
    spark_velo: dict,
    activity_log: dict,
    targets: list[str],
) -> tuple[dict, dict]:
    now = datetime.now(timezone.utc)
    target_set = {t.upper() for t in targets if t}

    fresh_activity = {}
    for ticker, data in activity_log.items():
        symbol = str(ticker).upper()
        if target_set and symbol not in target_set:
            continue
        if _is_fresh_activity(data, now=now):
            fresh_activity[symbol] = data

    for ticker in list(spark_velo.keys()):
        symbol = str(ticker).upper()
        entry = spark_velo.get(ticker) or {}
        options_ts = _parse_activity_ts(entry.get("options_ts"))
        is_current_target = not target_set or symbol in target_set
        is_fresh = options_ts is not None and (now - options_ts) <= MAX_ACTIVITY_AGE
        if not is_current_target or not is_fresh:
            entry.pop("options", None)
            entry.pop("options_signals", None)
            entry.pop("gamma_magnet", None)
            entry.pop("options_ts", None)
        if not entry:
            spark_velo.pop(ticker, None)

    return spark_velo, fresh_activity


# ── Source 1: Yahoo Finance via yfinance (public fallback) ───────────────────
def fetch_chain_yfinance(ticker: str) -> dict | None:
    """
    Fetch the nearest-dated option chain from Yahoo via yfinance.
    This keeps the public scanner alive even when broker keys are absent.
    """
    if yf is None:
        return None
    if not _likely_optionable(ticker):
        return None
    try:
        quote = yf.Ticker(ticker)
        expirations = list(quote.options or [])
        if not expirations:
            return None
        chain = quote.option_chain(expirations[0])
        calls_df = getattr(chain, "calls", None)
        puts_df = getattr(chain, "puts", None)
        if calls_df is None or puts_df is None:
            return None

        def _safe_float(value: object, default: float = 0.0) -> float:
            try:
                num = float(value or 0.0)
            except Exception:
                return default
            return default if math.isnan(num) else num

        def _safe_int(value: object, default: int = 0) -> int:
            try:
                num = float(value or 0.0)
            except Exception:
                return default
            return default if math.isnan(num) else int(num)

        def _norm_rows(frame) -> list[dict]:
            rows: list[dict] = []
            for row in frame.to_dict(orient="records"):
                rows.append(
                    {
                        "contractSymbol": row.get("contractSymbol", ""),
                        "strike": _safe_float(row.get("strike", 0.0)),
                        "volume": _safe_int(row.get("volume", 0)),
                        "openInterest": _safe_int(row.get("openInterest", 0)),
                        "bid": _safe_float(row.get("bid", 0.0)),
                        "ask": _safe_float(row.get("ask", 0.0)),
                        "impliedVolatility": _safe_float(row.get("impliedVolatility", 0.0)),
                    }
                )
            return rows

        price = 0.0
        try:
            fast_info = getattr(quote, "fast_info", {}) or {}
            price = float(fast_info.get("lastPrice") or 0.0)
        except Exception:
            price = 0.0

        calls = _norm_rows(calls_df)
        puts = _norm_rows(puts_df)
        if not calls and not puts:
            return None
        return {
            "calls": calls,
            "puts": puts,
            "price": price,
            "source": "yfinance",
        }
    except Exception as exc:
        print(f"  WARN: yfinance options error for {ticker}: {exc}")
        return None


# ── Source 2: Alpaca Markets options snapshot ────────────────────────────────
# Free paper trading account: alpaca.markets → Sign Up → Paper Trading
# Gives ALPACA_API_KEY + ALPACA_SECRET_KEY. Add to .sec_email_env.
def fetch_chain_alpaca(ticker: str) -> dict | None:
    """
    Fetch option chain from Alpaca REST API (free paper trading account).
    Normalizes to {calls, puts, price, source} format.
    """
    api_key = _load_key("ALPACA_API_KEY")
    sec_key = _load_key("ALPACA_SECRET_KEY")
    if not api_key or not sec_key:
        return None

    encoded = urllib.parse.quote(ticker)
    # Get near-term snapshots with Vol+OI data
    url = (f"https://data.alpaca.markets/v1beta1/options/snapshots/{encoded}"
           f"?feed=indicative&limit=200")
    raw = _get(url, headers={
        "APCA-API-KEY-ID":     api_key,
        "APCA-API-SECRET-KEY": sec_key,
    })
    if not raw:
        return None
    try:
        d         = json.loads(raw)
        snapshots = d.get("snapshots", {})
        calls, puts = [], []
        for symbol, snap in snapshots.items():
            quote  = snap.get("latestQuote", {})
            greeks = snap.get("greeks", {})
            oi     = snap.get("openInterest", 0) or 0
            # Alpaca provides volume via dailyBar
            bar    = snap.get("dailyBar", {})
            vol    = int(bar.get("v", 0) or 0)
            # Parse strike and type from symbol (e.g. AAPL240419C00170000)
            try:
                strike = float(symbol[-8:]) / 1000.0
                cp     = symbol[-9]   # 'C' or 'P'
            except Exception:
                strike = 0.0
                cp     = "?"
            entry = {
                "contractSymbol":   symbol,
                "strike":           strike,
                "volume":           vol,
                "openInterest":     oi,
                "bid":              quote.get("bp", 0.0),
                "ask":              quote.get("ap", 0.0),
                "impliedVolatility": greeks.get("iv", 0.0),
            }
            (calls if cp == "C" else puts).append(entry)

        if calls or puts:
            return {
                "calls":  calls,
                "puts":   puts,
                "price":  0.0,
                "source": "alpaca",
            }
    except Exception as exc:
        print(f"  WARN: Alpaca options parse error for {ticker}: {exc}")
    return None


# ── Source 3: Tradier sandbox (fallback — free dev account) ──────────────────
def fetch_chain_tradier(ticker: str) -> dict | None:
    """
    Fetch option chain from Tradier sandbox (free developer account).
    Sandbox token from: developer.tradier.com → Register → Sandbox token
    Add TRADIER_TOKEN to .sec_email_env.
    """
    token = _load_key("TRADIER_TOKEN")
    if not token:
        return None

    encoded = urllib.parse.quote(ticker)
    # Get nearest expiration
    exp_url = (f"https://sandbox.tradier.com/v1/markets/options/expirations"
               f"?symbol={encoded}")
    raw = _get(exp_url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    if not raw:
        return None
    try:
        exps = json.loads(raw).get("expirations", {}).get("date") or []
        if not exps:
            return None
        nearest = exps[0] if isinstance(exps, list) else exps

        chain_url = (f"https://sandbox.tradier.com/v1/markets/options/chains"
                     f"?symbol={encoded}&expiration={nearest}&greeks=false")
        raw2 = _get(chain_url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        if not raw2:
            return None
        opts   = json.loads(raw2).get("options", {}).get("option") or []
        calls  = [o for o in opts if o.get("option_type") == "call"]
        puts   = [o for o in opts if o.get("option_type") == "put"]
        # Normalize to standard format
        def _norm(o: dict) -> dict:
            return {
                "contractSymbol": o.get("symbol", ""),
                "strike":         o.get("strike", 0.0),
                "volume":         o.get("volume", 0) or 0,
                "openInterest":   o.get("open_interest", 0) or 0,
                "bid":            o.get("bid", 0.0),
                "ask":            o.get("ask", 0.0),
                "impliedVolatility": o.get("greeks", {}).get("smv_vol", 0.0) if isinstance(o.get("greeks"), dict) else 0.0,
            }
        return {
            "calls":  [_norm(c) for c in calls],
            "puts":   [_norm(p) for p in puts],
            "price":  0.0,
            "source": "tradier_sandbox",
        }
    except Exception as exc:
        print(f"  WARN: Tradier options parse error for {ticker}: {exc}")
    return None


# ── Detectors ─────────────────────────────────────────────────────────────────
def detect_sweeps(contracts: list[dict]) -> list[dict]:
    """Return contracts where Vol/OI > SWEEP_RATIO_MIN and volume > MIN_VOLUME."""
    sweeps = []
    for c in contracts:
        vol = c.get("volume") or 0
        oi  = c.get("openInterest") or 0
        if vol >= MIN_VOLUME and oi > 0 and (vol / oi) >= SWEEP_RATIO_MIN:
            sweeps.append({
                "contractSymbol": c.get("contractSymbol", ""),
                "strike":         c.get("strike", 0),
                "volume":         vol,
                "openInterest":   oi,
                "ratio":          round(vol / oi, 2),
                "iv":             round(c.get("impliedVolatility", 0.0), 4),
            })
    return sorted(sweeps, key=lambda x: -x["ratio"])


def detect_flow(calls: list[dict], puts: list[dict]) -> dict:
    """Compute directional flow ratio and sentiment."""
    call_vol = sum((c.get("volume") or 0) for c in calls)
    put_vol  = sum((c.get("volume") or 0) for c in puts)
    ratio    = round(call_vol / put_vol, 3) if put_vol > 0 else 999.0

    if ratio >= FLOW_RATIO_MIN:
        sentiment = "BULLISH"
    elif ratio <= (1.0 / FLOW_RATIO_MIN):
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    return {
        "call_volume":  call_vol,
        "put_volume":   put_vol,
        "cp_ratio":     ratio,
        "sentiment":    sentiment,
    }


def detect_gamma_magnet(calls: list[dict], puts: list[dict]) -> dict | None:
    """Find the top strike by combined volume — the Gamma Magnet."""
    strike_vol: dict[float, int] = {}
    for c in calls + puts:
        s   = c.get("strike", 0.0)
        vol = c.get("volume") or 0
        strike_vol[s] = strike_vol.get(s, 0) + vol
    if not strike_vol:
        return None
    top = max(strike_vol, key=lambda x: strike_vol[x])
    return {"strike": top, "volume": strike_vol[top]}


def analyze_chain(ticker: str, chain: dict) -> dict:
    """Run all three detectors on a chain and return analysis."""
    calls   = chain.get("calls", [])
    puts    = chain.get("puts",  [])
    sweeps  = detect_sweeps(calls) + detect_sweeps(puts)
    call_sweeps = [s for s in sweeps if "C" in s["contractSymbol"]]
    put_sweeps  = [s for s in sweeps if "P" in s["contractSymbol"]]
    flow    = detect_flow(calls, puts)
    magnet  = detect_gamma_magnet(calls, puts)

    # Compute velocity contribution
    velocity = 0.0
    signals  = []

    if sweeps:
        velocity += SWEEP_VELOCITY
        signals.append(f"SWEEP×{len(sweeps)}")

    if flow["sentiment"] == "BULLISH":
        velocity += FLOW_BULL_VELOCITY
        signals.append(f"BULL_FLOW({flow['cp_ratio']:.1f}x)")
    elif flow["sentiment"] == "BEARISH":
        velocity += FLOW_BEAR_VELOCITY
        signals.append(f"BEAR_FLOW({flow['cp_ratio']:.2f}x)")

    return {
        "ticker":       ticker,
        "price":        chain.get("price", 0.0),
        "source":       chain.get("source", ""),
        "sweep_count":  len(sweeps),
        "call_sweeps":  len(call_sweeps),
        "put_sweeps":   len(put_sweeps),
        "top_sweeps":   sweeps[:3],
        "flow":         flow,
        "gamma_magnet": magnet,
        "velocity":     round(velocity, 2),
        "signals":      signals,
        "ts":           datetime.now(timezone.utc).isoformat(),
    }


# ── Scan target selection ─────────────────────────────────────────────────────
def load_high_velocity_tickers(threshold: float = SCORE_THRESHOLD) -> list[str]:
    """
    Return tickers with gap/catalyst score above threshold.
    Sources: sec_catalyst_ranked.csv → combined_priority_tickers.txt fallback.
    """
    ranked = ROOT / "sec_catalyst_ranked.csv"
    if ranked.exists():
        tickers = []
        try:
            with ranked.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    score = float(row.get("score") or row.get("total_score") or 0)
                    if score >= threshold:
                        t = (row.get("ticker") or row.get("symbol") or "").strip().upper()
                        if t:
                            tickers.append(t)
            if tickers:
                optionable = [t for t in tickers if _likely_optionable(t)]
                remainder = [t for t in tickers if t not in optionable]
                return optionable + remainder
        except Exception:
            pass

    # Fallback: combined priority list
    for fname in ("combined_priority_tickers.txt", "sec_catalyst_tickers.txt"):
        p = ROOT / fname
        if p.exists():
            return [l.strip().upper() for l in p.read_text().splitlines()
                    if l.strip() and not l.startswith("#")]

    return []


# ── Main ──────────────────────────────────────────────────────────────────────
def main(limit: int = 50, dry_run: bool = False,
         single_ticker: str | None = None) -> None:

    if single_ticker:
        targets = [single_ticker.upper()]
    else:
        targets = load_high_velocity_tickers()[:limit]

    if not targets:
        print("spoke_options: no high-velocity tickers found — run rank_sec_catalysts.py first")
        return

    print(f"spoke_options: scanning {len(targets)} high-velocity tickers | "
          f"{'DRY RUN' if dry_run else 'LIVE'}")

    if dry_run:
        for t in targets[:10]:
            print(f"  Would scan: {t}")
        return

    # Load existing spark velocities
    spark_velo: dict = {}
    if SPARK_VELOCITIES.exists():
        try:
            spark_velo = json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass

    activity_log: dict = {}
    if OPTIONS_ACTIVITY.exists():
        try:
            activity_log = json.loads(OPTIONS_ACTIVITY.read_text())
        except Exception:
            pass
    spark_velo, activity_log = _prune_options_state(spark_velo, activity_log, targets)

    sweep_count   = 0
    bullish_count = 0
    bearish_count = 0

    # Preflight: identify which source is available
    has_yf      = yf is not None
    has_alpaca  = bool(_load_key("ALPACA_API_KEY") and _load_key("ALPACA_SECRET_KEY"))
    has_tradier = bool(_load_key("TRADIER_TOKEN"))
    if not has_yf and not has_alpaca and not has_tradier:
        print("\nspoke_options: No options data source configured.")
        print("  Option A (recommended): install yfinance for public Yahoo chain access")
        print("    python3 -m pip install --break-system-packages yfinance")
        print("  Option B: alpaca.markets → Sign Up → Paper Trading → API Keys")
        print("    Add to .sec_email_env: ALPACA_API_KEY= and ALPACA_SECRET_KEY=")
        print("  Option C: developer.tradier.com → Register → Sandbox Token")
        print("    Add to .sec_email_env: TRADIER_TOKEN=")
        SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
        OPTIONS_ACTIVITY.write_text(json.dumps(activity_log, indent=2))
        print("  Existing stale options state pruned.")
        return
    sources = []
    if has_yf:
        sources.append("Yahoo/yfinance")
    if has_alpaca:
        sources.append("Alpaca")
    if has_tradier:
        sources.append("Tradier sandbox")
    print(f"  Sources: {', '.join(sources)}")

    for i, ticker in enumerate(targets):
        # Prefer public Yahoo/yfinance, then broker-backed fallbacks.
        chain = fetch_chain_yfinance(ticker)
        if not chain:
            chain = fetch_chain_alpaca(ticker)
        if not chain:
            chain = fetch_chain_tradier(ticker)
        if not chain:
            time.sleep(0.2)
            continue

        analysis = analyze_chain(ticker, chain)
        activity_log[ticker] = analysis

        velo = analysis["velocity"]
        if velo != 0.0:
            spark_velo.setdefault(ticker, {})["options"] = velo
            spark_velo[ticker]["options_signals"]   = analysis["signals"]
            spark_velo[ticker]["gamma_magnet"]       = analysis.get("gamma_magnet")
            spark_velo[ticker]["options_ts"]         = analysis["ts"]
        else:
            if ticker in spark_velo:
                spark_velo[ticker].pop("options", None)

        if analysis["sweep_count"] > 0:
            sweep_count += 1
            flag = "⚡ SWEEP"
        elif analysis["flow"]["sentiment"] == "BULLISH":
            bullish_count += 1
            flag = "🟢 BULL"
        elif analysis["flow"]["sentiment"] == "BEARISH":
            bearish_count += 1
            flag = "🔴 BEAR"
        else:
            flag = "   ----"

        if velo != 0.0 or analysis["sweep_count"] > 0:
            mag = analysis.get("gamma_magnet") or {}
            print(f"  {ticker:6s}  {flag}  "
                  f"sweeps={analysis['sweep_count']}  "
                  f"C/P={analysis['flow']['cp_ratio']:.2f}  "
                  f"vel={velo:+.1f}  "
                  f"magnet@{mag.get('strike', '?')}")

        time.sleep(0.25)

        # Checkpoint every 20 tickers
        if (i + 1) % 20 == 0:
            SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
            OPTIONS_ACTIVITY.write_text(json.dumps(activity_log, indent=2))

    # Final save
    SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
    OPTIONS_ACTIVITY.write_text(json.dumps(activity_log, indent=2))

    print(f"\nspoke_options: complete")
    print(f"  Scanned    : {len(targets)} tickers")
    print(f"  Sweeps     : {sweep_count}")
    print(f"  Bullish    : {bullish_count}")
    print(f"  Bearish    : {bearish_count}")
    print(f"  Output     : options_activity.json | spark_velocities.json[options]")


if __name__ == "__main__":
    import sys
    lim    = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "50"))
    ticker = next((a.split("=")[1] for a in sys.argv if a.startswith("--ticker=")), None)
    dry    = "--dry-run" in sys.argv
    main(limit=lim, dry_run=dry, single_ticker=ticker)
