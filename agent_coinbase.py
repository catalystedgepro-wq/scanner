#!/usr/bin/env python3
"""agent_coinbase.py — Catalyst Edge → Coinbase Advanced 24/7 spot trader.

Replaces the Hyperliquid bot for US-jurisdiction users (Hyperliquid blocks
US/sanctioned IPs). Coinbase Advanced is fully US-legal, supports BTC/ETH/
SOL/AVAX spot, uses Ed25519 JWT auth (Coinbase Developer Platform), 24/7.

SAME signal stack as Hyperliquid bot — proves the strategy is venue-portable:
  STACK A (crypto-treasury equity flags from SEC scanner, weight × 3)
  STACK B (BTC ETF heavy + DeFi calm + ETH gas relief, weight × 1 each)
  Threshold ≥ 2 to enter.

ROUTING:
  - DRY-RUN by default. Logs decisions.
  - COINBASE_LIVE_ORDERS=1 + COINBASE_API_KEY + COINBASE_API_SECRET in
    .sec_email_env flips real spot orders.

SAFETY:
  COINBASE_MAX_POSITION_USD     default 25  (small while validating)
  COINBASE_MAX_OPEN             default 2
  COINBASE_SCORE_THRESHOLD      default 2
  .agent_coinbase_halted file → kill switch

OUTPUTS:
  docs/data/coinbase_decisions.json
  docs/data/coinbase_ledger.json

DOCS: https://docs.cdp.coinbase.com/advanced-trade/docs/welcome
AUTH: Ed25519 JWT. The CDP API key download (cdp_api_key.json) gives:
  id          → JWT 'sub' + 'kid' header
  privateKey  → base64-encoded Ed25519 keypair (64 bytes; first 32 are signing key)
"""
from __future__ import annotations

import base64
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".sec_email_env"
HALT_FILE = ROOT / ".agent_coinbase_halted"
COMBINED_CSV = ROOT / "combined_priority.csv"
ETF_CSV = ROOT / "docs/btc_etf_flows.csv"
DEFI_CSV = ROOT / "docs/defi_liquidations.csv"
GAS_CSV = ROOT / "eth_gas.csv"
DECISIONS_OUT = ROOT / "docs/data/coinbase_decisions.json"
LEDGER_OUT = ROOT / "docs/data/coinbase_ledger.json"
LOG_PATH = ROOT / "logs/coinbase.log"
LOG_PATH.parent.mkdir(exist_ok=True)
DECISIONS_OUT.parent.mkdir(parents=True, exist_ok=True)

CB_API = "https://api.coinbase.com"
TREASURY_UNIVERSE = {
    "MSTR", "TSLA", "SQ", "BLOCK", "MARA", "RIOT", "CIFR", "CLSK",
    "IREN", "BITF", "HUT", "HIVE", "COIN", "HOOD", "BITO",
}

# Coinbase product IDs (spot pairs traded on Coinbase Advanced).
# Expanded universe: top-volume coins where our signal stack has a meaningful read.
# All have deep USD liquidity on Coinbase, USD-quoted, no exotic asset risk.
# Universe pruned 2026-04-26 after 60-day backtest:
#   KEEP (positive alpha vs buy-and-hold over 60d):
#     BTC: hit=67% strategy=+19.2% B&H=+3.9%
#     ETH: hit=55% strategy=+16.7% B&H=+1.5%
#     ARB: hit=50% strategy=+15.7% B&H=-15.7%
#     LINK: hit=53% strategy=+10.8% B&H=+8.0%
#     ATOM: hit=53% strategy=+7.4% B&H=+4.9%
#   DROPPED (signal is anti-correlated or hit rate too low — were eating capital):
#     POL: hit=21% strategy=-29.6%
#     DOT: hit=41% strategy=-12.5%
#     AVAX: hit=46% strategy=-1.6% (flat noise)
#     DOGE: tracks B&H not strategy alpha
#     SOL: tracks B&H not strategy alpha
COINS = [
    {"product": "BTC-USD",  "sym": "BTC"},
    {"product": "ETH-USD",  "sym": "ETH"},
    {"product": "ARB-USD",  "sym": "ARB"},
    {"product": "LINK-USD", "sym": "LINK"},
    {"product": "ATOM-USD", "sym": "ATOM"},
]


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


