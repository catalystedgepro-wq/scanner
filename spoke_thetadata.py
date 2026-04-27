#!/usr/bin/env python3
"""spoke_thetadata.py — Domain 8: Options Flow (ThetaData + Yahoo Finance Fallback).

Scans for unusual options activity: high volume-to-OI ratios, large block
trades, and put/call skew anomalies. Injects OPTIONS velocity into
spark_velocities.json for the HUD's Gamma Well visualization.

Physics:
    Unusual call activity detected  → spark_velocity = +8.0 (bullish)
    Unusual put activity detected   → spark_velocity = -6.0 (bearish)
    Block trade > $500K notional    → spark_velocity = +/-12.0
    Decay: k = log(2)/48 ≈ 0.01443 (half-life = 48h — options are fast)

Architecture:
    1. If THETADATA_API_KEY set → use ThetaData bulk snapshot (preferred)
    2. Fallback → Yahoo Finance options chain (free, rate-limited)
    3. Filter for unusual activity (vol/OI > 3x, block trades)
    4. Write to spark_velocities.json["options"] + metadata
    5. Write gamma_size to entity for HUD gamma well rendering

Data Sources:
    Primary:  ThetaData REST API ($25/mo) — thetadata.net
    Fallback: Yahoo Finance (free, no key) — rate-limited

Run: python3 spoke_thetadata.py [--limit=100] [--dry-run]
Schedule: Every 30 minutes during market hours (09:30-16:00 ET).
Pure stdlib — no pip dependencies.
"""
from __future__ import annotations

import json
import math
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent

SPARK_VELOCITIES = ROOT / "spark_velocities.json"
ENTITY_MASTER    = ROOT / "entity_master.json"
OPTIONS_CACHE    = ROOT / ".options_cache.json"

# Physics constants
OPTIONS_VELOCITY_CALL  = 8.0    # bullish unusual call activity
OPTIONS_VELOCITY_PUT   = -6.0   # bearish unusual put activity
OPTIONS_VELOCITY_BLOCK = 12.0   # large block trade (sign depends on side)
_DECAY_K = math.log(2) / 48     # half-life = 48 hours

# Detection thresholds
VOL_OI_THRESHOLD   = 3.0   # volume / open interest ratio for "unusual"
BLOCK_NOTIONAL_MIN = 500_000  # $500K minimum for block classification
MIN_OI             = 100    # ignore illiquid strikes
MIN_VOLUME         = 50     # ignore noise
GAMMA_SIZE_SCALE   = 20.0   # normalize gamma_size for HUD visualization

# Rate limit
YAHOO_DELAY_S  = 0.6
THETA_DELAY_S  = 0.25

# TLS context for Yahoo (bypasses some cert issues on older systems)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

OPTIONS_FIELDS = ("options", "options_side", "options_vol_oi",
                  "options_notional", "options_ts", "gamma_size")


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for p in (ROOT / ".sec_email_env", Path.home() / ".sec_email_env"):
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def _thetadata_key() -> str:
    return os.environ.get("THETADATA_API_KEY", _load_env().get("THETADATA_API_KEY", ""))


def load_spark_velocities() -> dict:
    if SPARK_VELOCITIES.exists():
        try:
            return json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass
    return {}


def save_spark_velocities(data: dict) -> None:
    SPARK_VELOCITIES.write_text(json.dumps(data, indent=2))


def load_options_cache() -> dict:
    if OPTIONS_CACHE.exists():
        try:
            return json.loads(OPTIONS_CACHE.read_text())
        except Exception:
            pass
    return {}


def save_options_cache(data: dict) -> None:
    OPTIONS_CACHE.write_text(json.dumps(data, indent=2))


def compute_options_velocity(detected_ts: str, magnitude: float) -> float:
    """Apply exponential decay from detection time."""
    try:
        dt = datetime.fromisoformat(detected_ts.replace("Z", "+00:00"))
        hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        return round(magnitude * math.exp(-_DECAY_K * max(0, hours)), 4)
    except Exception:
        return round(magnitude, 4)


# ── ThetaData Provider ────────────────────────────────────────────────────────

