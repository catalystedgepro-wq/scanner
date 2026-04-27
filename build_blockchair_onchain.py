#!/usr/bin/env python3
"""build_blockchair_onchain.py — multi-chain on-chain macro.

Full-chain stats (BTC/ETH/LTC/DOGE/BCH) per API call:
- 24h tx count + USD volume (actual economic throughput)
- CDD-24h (coin days destroyed — old-coin wake-up signal)
- Hashrate + difficulty (security + mining economics)
- Mempool depth (congestion)
- Node count (network distribution)
- Largest_tx_24h USD (whale activity flag)

Complements build_btc_eth_network.py (gas/fees/pools) and
build_crypto_onchain.py (treasury balances) — this one covers the
actual economic pulse of each chain.

Signal: CDD spikes = long-dormant coins moving (bearish if peak cycle,
neutral if accumulation). Hashrate drops = miner capitulation / power
crisis. USD volume 24h diverging from price = accumulation/distribution.

Drives:
- BTC miners (MARA, RIOT, CLSK, CIFR, HIVE, BITF, CORZ)
- Crypto exchange proxies (COIN, HOOD)
- BTC treasuries (MSTR, SMLR, BTBT)
- Doge-exposed stocks (TSLA via X/DOGE commerce)

Source: api.blockchair.com/{chain}/stats (free, no key, rate-limited).
Output: blockchair_onchain.csv
Columns: chain, metric, value, unit, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "blockchair_onchain.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

CHAINS = ["bitcoin", "ethereum", "litecoin", "dogecoin", "bitcoin-cash"]

# Fields to extract from each chain's /stats response
METRICS = [
    ("best_block_height", "block_height", "block"),
    ("blocks_24h", "blocks_24h", "blocks"),
    ("transactions_24h", "tx_count_24h", "tx"),
    ("volume_24h", "volume_24h", "native_units"),
    ("difficulty", "difficulty", "pts"),
    ("hashrate_24h", "hashrate_24h", "h/s"),
    ("mempool_transactions", "mempool_tx", "tx"),
    ("mempool_tps", "mempool_tps", "tx/s"),
    ("average_transaction_fee_24h", "avg_fee_24h", "native_base"),
    ("median_transaction_fee_24h", "median_fee_24h", "native_base"),
    ("cdd_24h", "cdd_24h", "coin-days"),
    ("inflation_24h", "inflation_24h", "native_base"),
    ("nodes", "nodes", "nodes"),
    ("circulation", "circulation", "native_base"),
]


def _fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"blockchair_onchain: {url}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for chain in CHAINS:
        payload = _fetch(f"https://api.blockchair.com/{chain}/stats")
        if not isinstance(payload, dict):
            time.sleep(2)
            continue
        data = payload.get("data") if isinstance(payload.get("data"), dict) \
            else None
        if not isinstance(data, dict):
            time.sleep(2)
            continue

        # Largest tx 24h USD (nested dict)
        largest = data.get("largest_transaction_24h") or {}
        if isinstance(largest, dict) and largest.get("value_usd"):
            try:
                val = float(largest["value_usd"])
                rows.append({
                    "chain": chain,
                    "metric": "largest_tx_24h_usd",
                    "value": f"{val:.2f}",
                    "unit": "USD",
                })
            except (TypeError, ValueError):
                pass

        for src, metric, unit in METRICS:
            raw = data.get(src)
            if raw is None:
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            rows.append({
                "chain": chain,
                "metric": metric,
                "value": f"{val:.6f}" if abs(val) < 1 else f"{val:.2f}",
                "unit": unit,
            })

        # Rate limit: blockchair free tier = 30 req/min.
        time.sleep(2)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"blockchair_onchain: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["chain", "metric", "value", "unit", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    chains_hit = sorted({r["chain"] for r in rows})
    btc_vol = next(
        (r for r in rows if r["chain"] == "bitcoin"
         and r["metric"] == "volume_24h"), None)
    btc_cdd = next(
        (r for r in rows if r["chain"] == "bitcoin"
         and r["metric"] == "cdd_24h"), None)
    bits = []
    if btc_vol:
        bits.append(f"btc_vol24h={float(btc_vol['value'])/1e13:.2f}×10¹³sat")
    if btc_cdd:
        bits.append(f"btc_cdd={float(btc_cdd['value']):.0f}")
    print(f"blockchair_onchain: {len(rows)} metrics across "
          f"{len(chains_hit)} chains | {' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