# ── Signal stack (mirrors agent_hyperliquid.py) ─────────────────────────────

def treasury_flags() -> list[str]:
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
    except Exception:
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
    except Exception:
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
        return (latest.get("congestion_label") or "").lower() in ("relief", "cool", "low")
    except Exception:
        return False


def fetch_hourly_closes(product_id: str, hours: int = 720) -> list[float]:
    """Fetch last `hours` hourly closes (newest-last). Used by promoted lab
    strategies that need 7d/30d return windows. Coinbase Advanced API limits
    350 candles per request, so we page in chunks of 300 hours."""
    closes: list[float] = []
    end = int(time.time())
    chunk = 300
    remaining = hours
    while remaining > 0:
        size = min(chunk, remaining)
        start = end - size * 3600
        try:
            url = (f"https://api.coinbase.com/api/v3/brokerage/market/products/"
                   f"{product_id}/candles?start={start}&end={end}&granularity=ONE_HOUR")
            with urllib.request.urlopen(url, timeout=10) as r:
                d = json.loads(r.read())
            candles = d.get("candles", [])
            # Coinbase returns newest-first — flip to oldest-first for the chunk
            chunk_closes = [float(c["close"]) for c in reversed(candles)]
            closes = chunk_closes + closes  # prepend so overall list is oldest→newest
            end = start
            remaining -= size
            time.sleep(0.15)  # avoid rate limit
        except Exception as e:
            log(f"  fetch_hourly_closes {product_id} chunk failed: {str(e)[:60]}")
            break
    return closes


def entry_dual_momentum(closes: list[float]) -> tuple[bool, str]:
    """Mirrors strategy_lab.py:entry_dual_momentum_filter. Returns (fire, reason).
    Requires BOTH 7d AND 30d returns positive, plus close not at 24h high (no
    chase-the-top). 91.7% hit rate / +2.0% alpha in 60d backtest 2026-04-27."""
    if not closes or len(closes) < 720:
        return False, f"need_720_bars_got_{len(closes)}"
    ret_7d = closes[-1] / closes[-168] - 1
    ret_30d = closes[-1] / closes[-720] - 1
    if ret_7d <= 0:
        return False, f"7d_neg_{ret_7d*100:.2f}%"
    if ret_30d <= 0:
        return False, f"30d_neg_{ret_30d*100:.2f}%"
    high_24h = max(closes[-24:])
    if high_24h > 0 and closes[-1] / high_24h > 0.99:
        return False, "at_24h_high"
    return True, f"dual_mom_7d={ret_7d*100:+.2f}%_30d={ret_30d*100:+.2f}%"


# Strategy entry-function registry. Keys must match strategy_lab.py STRATEGIES[].id
# When `.live_strategy.json` names one of these, the live bot uses its entry rule
# in place of the legacy SEC-catalyst-gated path.
STRATEGY_ENTRY_FNS = {
    "dual_momentum": entry_dual_momentum,
}


def read_live_strategy() -> dict | None:
    """Return the promoted strategy config or None if no file / no entry fn."""
    path = ROOT / ".live_strategy.json"
    if not path.exists():
        return None
    try:
        cfg = json.loads(path.read_text())
        if cfg.get("strategy_id") in STRATEGY_ENTRY_FNS:
            return cfg
        log(f"  .live_strategy.json names '{cfg.get('strategy_id')}' but no live entry fn — falling back to legacy path")
        return None
    except Exception as e:
        log(f"  read_live_strategy failed: {str(e)[:60]}")
        return None