def fetch_thetadata_options(ticker: str, api_key: str) -> dict | None:
    """Fetch options snapshot from ThetaData REST API.

    Returns dict with keys: calls_vol, puts_vol, calls_oi, puts_oi,
    max_vol_oi, max_notional, dominant_side, unusual_strikes.
    """
    url = (
        f"https://api.thetadata.net/v2/snapshot/option/quote"
        f"?root={ticker}&exp_date_range=0,30&right=C,P"
    )
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"    ThetaData error for {ticker}: {e}", file=sys.stderr)
        return None

    contracts = data.get("response", [])
    if not contracts:
        return None

    calls_vol = 0
    puts_vol = 0
    calls_oi = 0
    puts_oi = 0
    unusual_strikes: list[dict] = []

    for c in contracts:
        right  = c.get("right", "C")
        vol    = int(c.get("volume", 0) or 0)
        oi     = int(c.get("open_interest", 0) or 0)
        bid    = float(c.get("bid", 0) or 0)
        ask    = float(c.get("ask", 0) or 0)
        mid    = (bid + ask) / 2 if (bid + ask) > 0 else 0
        strike = float(c.get("strike", 0) or 0) / 1000  # ThetaData uses millis

        if right == "C":
            calls_vol += vol
            calls_oi += oi
        else:
            puts_vol += vol
            puts_oi += oi

        if oi >= MIN_OI and vol >= MIN_VOLUME:
            ratio = vol / max(oi, 1)
            notional = vol * mid * 100
            if ratio >= VOL_OI_THRESHOLD or notional >= BLOCK_NOTIONAL_MIN:
                unusual_strikes.append({
                    "strike": strike,
                    "right": right,
                    "vol": vol,
                    "oi": oi,
                    "vol_oi": round(ratio, 2),
                    "notional": round(notional),
                    "mid": round(mid, 2),
                })

    total_vol = calls_vol + puts_vol
    total_oi  = calls_oi + puts_oi
    vol_oi    = total_vol / max(total_oi, 1)
    dominant  = "call" if calls_vol > puts_vol * 1.5 else ("put" if puts_vol > calls_vol * 1.5 else "mixed")

    max_notional = max((s["notional"] for s in unusual_strikes), default=0)
    max_vol_oi   = max((s["vol_oi"] for s in unusual_strikes), default=0)

    return {
        "calls_vol": calls_vol,
        "puts_vol": puts_vol,
        "calls_oi": calls_oi,
        "puts_oi": puts_oi,
        "total_vol": total_vol,
        "total_oi": total_oi,
        "vol_oi": round(vol_oi, 2),
        "max_vol_oi": round(max_vol_oi, 2),
        "max_notional": max_notional,
        "dominant_side": dominant,
        "unusual_count": len(unusual_strikes),
        "unusual_strikes": unusual_strikes[:5],
        "source": "thetadata",
    }


# ── Yahoo Finance Fallback ────────────────────────────────────────────────────

