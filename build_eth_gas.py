#!/usr/bin/env python3
"""build_eth_gas.py — Ethereum gas-fee tracker for L1 / L2 catalyst signals.

Source: blockchair (already wired) + ethgas.watch + Etherscan public gas
tracker. Free, no auth.

High-gas regimes (>100 gwei) signal:
  - DEX volume spike (revenue tailwind for COIN, HOOD)
  - L2 demand burst (MATIC, ARB, OP token correlations)
  - NFT / mint frenzy (RBLX, COIN secondary effects)
  - DeFi liquidation cascades

Output: eth_gas.csv
Columns:
    captured_at, gas_low_gwei, gas_avg_gwei, gas_high_gwei, base_fee_gwei,
    next_block_priority_gwei, congestion_label, eth_usd_price

Stdlib only. Light enough to run inline (one HTTP, low latency).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT  = ROOT / "eth_gas.csv"

UA = "CatalystEdge/1.0"
TIMEOUT = 12

# Blockscout public stats — no auth, returns gas prices + ETH spot + network util
BLOCKSCOUT_STATS = "https://eth.blockscout.com/api/v2/stats"


def _fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"  fetch fail {url[:60]}: {e}")
        return None


def label_congestion(gas_high: float) -> str:
    if gas_high >= 200: return "extreme"
    if gas_high >= 100: return "high"
    if gas_high >= 50:  return "elevated"
    if gas_high >= 25:  return "normal"
    return "low"


def main() -> int:
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    s = _fetch_json(BLOCKSCOUT_STATS) or {}
    gp = s.get("gas_prices") or {}

    def _f(v):
        try:
            return round(float(v), 2)
        except Exception:
            return 0.0

    gas_low  = _f(gp.get("slow"))
    gas_avg  = _f(gp.get("average"))
    gas_high = _f(gp.get("fast"))
    eth_usd  = _f(s.get("coin_price"))
    network_util = _f(s.get("network_utilization_percentage"))
    market_cap = _f(s.get("market_cap"))

    # base_fee not directly exposed; approx as low gas
    base_fee = gas_low
    priority = max(0.0, round(gas_avg - gas_low, 2))

    cong = label_congestion(gas_high)

    row = {
        "captured_at":           captured_at,
        "gas_low_gwei":          gas_low,
        "gas_avg_gwei":          gas_avg,
        "gas_high_gwei":         gas_high,
        "base_fee_gwei":         base_fee,
        "next_block_priority_gwei": priority,
        "congestion_label":      cong,
        "eth_usd_price":         eth_usd,
        "network_utilization":   network_util,
    }

    # Append-only history file
    is_new = not OUT.exists()
    with OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if is_new:
            w.writeheader()
        w.writerow(row)

    print(f"eth_gas: low={gas_low} avg={gas_avg} high={gas_high} gwei | "
          f"base={base_fee} prio={priority} | regime={cong} | "
          f"ETH=${eth_usd:.0f}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
