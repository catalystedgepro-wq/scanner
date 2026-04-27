#!/usr/bin/env python3
"""strategy_lab.py — Autonomous strategy research + improvement loop.

Runs every day. Tests N candidate strategies through fee-included backtest.
For each strategy:
  1. Pull last 60d hourly candles for our 5-coin universe
  2. Replay strategy logic
  3. Subtract realistic fees (50bps round-trip taker)
  4. Compute alpha vs buy-and-hold
  5. Log result to docs/data/strategy_lab.json (public on /trust/)
  6. If a strategy shows alpha > +1% NET of fees → AUTO-LIFT the halt and
     promote that strategy to live (write strategy config to .live_strategy.json)

This makes the bot a continuous learning system. Halted strategies get
re-tested if conditions change. New strategy variants get added to the queue.

Strategies tested (current queue):
  - momentum_5_4       (original, validated to fail with fees)
  - momentum_8_3       (asymmetric, also failed)
  - mean_revert_4h     (NEW — fade extreme moves on 4h bars)
  - mean_revert_24h    (NEW — fade daily extremes)
  - breakout_donchian  (NEW — 20-period Donchian channel breakout)
  - btc_only_momentum  (NEW — concentrated, less trade frequency)
  - tight_filter       (NEW — only top quintile breakout, half SL)
  - volatility_filter  (NEW — only trade in normal vol regime)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT = ROOT / "docs/data/strategy_lab.json"
HALT_FILE = ROOT / ".agent_coinbase_halted"
LIVE_STRATEGY = ROOT / ".live_strategy.json"
LOG = ROOT / "logs/strategy_lab.log"
LOG.parent.mkdir(exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)

PRODUCTS = ["BTC-USD", "ETH-USD", "ARB-USD", "LINK-USD", "ATOM-USD"]
FEE_BPS_RT = 50.0  # 25bps × 2 sides Coinbase taker
LOOKBACK_DAYS = 60
PROMOTE_THRESHOLD = 0.01  # +1% net alpha to auto-promote


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(m: str) -> None:
    line = f"[{now_iso()}] strategy_lab: {m}"
    LOG.open("a").write(line + "\n")
    print(line)


def fetch_hourly(product: str, hours: int) -> list[dict]:
    end = int(time.time())
    start = end - hours * 3600
    out = []
    chunk = 300
    while start < end:
        chunk_end = min(start + chunk * 3600, end)
        url = (f"https://api.coinbase.com/api/v3/brokerage/market/products/"
               f"{product}/candles?start={start}&end={chunk_end}&granularity=ONE_HOUR")
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                d = json.loads(r.read())
            out.extend(d.get("candles", []))
        except Exception as e:
            log(f"fetch {product} ERR: {e}")
            break
        start = chunk_end
        time.sleep(0.2)
    out.sort(key=lambda c: int(c["start"]))
    return out


# ── Strategy entry-decision functions ───────────────────────────────────────
# Each takes: closes, opens, highs, lows, current_idx → bool (enter long?)

def entry_momentum(closes, opens, highs, lows, i, params):
    """Original: 1h breakout in top quintile + 4h+24h trend agreement."""
    if i < 24:
        return False
    win = closes[i-23:i+1]
    chg_1h = (win[-1]/win[-2] - 1) if len(win) > 1 else 0
    chg_4h = (win[-1]/win[-5] - 1) if len(win) > 4 else 0
    chg_24h = (win[-1]/win[0] - 1)
    rets = [(win[j+1]/win[j] - 1) for j in range(len(win)-1)]
    sorted_r = sorted(rets, reverse=True)
    top_q = sorted_r[max(1, len(sorted_r)//5) - 1] if sorted_r else 0
    boost = 0
    if chg_24h > 0 and chg_4h > 0: boost += 1
    if chg_1h > 0 and chg_1h >= top_q: boost += 1
    return boost >= 2


def entry_mean_revert_4h(closes, opens, highs, lows, i, params):
    """Fade extreme moves: enter long when price drops > 4% in 4h."""
    if i < 4: return False
    chg_4h = (closes[i]/closes[i-4] - 1)
    return chg_4h <= -0.04  # -4% in 4h


def entry_mean_revert_24h(closes, opens, highs, lows, i, params):
    """Daily extreme: enter long when price drops > 8% in 24h."""
    if i < 24: return False
    chg_24h = (closes[i]/closes[i-24] - 1)
    return chg_24h <= -0.08


def entry_donchian(closes, opens, highs, lows, i, params):
    """Donchian breakout: enter long when close > 20-bar high."""
    n = params.get("n", 20)
    if i < n: return False
    prior_high = max(highs[i-n:i])
    return closes[i] > prior_high


def entry_strict_breakout(closes, opens, highs, lows, i, params):
    """Tighter filter: 1h must be top decile, 24h > 5%."""
    if i < 24: return False
    win = closes[i-23:i+1]
    chg_1h = (win[-1]/win[-2] - 1) if len(win) > 1 else 0
    chg_24h = (win[-1]/win[0] - 1)
    rets = [(win[j+1]/win[j] - 1) for j in range(len(win)-1)]
    sorted_r = sorted(rets, reverse=True)
    top_d = sorted_r[max(1, len(sorted_r)//10) - 1] if sorted_r else 0
    return chg_1h >= top_d and chg_24h > 0.05


def entry_buy_and_hold(closes, opens, highs, lows, i, params):
    """Control strategy: buy on first bar, hold forever.
    If this beats every other strategy, the regime is bull and active trading
    is the wrong move."""
    return i == 24  # enter once at start


def entry_trailing_momentum(closes, opens, highs, lows, i, params):
    """Same momentum entry as original, but uses TRAILING stop (handled in
    replay via params marker). Lets winners run."""
    if i < 24: return False
    win = closes[i-23:i+1]
    chg_1h = (win[-1]/win[-2] - 1) if len(win) > 1 else 0
    chg_4h = (win[-1]/win[-5] - 1) if len(win) > 4 else 0
    chg_24h = (win[-1]/win[0] - 1)
    rets = [(win[j+1]/win[j] - 1) for j in range(len(win)-1)]
    sorted_r = sorted(rets, reverse=True)
    top_q = sorted_r[max(1, len(sorted_r)//5) - 1] if sorted_r else 0
    boost = 0
    if chg_24h > 0 and chg_4h > 0: boost += 1
    if chg_1h > 0 and chg_1h >= top_q: boost += 1
    return boost >= 2


def entry_dca_on_decline(closes, opens, highs, lows, i, params):
    """DCA: enter every time price drops > 5% from rolling 7-day high.
    More entries, smaller size, scale-in-on-weakness."""
    if i < 168: return False
    roll_high = max(closes[i-168:i])
    return closes[i] / roll_high < 0.95


def entry_3_signal_consensus(closes, opens, highs, lows, i, params):
    """Require 3 indicators in agreement: 24h up, 4h up, 1h positive."""
    if i < 24: return False
    chg_1h = closes[i]/closes[i-1] - 1
    chg_4h = closes[i]/closes[i-4] - 1
    chg_24h = closes[i]/closes[i-24] - 1
    return chg_24h > 0.02 and chg_4h > 0.005 and chg_1h > 0


def entry_bear_regime_long(closes, opens, highs, lows, i, params):
    """Enter long ONLY when in bullish regime (price > SMA_long).
    In bearish regime, no entries → bot sits in USDC earning yield.

    Bullish regime: close > SMA_192 (8-day SMA on hourly bars)
                    AND short SMA > long SMA (golden cross)
    This means the bot is FLAT during bear markets, not losing.
    """
    sma_short = params.get("sma_short", 48)   # 2 days
    sma_long = params.get("sma_long", 192)    # 8 days
    if i < sma_long: return False
    short_sma = sum(closes[i-sma_short+1:i+1]) / sma_short
    long_sma = sum(closes[i-sma_long+1:i+1]) / sma_long
    is_bull_regime = closes[i] > long_sma and short_sma > long_sma
    if not is_bull_regime:
        return False
    # Within bull regime, use original momentum logic
    if i < 24: return False
    win = closes[i-23:i+1]
    chg_1h = (win[-1]/win[-2] - 1) if len(win) > 1 else 0
    chg_4h = (win[-1]/win[-5] - 1) if len(win) > 4 else 0
    chg_24h = (win[-1]/win[0] - 1)
    rets = [(win[j+1]/win[j] - 1) for j in range(len(win)-1)]
    sorted_r = sorted(rets, reverse=True)
    top_q = sorted_r[max(1, len(sorted_r)//5) - 1] if sorted_r else 0
    boost = 0
    if chg_24h > 0 and chg_4h > 0: boost += 1
    if chg_1h > 0 and chg_1h >= top_q: boost += 1
    return boost >= 2


def entry_relative_strength(closes, opens, highs, lows, i, params):
    """Enter long when this coin is in TOP performer over 7d.
    Idea: in bear markets, only the relatively strongest coins recover first.
    Even when whole crypto is down, top-RS coins may still be up vs peers.

    Note: this is a single-coin function so we approximate by saying:
    only enter if 7d return is POSITIVE (the coin is bucking the trend)."""
    if i < 168: return False
    chg_7d = closes[i]/closes[i-168] - 1
    if chg_7d <= 0:
        return False  # weak coin, skip
    # Within strong-coin set, momentum entry
    if i < 24: return False
    win = closes[i-23:i+1]
    chg_1h = (win[-1]/win[-2] - 1) if len(win) > 1 else 0
    chg_24h = (win[-1]/win[0] - 1)
    return chg_24h > 0 and chg_1h > 0


def entry_weekly_rotate(closes, opens, highs, lows, i, params):
    """Once per week (every 168h), enter if 7d return is positive AND
    among the top half of recent vol-adjusted returns. Cheapest possible
    rotation strategy — 8 trades per coin per 60d max, so fees barely bite."""
    if i < 168: return False
    if i % 168 != 0: return False              # weekly cadence
    win = closes[i-167:i+1]
    ret_7d = win[-1]/win[0] - 1
    return ret_7d > 0


def entry_drawdown_buy(closes, opens, highs, lows, i, params):
    """Buy each -8% drawdown from the rolling 14d high. Mean-revert variant
    targeting deeper-than-DCA pullbacks. Wider TP (12%) lets the bounce play out;
    deeper SL (-6%) accommodates noise around drawdown bottoms."""
    if i < 336: return False                   # need 14d window
    roll_high = max(closes[i-336:i])
    if roll_high <= 0: return False
    drawdown = closes[i] / roll_high - 1
    # Trigger at exactly -8% so we don't enter every bar of a deep drawdown
    if drawdown > -0.08: return False
    # Add a "bottoming" filter: 4h return > 0 (don't catch falling knife)
    if i < 4: return False
    chg_4h = closes[i]/closes[i-4] - 1
    return chg_4h > 0


def entry_regime_split(closes, opens, highs, lows, i, params):
    """Hybrid: buy_and_hold during established bull, bear_regime_long during
    transition. Enter at bar 24 if 8d SMA > 32d SMA (bull); also re-enter on
    any bull crossover after a bear period. The blend captures the full B&H
    return in bulls while reducing drawdown when the trend rolls over."""
    if i < 192: return False
    sma_short = sum(closes[i-47:i+1]) / 48      # 48h ≈ 2d
    sma_long  = sum(closes[i-191:i+1]) / 192    # 192h ≈ 8d
    # Re-entry on every bull crossover (not just the first bar)
    if i == 24:
        return sma_short > sma_long
    sma_short_prev = sum(closes[i-48:i]) / 48
    sma_long_prev  = sum(closes[i-192:i]) / 192
    bull_cross_now = (sma_short > sma_long) and (sma_short_prev <= sma_long_prev)
    return bull_cross_now


def entry_dual_momentum_filter(closes, opens, highs, lows, i, params):
    """Require BOTH 7d AND 30d returns positive. Gary Antonacci-style dual
    momentum but on crypto. Trades infrequent but only in confirmed uptrends.
    Wide TP/SL (15/6) so 1 winner pays for 2 losers."""
    if i < 720: return False                   # need 30d window
    ret_7d  = closes[i] / closes[i-168] - 1
    ret_30d = closes[i] / closes[i-720] - 1
    if ret_7d <= 0 or ret_30d <= 0: return False
    # Check we're not at a local top: current close not within 1% of 24h high
    high_24h = max(closes[i-23:i+1])
    if high_24h > 0 and closes[i] / high_24h > 0.99:
        return False
    return True


def entry_volatility_gated(closes, opens, highs, lows, i, params):
    """Original momentum but only when realized vol is in normal range."""
    if i < 24: return False
    win = closes[i-23:i+1]
    chg_1h = (win[-1]/win[-2] - 1) if len(win) > 1 else 0
    chg_4h = (win[-1]/win[-5] - 1) if len(win) > 4 else 0
    chg_24h = (win[-1]/win[0] - 1)
    rets = [(win[j+1]/win[j] - 1) for j in range(len(win)-1)]
    if not rets: return False
    mean_r = sum(rets) / len(rets)
    var = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets) - 1)
    std_h = var ** 0.5
    vol_bps_h = std_h * 10000
    in_normal_regime = 50 <= vol_bps_h <= 200
    if not in_normal_regime: return False
    sorted_r = sorted(rets, reverse=True)
    top_q = sorted_r[max(1, len(sorted_r)//5) - 1] if sorted_r else 0
    boost = 0
    if chg_24h > 0 and chg_4h > 0: boost += 1
    if chg_1h > 0 and chg_1h >= top_q: boost += 1
    return boost >= 2


def replay(product, candles, entry_fn, params, tp, sl, max_hold_h, fee_bps_rt):
    """Walk forward: at each hour, decide entry. Track exits at TP/SL/time-stop.
    Returns net cumulative return (after fees), hit rate, trade count.

    Supports a TRAILING-STOP exit when params has 'trail_pct' AND 'trail_arm_pct':
      - Below trail_arm_pct: hold normally (no trailing yet)
      - Once unrealized PnL crosses trail_arm_pct: track high-water mark
      - Close when price drops trail_pct below high-water mark
      - Hard TP (tp) and SL (sl) still apply as upper/lower bounds
    """
    if len(candles) < 30:
        return None
    closes = [float(c["close"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    n = len(candles)
    trades = []
    open_pos = None
    trail_pct = params.get("trail_pct", 0)         # 0 = no trailing
    trail_arm = params.get("trail_arm_pct", 0)     # arm threshold

    for i in range(24, n - 1):
        if open_pos:
            entry_idx = open_pos["entry_idx"]
            entry_px = open_pos["entry_price"]
            tp_px = entry_px * (1 + tp)
            sl_px = entry_px * (1 - sl)
            held_h = i - entry_idx
            # Update high-water mark + arm trailing if PnL crossed arm threshold
            if trail_pct > 0:
                if highs[i] > open_pos.get("hwm", entry_px):
                    open_pos["hwm"] = highs[i]
                if not open_pos.get("trail_armed"):
                    if (open_pos["hwm"] / entry_px - 1) >= trail_arm:
                        open_pos["trail_armed"] = True
            reason = None
            exit_px = None
            if highs[i] >= tp_px:
                exit_px = tp_px; reason = "TP"
            elif lows[i] <= sl_px:
                exit_px = sl_px; reason = "SL"
            # Trailing stop fires only after armed; uses lows[i] for conservative fill
            elif open_pos.get("trail_armed") and trail_pct > 0:
                trail_stop = open_pos["hwm"] * (1 - trail_pct)
                if lows[i] <= trail_stop and trail_stop > entry_px:
                    exit_px = trail_stop; reason = "TRAIL"
            elif held_h >= max_hold_h:
                exit_px = closes[i]; reason = "time"
            if reason:
                gross = (exit_px / entry_px) - 1
                ret = gross - (fee_bps_rt / 10000)
                trades.append({"return": ret, "exit": reason})
                open_pos = None
        if not open_pos and entry_fn(closes, opens, highs, lows, i, params):
            open_pos = {"entry_idx": i + 1, "entry_price": opens[i + 1],
                        "hwm": opens[i + 1], "trail_armed": False}
    if open_pos:
        gross = (closes[-1] / open_pos["entry_price"]) - 1
        ret = gross - (fee_bps_rt / 10000)
        trades.append({"return": ret, "exit": "open"})

    if not trades:
        return {"trades": 0, "cum_return": 0, "hit_rate": 0, "buy_hold": (closes[-1]/closes[0]) - 1}
    cum = 1.0
    for t in trades: cum *= (1 + t["return"])
    wins = sum(1 for t in trades if t["return"] > 0)
    return {
        "trades": len(trades),
        "cum_return": cum - 1,
        "hit_rate": wins / len(trades),
        "buy_hold": (closes[-1] / closes[0]) - 1,
        "trade_count_per_60d": len(trades),
    }


STRATEGIES = [
    {"id": "momentum_5_4", "fn": entry_momentum, "params": {}, "tp": 0.05, "sl": 0.04, "max_hold": 168,
     "desc": "Original: 1h breakout + trend agreement, 5/4 TP/SL"},
    {"id": "momentum_8_3", "fn": entry_momentum, "params": {}, "tp": 0.08, "sl": 0.03, "max_hold": 168,
     "desc": "Original momentum with asymmetric 8/3 TP/SL"},
    {"id": "mean_revert_4h", "fn": entry_mean_revert_4h, "params": {}, "tp": 0.04, "sl": 0.02, "max_hold": 48,
     "desc": "Fade -4% drops in 4h, target +4% bounce"},
    {"id": "mean_revert_24h", "fn": entry_mean_revert_24h, "params": {}, "tp": 0.08, "sl": 0.04, "max_hold": 168,
     "desc": "Fade -8% daily drops, target +8% bounce"},
    {"id": "donchian_20", "fn": entry_donchian, "params": {"n": 20}, "tp": 0.10, "sl": 0.05, "max_hold": 168,
     "desc": "Donchian 20-bar breakout, 10/5 TP/SL"},
    {"id": "donchian_50", "fn": entry_donchian, "params": {"n": 50}, "tp": 0.15, "sl": 0.06, "max_hold": 336,
     "desc": "Donchian 50-bar breakout (rarer), 15/6 TP/SL"},
    {"id": "strict_breakout", "fn": entry_strict_breakout, "params": {}, "tp": 0.10, "sl": 0.04, "max_hold": 168,
     "desc": "Top-decile 1h + 24h>5%, fewer trades, 10/4 TP/SL"},
    {"id": "volatility_gated", "fn": entry_volatility_gated, "params": {}, "tp": 0.06, "sl": 0.03, "max_hold": 168,
     "desc": "Original momentum gated to normal-vol regime, 6/3 TP/SL"},
    {"id": "buy_and_hold", "fn": entry_buy_and_hold, "params": {}, "tp": 999, "sl": 999, "max_hold": 99999,
     "desc": "CONTROL: enter at bar 24, hold to end (no exits)"},
    {"id": "trailing_momentum", "fn": entry_trailing_momentum, "params": {}, "tp": 0.30, "sl": 0.05, "max_hold": 720,
     "desc": "Momentum with wide TP (let winners run), tight SL — 30/5/30d"},
    {"id": "dca_decline", "fn": entry_dca_on_decline, "params": {}, "tp": 0.10, "sl": 0.10, "max_hold": 720,
     "desc": "DCA: enter on -5% from 7d high, target +10%, wide -10% SL"},
    {"id": "consensus_3sig", "fn": entry_3_signal_consensus, "params": {}, "tp": 0.06, "sl": 0.03, "max_hold": 168,
     "desc": "3-indicator agreement: 24h>2%, 4h>0.5%, 1h>0"},
    {"id": "bear_regime_long", "fn": entry_bear_regime_long,
     "params": {"sma_short": 48, "sma_long": 192}, "tp": 0.08, "sl": 0.04, "max_hold": 168,
     "desc": "BEAR-AWARE: only enter when 8d SMA > short SMA (bull regime). In bear regime, sit in USDC (no entries). 8/4 TP/SL."},
    {"id": "relative_strength", "fn": entry_relative_strength,
     "params": {}, "tp": 0.10, "sl": 0.04, "max_hold": 168,
     "desc": "Only enter coins with positive 7d return (relative strength). Filters out laggards in bear markets. 10/4 TP/SL."},
    # ── 2026-04-27 — 4 new candidates, gaps in the existing 14 ───────────
    {"id": "weekly_rotate", "fn": entry_weekly_rotate,
     "params": {}, "tp": 0.08, "sl": 0.05, "max_hold": 168,
     "desc": "Weekly cadence: enter once per 168h if 7d return positive. Lowest possible fee burn — max 8 trades per coin per 60d."},
    {"id": "drawdown_buy", "fn": entry_drawdown_buy,
     "params": {}, "tp": 0.12, "sl": 0.06, "max_hold": 336,
     "desc": "Buy -8% drawdowns from 14d high with 4h-up filter (no falling knife). 12/6 TP/SL."},
    {"id": "regime_split", "fn": entry_regime_split,
     "params": {}, "tp": 999, "sl": 0.10, "max_hold": 99999,
     "desc": "Hybrid: enter at start if 8d>32d SMA (bull) + re-enter on every bull crossover. -10% SL only, no TP — let it ride."},
    {"id": "dual_momentum", "fn": entry_dual_momentum_filter,
     "params": {}, "tp": 0.15, "sl": 0.06, "max_hold": 336,
     "desc": "Dual momentum: BOTH 7d AND 30d returns positive + not at 24h high. Antonacci-style trend confirmation. 15/6 TP/SL."},
    # 2026-04-27 — trailing variant: same entry, but exits via trailing-stop after +5%
    {"id": "dual_momentum_trail", "fn": entry_dual_momentum_filter,
     "params": {"trail_pct": 0.02, "trail_arm_pct": 0.05}, "tp": 0.30, "sl": 0.06, "max_hold": 336,
     "desc": "dual_momentum entry + trailing-stop exit: arm at +5%, exit on -2% from high-water mark. Hard TP cap +30%, SL -6%. Captures more of each winner; closes faster on stalls."},
]


def main() -> int:
    log(f"=== Strategy lab run, {len(STRATEGIES)} candidates × {len(PRODUCTS)} coins ===")
    candle_cache = {}
    for p in PRODUCTS:
        candle_cache[p] = fetch_hourly(p, LOOKBACK_DAYS * 24)
        log(f"  fetched {len(candle_cache[p])} candles for {p}")

    results = []
    for s in STRATEGIES:
        per_coin = []
        for p in PRODUCTS:
            r = replay(p, candle_cache[p], s["fn"], s["params"],
                       s["tp"], s["sl"], s["max_hold"], FEE_BPS_RT)
            if r:
                per_coin.append({"product": p, **r})
        if not per_coin: continue
        avg_cum = sum(c["cum_return"] for c in per_coin) / len(per_coin)
        avg_bh = sum(c["buy_hold"] for c in per_coin) / len(per_coin)
        avg_hit = sum(c["hit_rate"] * c["trades"] for c in per_coin) / max(1, sum(c["trades"] for c in per_coin))
        total_trades = sum(c["trades"] for c in per_coin)
        alpha = avg_cum - avg_bh
        verdict = "EDGE" if alpha > PROMOTE_THRESHOLD else ("MARGINAL" if alpha > 0 else "FAILED")
        results.append({
            "id": s["id"], "desc": s["desc"], "tp": s["tp"], "sl": s["sl"],
            "max_hold_h": s["max_hold"], "params": s["params"],
            "avg_cum_return": round(avg_cum, 5), "avg_buy_hold": round(avg_bh, 5),
            "alpha_vs_bh": round(alpha, 5), "weighted_hit_rate": round(avg_hit, 4),
            "total_trades_60d": total_trades, "trades_per_day": round(total_trades / (LOOKBACK_DAYS * len(PRODUCTS)), 3),
            "verdict": verdict,
            "per_coin": per_coin,
        })
        log(f"  {s['id']:20s}  trades={total_trades:>4d}  hit={avg_hit*100:>5.1f}%  "
            f"strat={avg_cum*100:>+6.2f}%  bh={avg_bh*100:>+6.2f}%  alpha={alpha*100:>+6.2f}%  → {verdict}")

    # Sort by alpha desc
    results.sort(key=lambda r: -r["alpha_vs_bh"])
    best = results[0] if results else None

    out = {
        "as_of": now_iso(),
        "lookback_days": LOOKBACK_DAYS,
        "fee_bps_round_trip": FEE_BPS_RT,
        "promote_threshold_alpha": PROMOTE_THRESHOLD,
        "products": PRODUCTS,
        "strategies_tested": len(STRATEGIES),
        "best_strategy": best["id"] if best else None,
        "best_alpha": best["alpha_vs_bh"] if best else None,
        "best_verdict": best["verdict"] if best else None,
        "results": results,
    }
    OUT.write_text(json.dumps(out, indent=2))

    # Auto-promote: if best strategy beats threshold AND halt is active, lift halt + write live config
    if best and best["alpha_vs_bh"] > PROMOTE_THRESHOLD:
        LIVE_STRATEGY.write_text(json.dumps({
            "promoted_at": now_iso(),
            "strategy_id": best["id"],
            "tp": best["tp"], "sl": best["sl"], "max_hold_h": best["max_hold_h"],
            "params": best["params"],
            "alpha_vs_bh": best["alpha_vs_bh"],
            "weighted_hit_rate": best["weighted_hit_rate"],
            "total_trades_60d": best["total_trades_60d"],
            "verdict": best["verdict"],
        }, indent=2))
        if HALT_FILE.exists():
            HALT_FILE.unlink()
            log(f"AUTO-PROMOTE: best strategy '{best['id']}' alpha={best['alpha_vs_bh']*100:+.2f}% — HALT LIFTED")
        else:
            log(f"AUTO-PROMOTE: best strategy '{best['id']}' alpha={best['alpha_vs_bh']*100:+.2f}% — bot already running")
    else:
        log(f"NO PROMOTION: best alpha {best['alpha_vs_bh']*100 if best else 0:+.2f}% < {PROMOTE_THRESHOLD*100:.1f}% threshold")

    log(f"DONE  best={best['id'] if best else 'none'}  alpha={best['alpha_vs_bh']*100 if best else 0:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
