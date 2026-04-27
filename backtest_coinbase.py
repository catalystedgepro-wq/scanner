#!/usr/bin/env python3
"""backtest_coinbase.py — Walk-forward backtest of the Coinbase signal stack.

Pulls last N days of hourly candles from Coinbase, replays the same scoring
logic the live bot uses, and outputs:
  - total trades
  - hit rate (% of trades that exited at TP, not SL/time)
  - average return per trade
  - cumulative return
  - max drawdown
  - Sharpe (annualized, hourly bars)
  - vs buy-and-hold benchmark

Single source of truth for "does this strategy actually have edge" — without
this, the live bot is gambling.

Strategy replicated:
  Score = base macro signal + intraday boost
  Threshold ≥ 2 to enter
  TP +5%, SL -4%, time-stop 168h

We can only backtest the INTRADAY portion (price-based). The macro signals
(treasury flags, BTC ETF heavy, DeFi calm, ETH gas relief) need historical
CSVs that aren't always available going back. This is conservative — backtest
shows whether intraday alone is profitable. If yes, real bot ≥ that. If no,
we have a problem.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT = ROOT / "docs/data/coinbase_backtest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD",
            "DOGE-USD", "POL-USD", "DOT-USD", "ATOM-USD", "ARB-USD"]


def fetch_hourly(product: str, hours: int) -> list[dict]:
    """Coinbase caps to 350 candles per request → fetch in 300-hour chunks."""
    end = int(time.time())
    start = end - hours * 3600
    out: list[dict] = []
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
            print(f"  {product}: fetch error {e}", file=sys.stderr)
            break
        start = chunk_end
        time.sleep(0.2)  # rate-limit politeness
    out.sort(key=lambda c: int(c["start"]))
    return out


def replay(product: str, candles: list[dict],
           tp: float, sl: float, max_hold_h: int,
           fee_bps_round_trip: float = 50.0) -> dict:
    """Walk forward. At each hour, compute intraday boost as live bot does.
    If boost ≥ 2 (the threshold-equivalent for intraday-only), enter long
    at next hour's open. Track exit at TP / SL / time-stop."""
    trades: list[dict] = []
    open_pos: dict | None = None
    closes = [float(c["close"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    n = len(candles)

    for i in range(24, n - 1):
        # Compute intraday boost on bar i (using last 24 bars)
        win = closes[i-23:i+1]  # 24 bars including i
        latest = win[-1]
        chg_1h = (latest / win[-2] - 1) if len(win) > 1 else 0
        chg_4h = (latest / win[-5] - 1) if len(win) > 4 else 0
        chg_24h = (latest / win[0] - 1) if len(win) > 1 else 0
        hourly_rets = [(win[j+1]/win[j] - 1) for j in range(len(win)-1)]
        sorted_rets = sorted(hourly_rets, reverse=True)
        top_q = sorted_rets[max(1, len(sorted_rets)//5) - 1] if sorted_rets else 0
        boost = 0
        if chg_24h > 0 and chg_4h > 0:
            boost += 1
        if chg_1h > 0 and chg_1h >= top_q:
            boost += 1

        # Manage open position first
        if open_pos:
            entry_idx = open_pos["entry_idx"]
            entry_px = open_pos["entry_price"]
            high = highs[i]
            low = lows[i]
            tp_px = entry_px * (1 + tp)
            sl_px = entry_px * (1 - sl)
            held_h = i - entry_idx
            if high >= tp_px:
                exit_px = tp_px
                exit_reason = "TP"
            elif low <= sl_px:
                exit_px = sl_px
                exit_reason = "SL"
            elif held_h >= max_hold_h:
                exit_px = closes[i]
                exit_reason = "time"
            else:
                exit_reason = None

            if exit_reason:
                gross_ret = (exit_px / entry_px) - 1
                # Subtract round-trip fees (taker × 2 sides)
                fee_drag = fee_bps_round_trip / 10000.0
                ret = gross_ret - fee_drag
                trades.append({
                    "product": product, "entry_idx": entry_idx,
                    "entry_price": entry_px, "exit_price": exit_px,
                    "exit_reason": exit_reason,
                    "gross_return": gross_ret,
                    "return": ret,  # net of fees
                    "held_hours": held_h,
                })
                open_pos = None

        # Enter on boost ≥ 2 (intraday-only equivalent of threshold)
        if not open_pos and boost >= 2:
            open_pos = {"entry_idx": i + 1, "entry_price": opens[i + 1]}

    # Close any remaining at last close
    if open_pos:
        entry_idx = open_pos["entry_idx"]
        entry_px = open_pos["entry_price"]
        if entry_idx < n:
            exit_px = closes[-1]
            gross_ret = (exit_px / entry_px) - 1
            fee_drag = fee_bps_round_trip / 10000.0
            ret = gross_ret - fee_drag
            trades.append({
                "product": product, "entry_idx": entry_idx,
                "entry_price": entry_px, "exit_price": exit_px,
                "exit_reason": "open_at_end",
                "gross_return": gross_ret,
                "return": ret,
                "held_hours": n - 1 - entry_idx,
            })

    if not trades:
        return {"product": product, "trades": 0, "summary": "no_trades"}

    rets = [t["return"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    cum_ret = 1.0
    equity_curve = [1.0]
    for r in rets:
        cum_ret *= (1 + r)
        equity_curve.append(cum_ret)
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    avg_r = sum(rets) / len(rets)
    # Hourly Sharpe scaled to ~365×24 = 8760 hours, but we trade ~once per
    # several days so use trade-count scaling instead
    if len(rets) > 1:
        var = sum((r - avg_r) ** 2 for r in rets) / (len(rets) - 1)
        std = var ** 0.5
        sharpe = avg_r / std if std > 0 else 0
    else:
        sharpe = 0

    bh = (closes[-1] / closes[0]) - 1

    return {
        "product": product,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "hit_rate": len(wins) / len(trades),
        "avg_return": round(avg_r, 5),
        "best_trade": round(max(rets), 5),
        "worst_trade": round(min(rets), 5),
        "cumulative_return": round(cum_ret - 1, 5),
        "max_drawdown": round(max_dd, 5),
        "sharpe_per_trade": round(sharpe, 3),
        "buy_hold_return": round(bh, 5),
        "vs_buy_hold": round((cum_ret - 1) - bh, 5),
        "exit_breakdown": {
            "TP": sum(1 for t in trades if t["exit_reason"] == "TP"),
            "SL": sum(1 for t in trades if t["exit_reason"] == "SL"),
            "time": sum(1 for t in trades if t["exit_reason"] == "time"),
            "open": sum(1 for t in trades if t["exit_reason"] == "open_at_end"),
        },
        "trade_log": trades[-10:],  # last 10 for inspection
    }


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    hours = days * 24
    tp = 0.05
    sl = 0.04
    max_hold_h = 168
    print(f"Backtesting {hours}h ({days}d) per coin, TP={tp*100}% SL={sl*100}% max_hold={max_hold_h}h")
    results = []
    for p in PRODUCTS:
        print(f"  {p}…", end=" ", flush=True)
        candles = fetch_hourly(p, hours)
        print(f"{len(candles)} candles", end=" → ")
        r = replay(p, candles, tp, sl, max_hold_h)
        print(f"trades={r.get('trades')} hit={r.get('hit_rate', 0)*100:.0f}% "
              f"cum={r.get('cumulative_return', 0)*100:+.2f}% "
              f"vs B&H {r.get('vs_buy_hold', 0)*100:+.2f}%")
        results.append(r)
        time.sleep(0.5)

    # Portfolio-level aggregate (equal-weight across coins)
    total_trades = sum(r.get("trades", 0) for r in results)
    total_wins = sum(r.get("wins", 0) for r in results)
    avg_cum = sum(r.get("cumulative_return", 0) for r in results) / max(1, len(results))
    avg_bh = sum(r.get("buy_hold_return", 0) for r in results) / max(1, len(results))

    portfolio = {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lookback_days": days,
        "tp": tp, "sl": sl, "max_hold_h": max_hold_h,
        "total_trades": total_trades,
        "total_wins": total_wins,
        "portfolio_hit_rate": (total_wins / total_trades) if total_trades else 0,
        "avg_cumulative_return": round(avg_cum, 5),
        "avg_buy_hold_return": round(avg_bh, 5),
        "alpha_vs_buy_hold": round(avg_cum - avg_bh, 5),
        "verdict": (
            "EDGE: outperforms buy-and-hold" if avg_cum > avg_bh + 0.01
            else "NO EDGE: at or below buy-and-hold"
        ),
        "per_product": results,
    }

    OUT.write_text(json.dumps(portfolio, indent=2))
    print()
    print(f"=== PORTFOLIO ({days}d, {len(PRODUCTS)} coins, intraday-only signals) ===")
    print(f"  total trades:        {total_trades}")
    print(f"  hit rate:            {portfolio['portfolio_hit_rate']*100:.1f}%")
    print(f"  avg cumulative ret:  {portfolio['avg_cumulative_return']*100:+.2f}%")
    print(f"  avg buy-and-hold:    {portfolio['avg_buy_hold_return']*100:+.2f}%")
    print(f"  alpha vs B&H:        {portfolio['alpha_vs_buy_hold']*100:+.2f}%")
    print(f"  VERDICT:             {portfolio['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
