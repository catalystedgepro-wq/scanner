#!/usr/bin/env python3
"""build_btc_eth_network.py — BTC + ETH live network activity.

Network usage + miner economics signals, complementary to the existing
build_crypto_onchain.py (which tracks corporate treasury balances).

- Ethereum gas tracker (Etherscan v2, no-key, rate-limited 1/5sec)
  → DeFi/NFT activity → COIN/HOOD trade volume proxy.
- Bitcoin recommended fee tiers (mempool.space) → block-space demand.
  Spike = ordinals/inscriptions → MARA/RIOT/CLSK fee-revenue component.
- Bitcoin mempool backlog (mempool.space) → pending tx count + vsize.
- Bitcoin mining pool share (mempool.space 24h) → hash concentration.
  Foundry/Antpool dominance feeds hash-centralization narrative.

Output: btc_eth_network.csv
Columns: metric_type, metric_name, value, unit, detail, captured_at

Sources: api.etherscan.io/v2 + mempool.space (both no-key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "btc_eth_network.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

ETH_GAS = ("https://api.etherscan.io/v2/api"
           "?chainid=1&module=gastracker&action=gasoracle")
BTC_FEES = "https://mempool.space/api/v1/fees/recommended"
BTC_POOLS = "https://mempool.space/api/v1/mining/pools/24h"
BTC_MEMPOOL = "https://mempool.space/api/mempool"


def _fetch(url: str, timeout: int = 15) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"btc_eth_network {url[:48]}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []

    gas = _fetch(ETH_GAS)
    if isinstance(gas, dict):
        result = gas.get("result") or {}
        if isinstance(result, dict):
            for name, key in [
                ("eth_gas_safe",    "SafeGasPrice"),
                ("eth_gas_propose", "ProposeGasPrice"),
                ("eth_gas_fast",    "FastGasPrice"),
                ("eth_base_fee",    "suggestBaseFee"),
            ]:
                v = result.get(key, "")
                if v != "":
                    rows.append({
                        "metric_type": "eth_gas",
                        "metric_name": name,
                        "value": str(v)[:12],
                        "unit": "gwei",
                        "detail": f"block_{result.get('LastBlock','')}",
                    })

    fees = _fetch(BTC_FEES)
    if isinstance(fees, dict):
        for name, key in [
            ("btc_fee_fastest",  "fastestFee"),
            ("btc_fee_30min",    "halfHourFee"),
            ("btc_fee_1h",       "hourFee"),
            ("btc_fee_economy",  "economyFee"),
            ("btc_fee_minimum",  "minimumFee"),
        ]:
            v = fees.get(key)
            if v is not None:
                rows.append({
                    "metric_type": "btc_fee",
                    "metric_name": name,
                    "value": str(v),
                    "unit": "sat_vbyte",
                    "detail": "",
                })

    mempool = _fetch(BTC_MEMPOOL)
    if isinstance(mempool, dict):
        for name, key, unit in [
            ("btc_mempool_tx_count",  "count",     "tx"),
            ("btc_mempool_vsize",     "vsize",     "vbytes"),
            ("btc_mempool_total_fee", "total_fee", "sats"),
        ]:
            v = mempool.get(key)
            if v is not None:
                rows.append({
                    "metric_type": "btc_mempool",
                    "metric_name": name,
                    "value": str(v),
                    "unit": unit,
                    "detail": "",
                })

    pools = _fetch(BTC_POOLS)
    if isinstance(pools, dict):
        plist = pools.get("pools") or []
        for p in plist[:12]:
            name = (p.get("name") or "").strip()
            blocks = p.get("blockCount")
            rank = p.get("rank")
            if not name or blocks is None:
                continue
            rows.append({
                "metric_type": "btc_pool_24h",
                "metric_name": f"pool_{name[:24]}",
                "value": str(blocks),
                "unit": "blocks",
                "detail": f"rank_{rank}",
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"btc_eth_network: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["metric_type", "metric_name", "value", "unit", "detail",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    idx = {r["metric_name"]: r for r in rows}
    eth_fast = idx.get("eth_gas_fast", {}).get("value", "?")
    btc_fast = idx.get("btc_fee_fastest", {}).get("value", "?")
    pool_ct = sum(1 for r in rows if r["metric_type"] == "btc_pool_24h")
    top_pool = next(
        (r for r in rows if r["metric_type"] == "btc_pool_24h"), {})
    top_nm = top_pool.get("metric_name", "?").replace("pool_", "")
    print(f"btc_eth_network: {len(rows)} rows | ETH fast={eth_fast}gwei "
          f"BTC fast={btc_fast}sat/vB | top pool {top_nm}="
          f"{top_pool.get('value','?')} blocks "
          f"({pool_ct} pools) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
