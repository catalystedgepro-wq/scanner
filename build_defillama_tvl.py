#!/usr/bin/env python3
"""build_defillama_tvl.py — DeFi TVL (Total Value Locked) across chains + stables.

Stablecoin supply + on-chain TVL is a macro read on crypto risk appetite.
Direct tickers: COIN (Coinbase USDC + exchange volume), SQ (Cash App BTC),
MSTR (NAV to BTC price), MARA/RIOT/CLSK (hash rate vs coin price). Also:
stablecoin redemptions → USDT de-peg scares → risk-off.

Source: llama.fi public API (free, no key, rate limit gentle).

Output: defillama_tvl.csv
Columns: metric, key, value_usd, change_1d_pct, change_7d_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "defillama_tvl.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

ENDPOINTS = [
    ("chain_tvl", "https://api.llama.fi/v2/chains"),
    ("stablecoins", "https://stablecoins.llama.fi/stablecoins?includePrices=true"),
    ("global_tvl", "https://api.llama.fi/v2/historicalChainTvl"),
]


def fetch(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"defillama {url[-30:]}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # Top chains by TVL
    chains = fetch(ENDPOINTS[0][1]) or []
    if isinstance(chains, list):
        for c in sorted(chains, key=lambda x: -(x.get("tvl") or 0))[:20]:
            rows.append({
                "metric": "chain_tvl",
                "key": c.get("name", ""),
                "value_usd": f"{c.get('tvl', 0):.0f}",
                "change_1d_pct": f"{c.get('change_1d') or 0:.2f}",
                "change_7d_pct": f"{c.get('change_7d') or 0:.2f}",
                "captured_at": now,
            })

    # Stablecoin market caps
    stables = fetch(ENDPOINTS[1][1]) or {}
    if isinstance(stables, dict):
        for s in sorted(
            stables.get("peggedAssets") or [],
            key=lambda x: -(((x.get("circulating") or {}).get("peggedUSD") or 0)),
        )[:15]:
            cap = ((s.get("circulating") or {}).get("peggedUSD") or 0)
            rows.append({
                "metric": "stablecoin_mcap",
                "key": s.get("symbol", ""),
                "value_usd": f"{cap:.0f}",
                "change_1d_pct": "",
                "change_7d_pct": "",
                "captured_at": now,
            })

    # Global historical → latest + 7d delta
    hist = fetch(ENDPOINTS[2][1]) or []
    if isinstance(hist, list) and hist:
        latest = hist[-1].get("tvl") or 0
        d7 = hist[-8].get("tvl") if len(hist) > 7 else latest
        pct = ((latest - d7) / d7 * 100) if d7 else 0
        rows.insert(0, {
            "metric": "global_tvl",
            "key": "all_chains",
            "value_usd": f"{latest:.0f}",
            "change_1d_pct": "",
            "change_7d_pct": f"{pct:+.2f}",
            "captured_at": now,
        })

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "metric", "key", "value_usd", "change_1d_pct",
                "change_7d_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"defillama_tvl: {len(rows)} rows -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
