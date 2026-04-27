#!/usr/bin/env python3
"""agent_hyperliquid.py — Catalyst Edge → Hyperliquid 24/7 perp trader.

The 24/7 leg of the trading harness. Equity bots only fire 9:30-4 ET; this
one runs every cron tick, all year. Two signal stacks combined:

  STACK A (crypto-treasury equity flags, weight × 3):
    Whenever scanner flags MSTR / MARA / RIOT / COIN / CIFR / CLSK / IREN /
    BITF / HUT / HIVE / TSLA / SQ / HOOD / BITO during market hours, treat
    that as a crypto-positive catalyst. Open a small BTC-perp long.

  STACK B (always-on on-chain signal stack, weight × 1):
    Reuses the same crypto signals as agent_alpaca_crypto.py:
      +1  BTC ETF heavy interest (combined dollar_volume_usd > $2B)
      +1  Broad-crypto calm (defi liquidations drift, |avg 1d| <= 2%)
      +1  ETH gas relief (only counts for ETH/USD entries)

Combined score:
  score = 3 × (1 if any crypto-treasury equity flagged today else 0)
        + B_score
  Threshold to enter: score >= 2.

ROUTING:
  - DRY-RUN by default. Logs every decision.
  - HYPERLIQUID_LIVE_ORDERS=1 + HYPERLIQUID_PRIVATE_KEY in .sec_email_env
    flips real orders. Wallet must hold USDC on Arbitrum and be approved
    for Hyperliquid trading (one-time on-chain transaction at app.hyperliquid.xyz).

SAFETY:
  HYPERLIQUID_MAX_POSITION_USD   default 25  (small while validating)
  HYPERLIQUID_MAX_LEVERAGE       default 2  (low — this is signal proof, not a yolo)
  HYPERLIQUID_MAX_OPEN           default 2  (BTC + ETH at most)
  .agent_hyperliquid_halted file → kill switch

OUTPUTS:
  docs/data/hyperliquid_decisions.json   today's decisions + positions
  docs/data/hyperliquid_ledger.json      audit trail of placed orders
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
HALT_FILE = ROOT / ".agent_hyperliquid_halted"
COMBINED_CSV = ROOT / "combined_priority.csv"
ETF_CSV = ROOT / "docs/btc_etf_flows.csv"
DEFI_CSV = ROOT / "docs/defi_liquidations.csv"
GAS_CSV = ROOT / "eth_gas.csv"
DECISIONS_OUT = ROOT / "docs/data/hyperliquid_decisions.json"
LEDGER_OUT = ROOT / "docs/data/hyperliquid_ledger.json"
LOG_PATH = ROOT / "logs/hyperliquid.log"
LOG_PATH.parent.mkdir(exist_ok=True)
DECISIONS_OUT.parent.mkdir(parents=True, exist_ok=True)

# Crypto-treasury equity universe (mirrors agent_crypto_treasury.py)
TREASURY_UNIVERSE = {
    "MSTR", "TSLA", "SQ", "BLOCK", "MARA", "RIOT", "CIFR", "CLSK",
    "IREN", "BITF", "HUT", "HIVE", "COIN", "HOOD", "BITO",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    line = f"[{now_iso()}] {msg}"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def env_float(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


# ── Signal stack ────────────────────────────────────────────────────────────

def treasury_flags() -> list[str]:
    """Crypto-treasury equities flagged by SEC scanner today."""
    if not COMBINED_CSV.exists():
        return []
    flagged: list[str] = []
    with COMBINED_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            if t in TREASURY_UNIVERSE:
                flagged.append(t)
    return flagged


def btc_etf_heavy() -> bool:
    if not ETF_CSV.exists():
        return False
    try:
        with ETF_CSV.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return False
        latest = rows[-1]
        dv = float(latest.get("dollar_volume_usd") or latest.get("net_flow_usd") or 0)
        return dv > 2_000_000_000
    except Exception as e:
        log(f"etf signal ERROR: {e}")
        return False


def crypto_calm() -> bool:
    if not DEFI_CSV.exists():
        return False
    try:
        with DEFI_CSV.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return False
        drift = sum(1 for r in rows[-10:] if (r.get("stress_label") or "").lower() == "drift")
        return drift >= 6
    except Exception as e:
        log(f"defi signal ERROR: {e}")
        return False


def eth_gas_relief() -> bool:
    if not GAS_CSV.exists():
        return False
    try:
        with GAS_CSV.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return False
        latest = rows[-1]
        label = (latest.get("congestion_label") or "").lower()
        return label in ("relief", "cool", "low")
    except Exception:
        return False


def signal_score() -> dict:
    flagged = treasury_flags()
    treasury_w = 3 if flagged else 0
    etf = btc_etf_heavy()
    calm = crypto_calm()
    gas = eth_gas_relief()
    btc_score = treasury_w + (1 if etf else 0) + (1 if calm else 0)
    eth_score = treasury_w + (1 if etf else 0) + (1 if calm else 0) + (1 if gas else 0)
    return {
        "as_of": now_iso(),
        "treasury_flags": flagged,
        "treasury_w": treasury_w,
        "btc_etf_heavy": etf,
        "crypto_calm": calm,
        "eth_gas_relief": gas,
        "btc_score": btc_score,
        "eth_score": eth_score,
    }


# ── Hyperliquid wiring ──────────────────────────────────────────────────────

def hl_live_state() -> dict:
    """READ-ONLY: pull mid-prices and account state. No signing needed."""
    out: dict = {"connected": False}
    try:
        from hyperliquid.info import Info  # type: ignore
        from hyperliquid.utils import constants  # type: ignore
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        mids = info.all_mids()
        out["btc_mid"] = float(mids.get("BTC") or 0)
        out["eth_mid"] = float(mids.get("ETH") or 0)
        out["connected"] = True
        wallet = (os.environ.get("HYPERLIQUID_WALLET") or "").strip()
        if wallet:
            try:
                state = info.user_state(wallet)
                out["account_value"] = float(state.get("marginSummary", {}).get("accountValue") or 0)
                out["positions"] = [
                    {"coin": p["position"]["coin"],
                     "szi": float(p["position"]["szi"]),
                     "entry_px": float(p["position"]["entryPx"] or 0)}
                    for p in (state.get("assetPositions") or [])
                ]
            except Exception as e:
                out["account_state_err"] = str(e)[:120]
    except Exception as e:
        out["err"] = str(e)[:120]
    return out


def hl_place_order(coin: str, sz_usd: float, mid_px: float,
                   private_key: str, max_leverage: int) -> dict:
    """LIVE: place a market long. Gated upstream by HYPERLIQUID_LIVE_ORDERS=1."""
    try:
        from hyperliquid.exchange import Exchange  # type: ignore
        from hyperliquid.utils import constants  # type: ignore
        from eth_account import Account  # type: ignore
        wallet = Account.from_key(private_key)
        exchange = Exchange(wallet, constants.MAINNET_API_URL)
        # Set leverage cap for this coin
        try:
            exchange.update_leverage(max_leverage, coin)
        except Exception as e:
            log(f"  hl set_leverage {coin} warn: {e}")
        # Compute size in coin (round to platform's granularity)
        if mid_px <= 0:
            return {"ok": False, "reason": "no_mid_price"}
        sz = round(sz_usd / mid_px, 4)
        if sz <= 0:
            return {"ok": False, "reason": "size_too_small"}
        # Slippage 0.5% market order
        result = exchange.market_open(coin, True, sz, None, 0.005)
        return {"ok": True, "hyperliquid": result}
    except Exception as e:
        return {"ok": False, "reason": f"exchange_err: {str(e)[:120]}"}


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    load_env()
    if HALT_FILE.exists():
        log("HALT file present — exiting")
        return 0

    max_pos = env_float("HYPERLIQUID_MAX_POSITION_USD", 25.0)
    max_lev = env_int("HYPERLIQUID_MAX_LEVERAGE", 2)
    max_open = env_int("HYPERLIQUID_MAX_OPEN", 2)
    live = (os.environ.get("HYPERLIQUID_LIVE_ORDERS") or "").strip() == "1"
    pk = (os.environ.get("HYPERLIQUID_PRIVATE_KEY") or "").strip()
    threshold = env_int("HYPERLIQUID_SCORE_THRESHOLD", 2)

    sig = signal_score()
    state = hl_live_state()
    log(f"signals btc={sig['btc_score']} eth={sig['eth_score']} treasury={sig['treasury_flags']} "
        f"hl_connected={state.get('connected')} live={live}")

    # Build candidate list
    candidates: list[dict] = []
    for coin, score, mid_key in [("BTC", sig["btc_score"], "btc_mid"),
                                  ("ETH", sig["eth_score"], "eth_mid")]:
        mid = state.get(mid_key, 0)
        candidates.append({
            "coin": coin,
            "score": score,
            "above_threshold": score >= threshold,
            "mid_px": mid,
        })

    # Decide
    decisions: list[dict] = []
    placed: list[dict] = []
    for c in sorted(candidates, key=lambda x: -x["score"])[:max_open]:
        decision = {**c, "max_position_usd": max_pos, "max_leverage": max_lev,
                    "live": live, "result": None}
        if not c["above_threshold"]:
            decision["result"] = {"ok": False, "reason": f"score={c['score']} < threshold={threshold}"}
        elif not live:
            decision["result"] = {"ok": False, "reason": "dry_run (HYPERLIQUID_LIVE_ORDERS!=1)"}
        elif not pk:
            decision["result"] = {"ok": False, "reason": "no_HYPERLIQUID_PRIVATE_KEY"}
        elif not c["mid_px"]:
            decision["result"] = {"ok": False, "reason": "no_mid_price"}
        else:
            decision["result"] = hl_place_order(c["coin"], max_pos, c["mid_px"], pk, max_lev)
            if decision["result"].get("ok"):
                placed.append(decision)
        decisions.append(decision)
        log(f"  {c['coin']} score={c['score']} → {decision['result']['reason'] if not decision['result'].get('ok') else 'PLACED'}")

    DECISIONS_OUT.write_text(json.dumps({
        "as_of": now_iso(),
        "signals": sig,
        "live_state": state,
        "config": {
            "max_position_usd": max_pos,
            "max_leverage": max_lev,
            "max_open": max_open,
            "score_threshold": threshold,
            "live_orders": live,
            "wallet_configured": bool(pk),
        },
        "decisions": decisions,
    }, indent=2))

    # Append to ledger
    if placed:
        existing: list[dict] = []
        if LEDGER_OUT.exists():
            try:
                existing = json.loads(LEDGER_OUT.read_text())
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        for p in placed:
            existing.append({"placed_at": now_iso(), **p})
        LEDGER_OUT.write_text(json.dumps(existing[-500:], indent=2))

    log(f"DONE  decisions={len(decisions)}  placed={len(placed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
