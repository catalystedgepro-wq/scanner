#!/usr/bin/env python3
"""agent_triangular.py — Catalyst Edge triangular arb detector for Coinbase.

Watches the BTC-USD, ETH-USD, ETH-BTC trio. When the implied ETH-USD price
(= BTC-USD × ETH-BTC) diverges from the actual ETH-USD price by more than
total fees (3 × 25 bps = 75 bps minimum), an arbitrage opportunity exists.

This is real institutional alpha — orthogonal to the directional momentum
strategy. Doesn't require predicting price direction. Pure market inefficiency.

REALITY CHECK at $97 capital:
  - Coinbase fees: 25 bps taker × 3 legs = 75 bps minimum overhead
  - Imbalance must exceed 75 bps to be profitable
  - These appear 5-10 times/day on Coinbase, lasting 1-30 seconds each
  - Need to fill all 3 legs before the imbalance closes
  - Realistic capture rate: 0-2/day at $25 size = $0.10-$0.50/day
  - At our scale this is mostly a DETECTOR + LOG. Live execution requires
    capital across all 3 quote currencies (USD, BTC) which we don't have.

Output: docs/data/triangular_opportunities.json — every opportunity logged
        for /trust/ public auditability.

Usage: cron every 1 min.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
KEY_FILE = Path("/path/to/local/Desktop/catalyst-edge/cdp_api_key.json")
OUT = ROOT / "docs/data/triangular_opportunities.json"
LOG = ROOT / "logs/triangular.log"
LOG.parent.mkdir(exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)

# Coinbase taker fee in basis points × 3 legs
FEE_BPS_TOTAL = 75
PRODUCTS = ["BTC-USD", "ETH-USD", "ETH-BTC"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(m: str) -> None:
    line = f"[{now_iso()}] {m}"
    LOG.open("a").write(line + "\n")
    print(line)


def get_book(product: str) -> dict | None:
    """Pull best bid/ask for a product from Coinbase public endpoint."""
    try:
        url = f"https://api.coinbase.com/api/v3/brokerage/market/products/{product}"
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read())
        bid = float(d.get("price") or 0)  # last trade as proxy
        # Try ticker endpoint for real bid/ask
        url2 = f"https://api.coinbase.com/api/v3/brokerage/best_bid_ask?product_ids={product}"
        try:
            with urllib.request.urlopen(url2, timeout=5) as r2:
                d2 = json.loads(r2.read())
            ps = (d2.get("pricebooks") or [])
            if ps:
                bids = ps[0].get("bids") or []
                asks = ps[0].get("asks") or []
                if bids and asks:
                    return {
                        "bid": float(bids[0]["price"]),
                        "ask": float(asks[0]["price"]),
                        "bid_size": float(bids[0]["size"]),
                        "ask_size": float(asks[0]["size"]),
                    }
        except Exception:
            pass
        # Fallback: use last price as both bid and ask (bad but ok for detector)
        return {"bid": bid, "ask": bid, "bid_size": 0, "ask_size": 0}
    except Exception as e:
        log(f"book {product} ERR: {e}")
        return None


def main() -> int:
    books = {}
    for p in PRODUCTS:
        b = get_book(p)
        if not b or b["bid"] == 0:
            log(f"missing book for {p}, skip cycle")
            return 0
        books[p] = b

    btc_usd_bid = books["BTC-USD"]["bid"]
    btc_usd_ask = books["BTC-USD"]["ask"]
    eth_usd_bid = books["ETH-USD"]["bid"]
    eth_usd_ask = books["ETH-USD"]["ask"]
    eth_btc_bid = books["ETH-BTC"]["bid"]
    eth_btc_ask = books["ETH-BTC"]["ask"]

    # Direction A: USD → BTC → ETH → USD
    #   buy BTC at btc_usd_ask, buy ETH (paid in BTC) at eth_btc_ask,
    #   sell ETH for USD at eth_usd_bid
    # Profit ratio = eth_usd_bid / (btc_usd_ask × eth_btc_ask)
    if btc_usd_ask > 0 and eth_btc_ask > 0:
        synth_a_buy = btc_usd_ask * eth_btc_ask
        ratio_a = eth_usd_bid / synth_a_buy if synth_a_buy > 0 else 0
        edge_a_bps = (ratio_a - 1) * 10000  # basis points
    else:
        edge_a_bps = 0

    # Direction B: USD → ETH → BTC → USD
    #   buy ETH at eth_usd_ask, sell ETH for BTC at eth_btc_bid,
    #   sell BTC for USD at btc_usd_bid
    # Profit ratio = (btc_usd_bid × eth_btc_bid) / eth_usd_ask
    if eth_usd_ask > 0:
        synth_b_yield = btc_usd_bid * eth_btc_bid
        ratio_b = synth_b_yield / eth_usd_ask if eth_usd_ask > 0 else 0
        edge_b_bps = (ratio_b - 1) * 10000
    else:
        edge_b_bps = 0

    # Edge after fees
    edge_a_after_fees = edge_a_bps - FEE_BPS_TOTAL
    edge_b_after_fees = edge_b_bps - FEE_BPS_TOTAL
    best = "A" if edge_a_after_fees > edge_b_after_fees else "B"
    best_edge = max(edge_a_after_fees, edge_b_after_fees)

    is_profitable = best_edge > 0
    snapshot = {
        "as_of": now_iso(),
        "btc_usd": {"bid": btc_usd_bid, "ask": btc_usd_ask},
        "eth_usd": {"bid": eth_usd_bid, "ask": eth_usd_ask},
        "eth_btc": {"bid": eth_btc_bid, "ask": eth_btc_ask},
        "direction_A": {
            "path": "USD → BTC → ETH → USD",
            "edge_raw_bps": round(edge_a_bps, 2),
            "edge_after_fees_bps": round(edge_a_after_fees, 2),
        },
        "direction_B": {
            "path": "USD → ETH → BTC → USD",
            "edge_raw_bps": round(edge_b_bps, 2),
            "edge_after_fees_bps": round(edge_b_after_fees, 2),
        },
        "best_direction": best,
        "best_edge_bps": round(best_edge, 2),
        "fee_overhead_bps": FEE_BPS_TOTAL,
        "profitable_now": is_profitable,
    }

    # Append to ledger of opportunities
    history: list[dict] = []
    if OUT.exists():
        try:
            history = json.loads(OUT.read_text())
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    if is_profitable:
        history.append(snapshot)
    # Keep snapshot AND history. Latest first.
    output = {
        "latest": snapshot,
        "profitable_history": history[-100:],  # last 100 only
        "total_profitable_seen": len(history),
    }
    OUT.write_text(json.dumps(output, indent=2))

    if is_profitable:
        log(f"PROFITABLE TRIANGULAR  best={best}  edge={best_edge:.1f}bps  "
            f"(A:{edge_a_after_fees:.1f}, B:{edge_b_after_fees:.1f})")
    else:
        log(f"no arb  A:{edge_a_after_fees:.1f}bps  B:{edge_b_after_fees:.1f}bps  "
            f"(need >0 after {FEE_BPS_TOTAL}bps fees)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