def fetch_yahoo_options(ticker: str) -> dict | None:
    """Scrape options chain from Yahoo Finance (free, no key).

    Returns same shape as fetch_thetadata_options.
    """
    url = f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) CerebroscopeBot/1.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12, context=_SSL_CTX) as resp:
            raw = json.loads(resp.read().decode())
    except Exception as e:
        print(f"    Yahoo options error for {ticker}: {e}", file=sys.stderr)
        return None

    result = raw.get("optionChain", {}).get("result", [])
    if not result:
        return None

    chain = result[0]
    options = chain.get("options", [])
    if not options:
        return None

    nearest = options[0]
    calls = nearest.get("calls", [])
    puts  = nearest.get("puts", [])

    calls_vol = sum(int(c.get("volume", 0) or 0) for c in calls)
    puts_vol  = sum(int(p.get("volume", 0) or 0) for p in puts)
    calls_oi  = sum(int(c.get("openInterest", 0) or 0) for c in calls)
    puts_oi   = sum(int(p.get("openInterest", 0) or 0) for p in puts)

    unusual_strikes: list[dict] = []

    for contract in calls + puts:
        vol    = int(contract.get("volume", 0) or 0)
        oi     = int(contract.get("openInterest", 0) or 0)
        bid    = float(contract.get("bid", 0) or 0)
        ask    = float(contract.get("ask", 0) or 0)
        mid    = (bid + ask) / 2 if (bid + ask) > 0 else 0
        strike = float(contract.get("strike", 0) or 0)
        right  = "C" if contract.get("contractSymbol", "").endswith("C") or contract in calls else "P"

        # Yahoo doesn't have a reliable right indicator in the object itself
        # Determine from whether it came from calls or puts list
        if contract in calls:
            right = "C"
        else:
            right = "P"

        if oi >= MIN_OI and vol >= MIN_VOLUME:
            ratio = vol / max(oi, 1)
            notional = vol * mid * 100
            if ratio >= VOL_OI_THRESHOLD or notional >= BLOCK_NOTIONAL_MIN:
                unusual_strikes.append({
                    "strike": strike,
                    "right": right,
                    "vol": vol,
                    "oi": oi,
                    "vol_oi": round(ratio, 2),
                    "notional": round(notional),
                    "mid": round(mid, 2),
                })

    total_vol = calls_vol + puts_vol
    total_oi  = calls_oi + puts_oi
    vol_oi    = total_vol / max(total_oi, 1)
    dominant  = "call" if calls_vol > puts_vol * 1.5 else ("put" if puts_vol > calls_vol * 1.5 else "mixed")

    max_notional = max((s["notional"] for s in unusual_strikes), default=0)
    max_vol_oi   = max((s["vol_oi"] for s in unusual_strikes), default=0)

    return {
        "calls_vol": calls_vol,
        "puts_vol": puts_vol,
        "calls_oi": calls_oi,
        "puts_oi": puts_oi,
        "total_vol": total_vol,
        "total_oi": total_oi,
        "vol_oi": round(vol_oi, 2),
        "max_vol_oi": round(max_vol_oi, 2),
        "max_notional": max_notional,
        "dominant_side": dominant,
        "unusual_count": len(unusual_strikes),
        "unusual_strikes": unusual_strikes[:5],
        "source": "yahoo",
    }


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_options_activity(snapshot: dict) -> tuple[float, str]:
    """Score the options snapshot into a velocity magnitude + side label.

    Returns (velocity, side_label).
    """
    if not snapshot or snapshot.get("total_vol", 0) < MIN_VOLUME:
        return 0.0, "quiet"

    vol_oi     = snapshot.get("max_vol_oi", 0)
    notional   = snapshot.get("max_notional", 0)
    dominant   = snapshot.get("dominant_side", "mixed")
    unusual_ct = snapshot.get("unusual_count", 0)

    if unusual_ct == 0:
        return 0.0, "quiet"

    # Base velocity from vol/OI ratio
    if vol_oi >= 10:
        base = OPTIONS_VELOCITY_BLOCK
    elif vol_oi >= VOL_OI_THRESHOLD:
        base = OPTIONS_VELOCITY_CALL
    else:
        base = OPTIONS_VELOCITY_CALL * 0.5

    # Scale by number of unusual strikes (capped at 2x)
    scale = min(2.0, 1.0 + (unusual_ct - 1) * 0.2)
    magnitude = base * scale

    # Block trade boost
    if notional >= BLOCK_NOTIONAL_MIN:
        magnitude = max(magnitude, OPTIONS_VELOCITY_BLOCK)

    # Sign by dominant side
    if dominant == "put":
        return round(-abs(magnitude), 2), "bearish_put"
    elif dominant == "call":
        return round(abs(magnitude), 2), "bullish_call"
    else:
        return round(abs(magnitude) * 0.6, 2), "mixed"