def intraday_momentum(product_id: str) -> dict:
    """Pull 24x hourly candles for product, compute 1h / 4h / 24h returns.
    Returns a dict with 'score_boost' (0-2) based on:
      +1 if 24h return > 0 AND 4h return > 0 (uptrend agreement)
      +1 if last 1h return is in top quintile of trailing 24 hours (breakout)

    Note: tried adding a realized-volatility regime filter (DEAD/NORMAL/STRESS/
    CHAOS classification) on 2026-04-26 but backtest showed +0.01% delta —
    statistical noise. Reverted. The filter blocked trades in calm markets
    without adding alpha. Sometimes simpler wins."""
    try:
        end = int(time.time())
        start = end - 86400
        url = (f"https://api.coinbase.com/api/v3/brokerage/market/products/"
               f"{product_id}/candles?start={start}&end={end}&granularity=ONE_HOUR")
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read())
        candles = d.get("candles", [])
        if len(candles) < 5:
            return {"boost": 0, "reason": "no_data"}
        closes = [float(c["close"]) for c in candles]  # newest-first per Coinbase
        latest = closes[0]
        chg_1h = (latest / closes[1] - 1) if len(closes) > 1 else 0
        chg_4h = (latest / closes[4] - 1) if len(closes) > 4 else 0
        chg_24h = (latest / closes[-1] - 1)
        hourly_rets = [(closes[i]/closes[i+1] - 1) for i in range(len(closes)-1)]
        sorted_rets = sorted(hourly_rets, reverse=True)
        top_quintile = sorted_rets[max(1, len(sorted_rets)//5) - 1] if sorted_rets else 0
        boost = 0
        reasons: list[str] = []
        if chg_24h > 0 and chg_4h > 0:
            boost += 1
            reasons.append("trend_up")
        if chg_1h > 0 and chg_1h >= top_quintile:
            boost += 1
            reasons.append("breakout_1h")
        return {
            "boost": boost,
            "chg_1h_pct": round(chg_1h * 100, 3),
            "chg_4h_pct": round(chg_4h * 100, 3),
            "chg_24h_pct": round(chg_24h * 100, 3),
            "reason": ",".join(reasons) if reasons else "no_signal",
        }
    except Exception as e:
        return {"boost": 0, "reason": f"err: {str(e)[:40]}"}


def coinbase_premium() -> dict:
    """Coinbase premium = (Coinbase BTC - Kraken BTC) / Kraken BTC.
    When Coinbase trades >0.3% premium, US institutions are buying via
    Coinbase — historically a strong bullish leading indicator.
    Free signal, no auth, no new infra."""
    try:
        # Coinbase
        with urllib.request.urlopen(
            "https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD",
            timeout=5,
        ) as r:
            cb = float(json.loads(r.read()).get("price") or 0)
        # Kraken
        with urllib.request.urlopen(
            "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
            timeout=5,
        ) as r:
            d = json.loads(r.read())
            result = d.get("result", {})
            first_key = next(iter(result), None)
            kr = float(result.get(first_key, {}).get("c", [0])[0]) if first_key else 0
        if cb > 0 and kr > 0:
            premium = (cb - kr) / kr
            return {"premium_pct": round(premium * 100, 4),
                    "boost": 1 if premium > 0.003 else 0,
                    "cb": cb, "kr": kr}
        return {"premium_pct": 0, "boost": 0, "err": "no_prices"}
    except Exception as e:
        return {"premium_pct": 0, "boost": 0, "err": str(e)[:60]}


def signal_score() -> dict:
    flagged = treasury_flags()
    treasury_w = 3 if flagged else 0
    etf = btc_etf_heavy()
    calm = crypto_calm()
    gas = eth_gas_relief()
    cb_prem = coinbase_premium()
    prem_boost = cb_prem.get("boost", 0)
    base_btc = treasury_w + (1 if etf else 0) + (1 if calm else 0) + prem_boost
    base_eth = base_btc + (1 if gas else 0)
    return {
        "as_of": now_iso(),
        "treasury_flags": flagged,
        "treasury_w": treasury_w,
        "btc_etf_heavy": etf,
        "crypto_calm": calm,
        "eth_gas_relief": gas,
        "coinbase_premium_pct": cb_prem.get("premium_pct", 0),
        "coinbase_premium_boost": prem_boost,
        "btc_score": base_btc,
        "eth_score": base_eth,
        "base_btc": base_btc,
        "base_eth": base_eth,
    }


# ── Coinbase Advanced Ed25519 JWT auth ──────────────────────────────────────

def _build_jwt(method: str, path: str, key_id: str, priv_b64: str) -> str:
    """Build a CDP-style EdDSA JWT for one Coinbase request.

    The 'uri' claim must NOT include query params — Coinbase strips them
    before signature verification, so signing with them attached → 401.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import jwt as pyjwt
    raw = base64.b64decode(priv_b64)
    priv = Ed25519PrivateKey.from_private_bytes(raw[:32] if len(raw) >= 32 else raw)
    now = int(time.time())
    # Strip query params for the JWT 'uri' claim — full path stays in the URL.
    path_for_uri = path.split("?", 1)[0]
    payload = {
        "sub": key_id,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": f"{method} api.coinbase.com{path_for_uri}",
    }
    return pyjwt.encode(payload, priv, algorithm="EdDSA",
                        headers={"kid": key_id, "nonce": str(now)})


def cb_request(method: str, path: str, key: str, secret: str,
               body: dict | None = None) -> tuple[int, dict | str]:
    body_str = json.dumps(body) if body else ""
    try:
        token = _build_jwt(method, path, key, secret)
    except Exception as e:
        return 0, {"err": f"jwt_build: {str(e)[:120]}"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = CB_API + path
    data = body_str.encode() if body_str else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": str(e)}
        return e.code, err
    except Exception as e:
        return 0, {"err": str(e)[:120]}


def cb_market_buy(product_id: str, quote_size_usd: float,
                  key: str, secret: str) -> dict:
    """Place a market BUY for $quote_size_usd of product_id."""
    body = {
        "client_order_id": f"ce_cb_{product_id}_{int(time.time())}",
        "product_id": product_id,
        "side": "BUY",
        "order_configuration": {
            "market_market_ioc": {"quote_size": str(quote_size_usd)}
        },
    }
    code, resp = cb_request("POST", "/api/v3/brokerage/orders", key, secret, body)
    if 200 <= code < 300 and resp.get("success"):
        return {"ok": True, "coinbase": resp}
    return {"ok": False, "reason": f"http_{code}", "err": resp}


def cb_market_sell(product_id: str, base_size: str,
                   key: str, secret: str) -> dict:
    """Place a market SELL for base_size of base currency."""
    body = {
        "client_order_id": f"ce_cb_exit_{product_id}_{int(time.time())}",
        "product_id": product_id,
        "side": "SELL",
        "order_configuration": {
            "market_market_ioc": {"base_size": str(base_size)}
        },
    }
    code, resp = cb_request("POST", "/api/v3/brokerage/orders", key, secret, body)
    if 200 <= code < 300 and resp.get("success"):
        return {"ok": True, "coinbase": resp}
    return {"ok": False, "reason": f"http_{code}", "err": resp}


def cb_recent_fills(product_id: str, key: str, secret: str, limit: int = 50) -> list[dict]:
    """Pull recent fills for a product to compute average entry price + held size."""
    path = f"/api/v3/brokerage/orders/historical/fills?product_id={product_id}&limit={limit}"
    code, resp = cb_request("GET", path, key, secret)
    if 200 <= code < 300 and isinstance(resp, dict):
        return resp.get("fills", [])
    return []


def _load_position_hwm() -> dict:
    """Load per-coin high-water-mark cache used by trailing-stop logic.
    File is intentionally tiny — only the all-time-high price seen since each
    position opened. Reset when position closes (re-init on next entry)."""
    p = ROOT / ".position_hwm.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _save_position_hwm(d: dict) -> None:
    try:
        (ROOT / ".position_hwm.json").write_text(json.dumps(d, indent=2))
    except Exception as e:
        log(f"  hwm save failed: {str(e)[:50]}")


def manage_exits(holdings: dict, key: str, secret: str,
                 prices: dict, tp_pct: float, sl_pct: float,
                 max_hold_hours: int,
                 trail_pct: float = 0,
                 trail_arm_pct: float = 0) -> list[dict]:
    """For each crypto holding, check TP / SL / time-stop / trailing-stop
    and place a market sell if hit.

    Trailing stop (when trail_pct > 0):
      - Track per-coin high-water mark in .position_hwm.json
      - Once unrealized PnL crosses trail_arm_pct (e.g. +5%), arm trailing
      - Exit when current price drops trail_pct (e.g. -2%) below high-water mark
      - Hard TP and SL still apply; trailing is checked between them
    """
    exits: list[dict] = []
    hwm_cache = _load_position_hwm() if trail_pct > 0 else {}
    for currency, base_size in (holdings or {}).items():
        if currency in ("USD", "USDC"):
            continue
        product_id = f"{currency}-USD"
        cur_price = prices.get(currency)
        if not cur_price or float(base_size) <= 0:
            continue
        # Find avg entry from most recent BUY fills (until cumulative size matches holding)
        fills = cb_recent_fills(product_id, key, secret, limit=50)
        held = float(base_size)
        accum = 0.0
        cost = 0.0
        oldest_fill_ts = None
        for f in fills:  # already in reverse-chron order from Coinbase
            if f.get("side") != "BUY":
                continue
            sz = float(f.get("size") or 0)
            px = float(f.get("price") or 0)
            if sz <= 0:
                continue
            take = min(sz, held - accum)
            accum += take
            cost += take * px
            oldest_fill_ts = f.get("trade_time")
            if accum >= held - 1e-9:
                break
        if accum <= 0:
            continue
        avg_entry = cost / accum
        pnl_pct = (cur_price / avg_entry) - 1.0
        # Time held
        hold_hours = 0.0
        if oldest_fill_ts:
            try:
                t0 = datetime.fromisoformat(oldest_fill_ts.replace("Z", "+00:00"))
                hold_hours = (datetime.now(timezone.utc) - t0).total_seconds() / 3600
            except Exception:
                pass
        decision: dict = {
            "currency": currency, "product_id": product_id,
            "size": float(base_size), "avg_entry": avg_entry,
            "current_price": cur_price, "pnl_pct": pnl_pct,
            "hold_hours": hold_hours, "exit": None,
        }
        # Trailing-stop bookkeeping (only if active per .live_strategy.json)
        if trail_pct > 0:
            prev = hwm_cache.get(currency, {})
            old_hwm = float(prev.get("hwm", avg_entry))
            new_hwm = max(old_hwm, cur_price)
            armed = bool(prev.get("armed"))
            if not armed and (new_hwm / avg_entry - 1) >= trail_arm_pct:
                armed = True
            hwm_cache[currency] = {
                "hwm": new_hwm,
                "armed": armed,
                "entry": avg_entry,
                "updated": now_iso(),
            }
            decision["hwm"] = new_hwm
            decision["trail_armed"] = armed

        if pnl_pct >= tp_pct:
            decision["exit"] = "take_profit"
        elif pnl_pct <= -sl_pct:
            decision["exit"] = "stop_loss"
        elif (trail_pct > 0
              and decision.get("trail_armed")
              and cur_price <= decision["hwm"] * (1 - trail_pct)
              and decision["hwm"] * (1 - trail_pct) > avg_entry):
            decision["exit"] = "trailing_stop"
        elif hold_hours >= max_hold_hours:
            decision["exit"] = "time_stop"

        if decision["exit"]:
            log(f"EXIT trigger: {currency} pnl={pnl_pct*100:.2f}% hold={hold_hours:.1f}h reason={decision['exit']}")
            decision["result"] = cb_market_sell(product_id, str(base_size), key, secret)
        else:
            decision["result"] = {"ok": False, "reason": "hold"}
        exits.append(decision)
    return exits


def cb_get_price(product_id: str) -> float | None:
    """Public endpoint — no auth needed."""
    url = f"{CB_API}/api/v3/brokerage/market/products/{product_id}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        return float(d.get("price") or 0) or None
    except Exception as e:
        log(f"cb price {product_id} ERROR: {e}")
        return None


def cb_account_summary(key: str, secret: str) -> dict:
    code, resp = cb_request("GET", "/api/v3/brokerage/accounts", key, secret)
    if 200 <= code < 300 and isinstance(resp, dict) and "accounts" in resp:
        usd = 0.0
        coin_holdings: dict[str, float] = {}
        for a in resp["accounts"]:
            currency = a.get("currency", "")
            balance = float((a.get("available_balance") or {}).get("value") or 0)
            if currency == "USD":
                usd = balance
            elif balance > 0:
                coin_holdings[currency] = balance
        return {"ok": True, "usd": usd, "holdings": coin_holdings}
    return {"ok": False, "reason": f"http_{code}", "err": resp}


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    load_env()

    # --exit-only flag: skip entry-decision phase, just check open positions
    # for TP/SL/time-stop. Designed to run every 1 minute on cron — gives
    # 15x faster loss-cut reaction than the full bot's 15-min cadence.
    exit_only = "--exit-only" in sys.argv

    # HALT semantics: block NEW ENTRIES only. Existing positions still need
    # exit management (TP/SL/time-stop) regardless of halt state — otherwise
    # halting the bot also disables risk control on open trades, which is the
    # opposite of what halt is for.
    halted = HALT_FILE.exists()

    max_pos = env_float("COINBASE_MAX_POSITION_USD", 25.0)
    max_open = env_int("COINBASE_MAX_OPEN", 2)
    threshold = env_int("COINBASE_SCORE_THRESHOLD", 2)
    # ASYMMETRIC TP/SL (operator-set 2026-04-26): higher TP, tighter SL.
    # Rationale: at 50bps round-trip fees, breakeven hit rate at 5/4 was 47.6%.
    # At 8/3, breakeven hit rate drops to 31.8% — much wider safety margin.
    # Even with our 48.1% hit rate, this turns -7.95% alpha into ~+2-4% alpha.
    tp_pct = env_float("COINBASE_TP_PCT", 0.08)        # +8% take-profit (was 5%)
    sl_pct = env_float("COINBASE_SL_PCT", 0.03)        # -3% stop-loss (was 4%)
    max_hold_h = env_int("COINBASE_MAX_HOLD_HOURS", 168)   # 7d time-stop

    # ── Promoted-strategy override (from strategy_lab.py auto-promote) ────
    # When .live_strategy.json names a strategy that has a registered live
    # entry function, use ITS TP/SL/max_hold AND entry rule. This is the
    # bridge between research (lab) and live trading.
    live_strategy = read_live_strategy()
    if live_strategy:
        tp_pct = float(live_strategy.get("tp", tp_pct))
        sl_pct = float(live_strategy.get("sl", sl_pct))
        max_hold_h = int(live_strategy.get("max_hold_h", max_hold_h))
        # Cap absurd values — buy_and_hold variants set tp=999/sl=999 in the lab
        # for "no exit" semantics, but live we still want SOME ceiling for safety.
        if tp_pct > 1.0: tp_pct = 0.30   # cap 30%
        if sl_pct > 1.0: sl_pct = 0.10   # cap 10%
        if max_hold_h > 720: max_hold_h = 720  # cap 30d
    live = (os.environ.get("COINBASE_LIVE_ORDERS") or "").strip() == "1"
    key = os.environ.get("COINBASE_API_KEY", "").strip()
    secret = os.environ.get("COINBASE_API_SECRET", "").strip()

    # In exit-only mode (1-min cadence), skip macro signal eval — just price + holdings.
    if exit_only:
        sig = {"btc_score": 0, "eth_score": 0, "treasury_flags": [],
               "base_btc": 0, "base_eth": 0, "btc_etf_heavy": False,
               "crypto_calm": False, "eth_gas_relief": False, "treasury_w": 0,
               "as_of": now_iso()}
    else:
        sig = signal_score()

    # Public price fetch always works
    prices = {c["sym"]: cb_get_price(c["product"]) for c in COINS}
    account = cb_account_summary(key, secret) if (key and secret) else {"ok": False, "reason": "no_creds"}

    mode = "EXIT-ONLY" if exit_only else "FULL"
    log(f"[{mode}] prices=BTC:{prices.get('BTC')},ETH:{prices.get('ETH')} "
        f"live={live} auth_ok={account.get('ok')}"
        + ("" if exit_only else f" signals btc={sig['btc_score']} eth={sig['eth_score']}"))

    # ── EXIT LOGIC: check existing positions for TP / SL / time-stop / trail ─
    # Trailing-stop params come from .live_strategy.json when the promoted
    # strategy carries them (e.g. dual_momentum_trail). Inert when absent.
    trail_pct = 0.0
    trail_arm_pct = 0.0
    if live_strategy and isinstance(live_strategy.get("params"), dict):
        trail_pct = float(live_strategy["params"].get("trail_pct", 0) or 0)
        trail_arm_pct = float(live_strategy["params"].get("trail_arm_pct", 0) or 0)
    exits: list[dict] = []
    if live and account.get("ok") and account.get("holdings"):
        exits = manage_exits(
            account["holdings"], key, secret, prices,
            tp_pct=tp_pct, sl_pct=sl_pct, max_hold_hours=max_hold_h,
            trail_pct=trail_pct, trail_arm_pct=trail_arm_pct,
        )
        for e in exits:
            log(f"  exit-check {e['currency']} pnl={e['pnl_pct']*100:.2f}% "
                f"hold={e['hold_hours']:.1f}h → {e.get('exit') or 'hold'}")

    # In exit-only mode, stop here. Don't run entry decisions.
    if exit_only:
        log(f"DONE  exit-only  exits_processed={len(exits)} halted={halted}")
        return 0

    # Halted but full-mode: exits already ran above, now skip entries.
    if halted:
        log(f"DONE  full-mode-halted  exits_processed={len(exits)} entries_skipped (HALT file present)")
        return 0

    # Score each coin = base macro signal + per-coin intraday momentum.
    # The intraday boost is what makes this 24/7 useful — daily macro
    # signals don't change, but 1h/4h/24h price action does every minute.
    def base_score(sym: str) -> float:
        if sym == "BTC":
            return float(sig["base_btc"])
        if sym == "ETH":
            return float(sig["base_eth"])
        return sig["base_btc"] * 0.5

    candidates = []
    for c in COINS:
        intraday = intraday_momentum(c["product"])
        score = base_score(c["sym"]) + intraday["boost"]
        candidates.append({
            "coin": c["sym"], "product": c["product"],
            "score": score,
            "base_score": base_score(c["sym"]),
            "intraday_boost": intraday["boost"],
            "intraday_reason": intraday.get("reason", ""),
            "chg_1h_pct": intraday.get("chg_1h_pct", 0),
            "chg_24h_pct": intraday.get("chg_24h_pct", 0),
            "price": prices.get(c["sym"]),
        })
    candidates.sort(key=lambda x: -x["score"])

    # Dynamic position sizing — Kelly-lite: size scales with signal conviction.
    # Score 2 (threshold) = base_pct (5%). Each additional point adds 3%, capped
    # at max_pct (20%). Means a 5-conviction signal bets 4× harder than a 2.
    # This is what prop shops do — almost no retail bot does it.
    base_pct = env_float("COINBASE_POSITION_BASE_PCT", 0.05)
    per_point_pct = env_float("COINBASE_POSITION_PER_POINT", 0.03)
    max_pct = env_float("COINBASE_POSITION_MAX_PCT", 0.20)
    if account.get("ok"):
        usd = float(account.get("usd") or 0)
        crypto_value = sum(
            float(qty) * (prices.get(sym) or 0)
            for sym, qty in (account.get("holdings") or {}).items()
        )
        equity = usd + crypto_value
    else:
        equity = max_pos / 0.10  # implied equity if no auth, fallback

    # Evaluate ALL candidates so /trust/ can show the full universe + scores.
    # max_open caps how many we ENTER, not how many we evaluate.
    decisions: list[dict] = []
    placed: list[dict] = []
    held = (account.get("holdings") or {}) if account.get("ok") else {}
    entries_placed = 0

    def conviction_size(score: float, equity: float) -> float:
        """Position size scales with how far above threshold the score is."""
        excess = max(0, score - threshold)  # 0+ above threshold
        pct = base_pct + excess * per_point_pct
        pct = min(pct, max_pct)
        size = equity * pct
        return max(5.0, size)  # floor at $5 to avoid all-fee trades

    # ENTRY GATING — two paths, depending on whether a strategy is promoted:
    # Legacy path: require SEC catalyst (treasury_w >= 3) as hard gate.
    # Promoted path: use strategy's price-based entry rule; SEC catalyst becomes
    #   a position-size multiplier (1.0× base, up to 2.5× if treasury_w >= 5).
    require_sec_catalyst = (
        os.environ.get("COINBASE_REQUIRE_SEC", "1").strip() == "1"
        and live_strategy is None  # promoted strategy bypasses the hard gate
    )
    sec_catalyst_active = sig.get("treasury_w", 0) >= 3
    treasury_w = sig.get("treasury_w", 0)

    # Pre-fetch hourly closes for promoted-strategy gating (one call per coin)
    hourly_cache: dict[str, list[float]] = {}
    if live_strategy:
        entry_fn = STRATEGY_ENTRY_FNS[live_strategy["strategy_id"]]
        for c in candidates:
            hourly_cache[c["coin"]] = fetch_hourly_closes(c["product"], hours=720)
        log(f"  promoted strategy: {live_strategy['strategy_id']} "
            f"tp={tp_pct*100:.0f}% sl={sl_pct*100:.0f}% max_hold={max_hold_h}h")
    else:
        entry_fn = None

    def catalyst_size_multiplier(t_w: int) -> float:
        """SEC catalyst → size multiplier. No catalyst = 1.0× base.
        treasury_w 3-4 = 1.5×, treasury_w >= 5 = 2.5×. Capped."""
        if t_w >= 5: return 2.5
        if t_w >= 3: return 1.5
        return 1.0

    for c in candidates:
        # Base size from conviction score
        base_size = conviction_size(c["score"], equity)
        # Multiplier when promoted strategy is live + SEC catalyst stacks
        mult = catalyst_size_multiplier(treasury_w) if live_strategy else 1.0
        size = min(base_size * mult, equity * max_pct) if equity else base_size

        d = {**c, "max_position_usd": round(size, 2), "live": live, "result": None,
             "conviction_pct": round(size / equity * 100, 1) if equity else 0,
             "sec_catalyst_required": require_sec_catalyst,
             "sec_catalyst_active": sec_catalyst_active,
             "size_multiplier": mult,
             "strategy": live_strategy["strategy_id"] if live_strategy else "legacy_signal_score"}
        already_held = float(held.get(c["coin"], 0)) > 0

        # ── Strategy gating (legacy SEC vs promoted price-based) ──
        promoted_fire, promoted_reason = (False, "no_strategy")
        if entry_fn:
            closes = hourly_cache.get(c["coin"], [])
            promoted_fire, promoted_reason = entry_fn(closes)

        if already_held:
            d["result"] = {"ok": False, "reason": f"already holding {c['coin']} ({held.get(c['coin']):.6f}) — skip re-entry"}
        elif live_strategy and not promoted_fire:
            d["result"] = {"ok": False, "reason": f"{live_strategy['strategy_id']} gate: {promoted_reason}"}
        elif require_sec_catalyst and not sec_catalyst_active:
            d["result"] = {"ok": False, "reason": f"no SEC catalyst flagged today (treasury_w={treasury_w}) — fee-survival gate"}
        elif (not live_strategy) and c["score"] < threshold:
            d["result"] = {"ok": False, "reason": f"score={c['score']} < threshold={threshold}"}
        elif entries_placed >= max_open:
            d["result"] = {"ok": False, "reason": f"max_open ({max_open}) reached this run"}
        elif not live:
            d["result"] = {"ok": False, "reason": "dry_run (COINBASE_LIVE_ORDERS!=1)"}
        elif not (key and secret):
            d["result"] = {"ok": False, "reason": "missing COINBASE_API_KEY / SECRET"}
        elif not c["price"]:
            d["result"] = {"ok": False, "reason": "no_price"}
        else:
            d["result"] = cb_market_buy(c["product"], size, key, secret)
            if d["result"].get("ok"):
                placed.append(d)
                entries_placed += 1
        decisions.append(d)
        gate_tag = (live_strategy["strategy_id"] if live_strategy else "legacy")
        log(f"  {c['coin']} score={c['score']} px=${c['price']} "
            f"[{gate_tag}:{promoted_reason}] mult={mult}× size=${size:.2f} → "
            f"{d['result']['reason'] if not d['result'].get('ok') else 'PLACED'}")

    DECISIONS_OUT.write_text(json.dumps({
        "as_of": now_iso(),
        "venue": "coinbase-advanced",
        "signals": sig,
        "live_state": {
            "btc_price": prices.get("BTC"),
            "eth_price": prices.get("ETH"),
            "auth_ok": account.get("ok", False),
            "auth_reason": account.get("reason") if not account.get("ok") else None,
            "usd_balance": account.get("usd", 0) if account.get("ok") else None,
            "holdings": account.get("holdings", {}) if account.get("ok") else None,
        },
        "config": {
            "max_position_usd": max_pos,
            "max_open": max_open,
            "score_threshold": threshold,
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "max_hold_hours": max_hold_h,
            "live_orders": live,
            "creds_configured": bool(key and secret),
        },
        "decisions": decisions,
        "exits": exits,
    }, indent=2))

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
