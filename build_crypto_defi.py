#!/usr/bin/env python3
"""build_crypto_defi.py — DeFi protocol TVL via DefiLlama.

DeFi TVL rising = crypto risk-on → COIN/MSTR/MARA/RIOT rally. BTC
dominance vs alt rotation tracked by TVL shifts. Large stablecoin
mint (USDT/USDC) → CRCL, CPG on-ramp volume signal. Ethereum-focused
TVL signals gas fee demand (affects ETH validators and miners).

Source: api.llama.fi /protocols and /v2/chains (public, no key).
Output: crypto_defi.csv
Columns: protocol, category, chain, tvl_usd, change_1d_pct,
         change_7d_pct, mcap, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_defi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://api.llama.fi/protocols"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"defillama: {e}")
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    items = fetch()
    items.sort(key=lambda p: p.get("tvl", 0) or 0, reverse=True)
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for p in items[:100]:
        chains = p.get("chains") or []
        chain = chains[0] if chains else ""
        rows.append({
            "protocol": (p.get("name") or "")[:60],
            "category": p.get("category", ""),
            "chain": chain,
            "tvl_usd": f"{p.get('tvl', 0) or 0:.0f}",
            "change_1d_pct": f"{p.get('change_1d', 0) or 0:+.2f}",
            "change_7d_pct": f"{p.get('change_7d', 0) or 0:+.2f}",
            "mcap": f"{p.get('mcap', 0) or 0:.0f}" if p.get("mcap") else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "protocol", "category", "chain",
                "tvl_usd", "change_1d_pct", "change_7d_pct",
                "mcap", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"defi: {len(rows)} protocols | #1 {top.get('protocol','?')} "
          f"tvl=${int(float(top.get('tvl_usd',0)))/1e9:.1f}B -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