def compute_gamma_size(snapshot: dict) -> float:
    """Compute gamma_size for HUD gamma well visualization.

    Returns 0-1 normalized value. > 0.2 triggers the wireframe sphere.
    """
    if not snapshot:
        return 0.0
    total_vol = snapshot.get("total_vol", 0)
    unusual   = snapshot.get("unusual_count", 0)
    notional  = snapshot.get("max_notional", 0)

    raw = (
        min(total_vol / 10000, 1.0) * 0.3
        + min(unusual / 5, 1.0) * 0.4
        + min(notional / 2_000_000, 1.0) * 0.3
    )
    return round(min(1.0, raw), 4)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(limit: int = 100, dry_run: bool = False) -> None:
    if not ENTITY_MASTER.exists():
        print("spoke_thetadata: entity_master.json not found")
        return

    entity_master: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))
    api_key = _thetadata_key()
    source = "thetadata" if api_key else "yahoo"

    print(f"[spoke_thetadata] {datetime.now(timezone.utc).isoformat()}")
    print(f"  Source: {source} | Limit: {limit} | {'DRY RUN' if dry_run else 'LIVE'}")

    if not api_key:
        print("  THETADATA_API_KEY not set — falling back to Yahoo Finance")
        print("  For real-time data: thetadata.net ($25/mo)")

    # Priority: active catalyst tickers first
    active: set[str] = set()
    for fname in ("sec_catalyst_tickers.txt", "combined_priority_tickers.txt"):
        p = ROOT / fname
        if p.exists():
            active.update(l.strip().upper() for l in p.read_text().splitlines() if l.strip())

    def _priority(t: str) -> int:
        if t in active:
            return 0
        cap = entity_master.get(t, {}).get("cap_tier", "")
        if cap in ("mega", "large"):
            return 1
        return 2

    # Select targets — only equities with decent gravity
    targets = [
        t for t, r in entity_master.items()
        if r.get("name")
        and not r.get("etf")
        and float(r.get("gravity", 0)) >= 5.0
    ]
    targets.sort(key=_priority)
    targets = targets[:limit]

    print(f"  Targets: {len(targets)} tickers")

    if dry_run:
        for t in targets[:5]:
            print(f"  Would scan: {t}")
        return

    options_cache = load_options_cache()
    spark_velo    = load_spark_velocities()
    now_iso       = datetime.now(timezone.utc).isoformat()

    unusual_found = 0
    quiet_count   = 0
    error_count   = 0

    for i, ticker in enumerate(targets):
        # Skip if checked today already
        cached = options_cache.get(ticker, {})
        if cached.get("checked") == date.today().isoformat() and cached.get("velocity") is not None:
            # Re-apply decayed velocity from cache
            velocity = compute_options_velocity(
                cached.get("ts", now_iso),
                cached.get("raw_magnitude", 0),
            )
            if velocity != 0:
                spark_velo.setdefault(ticker, {})["options"] = velocity
                spark_velo[ticker]["gamma_size"] = cached.get("gamma_size", 0)
            continue

        # Fetch options data
        if api_key:
            snapshot = fetch_thetadata_options(ticker, api_key)
            delay = THETA_DELAY_S
        else:
            snapshot = fetch_yahoo_options(ticker)
            delay = YAHOO_DELAY_S

        if snapshot is None:
            error_count += 1
            time.sleep(delay)
            continue

        velocity, side = score_options_activity(snapshot)
        gamma = compute_gamma_size(snapshot)

        options_cache[ticker] = {
            "checked": date.today().isoformat(),
            "ts": now_iso,
            "velocity": velocity,
            "raw_magnitude": abs(velocity),
            "side": side,
            "gamma_size": gamma,
            "vol_oi": snapshot.get("max_vol_oi", 0),
            "notional": snapshot.get("max_notional", 0),
            "unusual_count": snapshot.get("unusual_count", 0),
            "source": snapshot.get("source", source),
        }

        if velocity != 0:
            spark_velo.setdefault(ticker, {})["options"]          = velocity
            spark_velo[ticker]["options_side"]     = side
            spark_velo[ticker]["options_vol_oi"]   = snapshot.get("max_vol_oi", 0)
            spark_velo[ticker]["options_notional"] = snapshot.get("max_notional", 0)
            spark_velo[ticker]["options_ts"]       = now_iso
            spark_velo[ticker]["gamma_size"]       = gamma
            unusual_found += 1
            icon = "📈" if velocity > 0 else "📉"
            print(f"  {icon} {ticker:6s}  {side:14s}  {velocity:+.1f}v  "
                  f"vol/OI={snapshot['max_vol_oi']:.1f}  "
                  f"gamma={gamma:.2f}  "
                  f"notional=${snapshot['max_notional']:,.0f}")
        else:
            # Clear stale entry
            if ticker in spark_velo and "options" in spark_velo[ticker]:
                for field in OPTIONS_FIELDS:
                    spark_velo[ticker].pop(field, None)
            quiet_count += 1

        # Checkpoint every 25
        if (i + 1) % 25 == 0:
            save_options_cache(options_cache)
            save_spark_velocities(spark_velo)
            print(f"  [{i+1}/{len(targets)}] checkpoint — {unusual_found} unusual so far")

        time.sleep(delay)

    # Final save
    save_options_cache(options_cache)
    save_spark_velocities(spark_velo)

    print(f"\n[spoke_thetadata] complete")
    print(f"  Scanned  : {len(targets)} tickers via {source}")
    print(f"  Unusual  : {unusual_found}")
    print(f"  Quiet    : {quiet_count}")
    print(f"  Errors   : {error_count}")
    print(f"  Output   : spark_velocities.json[options, gamma_size]")


if __name__ == "__main__":
    _limit = 100
    _dry = "--dry-run" in sys.argv
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            try:
                _limit = int(arg.split("=")[1])
            except ValueError:
                pass
    main(limit=_limit, dry_run=_dry)
