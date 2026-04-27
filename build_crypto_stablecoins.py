#!/usr/bin/env python3
"""build_crypto_stablecoins.py — Stablecoin market caps (DefiLlama).

Stablecoin mint/burn = leading indicator for crypto flows. USDT mints
> $500M/day = BTC upside ahead. USDC redemptions post-SVB signaled
flight-to-quality. CRCL issuer earns T-bill yield on reserves. Tether
dominance vs USDC = offshore vs US exchange volume split signal.

Source: api.llama.fi/stablecoins (public).
Output: crypto_stablecoins.csv
Columns: symbol, name, circulating_usd, peg_mechanism, chain_count,
         pct_total, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_stablecoins.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch() -> list[dict]:
    url = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"stables: {e}")
        return []
    return data.get("peggedAssets", []) if isinstance(data, dict) else []


def main() -> None:
    items = fetch()
    total = 0
    processed = []
    for s in items:
        circ = (s.get("circulating") or {}).get("peggedUSD") or 0
        total += circ
        processed.append((s, circ))
    processed.sort(key=lambda x: x[1], reverse=True)
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for s, circ in processed[:40]:
        chains = s.get("chains") or []
        rows.append({
            "symbol": s.get("symbol", ""),
            "name": (s.get("name") or "")[:60],
            "circulating_usd": f"{circ:.0f}",
            "peg_mechanism": s.get("pegMechanism", ""),
            "chain_count": len(chains),
            "pct_total": f"{(circ / total * 100):.2f}" if total else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol", "name", "circulating_usd", "peg_mechanism",
                "chain_count", "pct_total", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    total_b = total / 1e9 if total else 0
    print(f"stables: {len(rows)} coins | total=${total_b:.1f}B | #1 "
          f"{top.get('symbol','?')} {top.get('pct_total','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
