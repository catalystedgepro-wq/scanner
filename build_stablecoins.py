#!/usr/bin/env python3
"""build_stablecoins.py — stablecoin circulation by peg + chain.

Stablecoin supply is the single best real-time proxy for crypto
market liquidity. When USDT/USDC circulation expands, dollars are
flowing into on-chain rails → Bitcoin bid, miner bid, COIN revenue.
Contraction signals deleveraging.

Signal:
- Total pegged supply ↑ 7d > 2% = crypto risk-on imminent
- USDT vs USDC rotation = regulatory/jurisdiction sentiment
  (post-Silicon Valley Bank, USDC ratio collapsed then recovered)
- DAI/FRAX/FDUSD/PYUSD share tracks DeFi-native liquidity
- Per-chain breakdown: ETH/TRX/SOL shares signal L1 rotation

Drives:
- Exchanges (COIN, HOOD)
- Bitcoin miners (MSTR, MARA, CLSK, RIOT, CIFR, WULF, HUT, IREN)
- Crypto infra (CORZ, CLSK, SDIG)
- Payment rails (PYPL PYUSD, HUB Circle-adjacent, CRCL if listed)
- Ethereum L1/L2 (ETH, ARB, OP, MATIC proxies)
- Solana ecosystem (SOL, ONDO)

Source: stablecoins.llama.fi/stablecoins?includePrices=true (free).
Output: stablecoins.csv
Columns: scope, key, circulating_usd, prev_day_usd, prev_week_usd,
         prev_month_usd, change_1d_pct, change_7d_pct, change_30d_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "stablecoins.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"


def _unwrap(v) -> float | None:
    if isinstance(v, dict):
        for pk in ("peggedUSD", "peggedEUR", "peggedVAR"):
            if pk in v:
                try:
                    return float(v[pk])
                except (TypeError, ValueError):
                    continue
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(cur: float | None, prev: float | None) -> str:
    if cur is None or prev is None or prev == 0:
        return ""
    return f"{((cur / prev) - 1) * 100:+.2f}"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"stablecoins: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"stablecoins: keeping existing {OUT_CSV.name}")
        return

    assets = payload.get("peggedAssets") or []
    if not isinstance(assets, list) or not assets:
        return

    rows: list[dict] = []
    total_cur = 0.0
    total_day = 0.0
    total_week = 0.0
    total_month = 0.0
    chain_totals: dict[str, float] = {}
    chain_prev_day: dict[str, float] = {}

    for a in assets:
        if not isinstance(a, dict):
            continue
        cur = _unwrap(a.get("circulating"))
        if cur is None or cur < 1e7:  # ignore dust (< $10M)
            continue
        day = _unwrap(a.get("circulatingPrevDay"))
        week = _unwrap(a.get("circulatingPrevWeek"))
        month = _unwrap(a.get("circulatingPrevMonth"))
        total_cur += cur
        if day is not None:
            total_day += day
        if week is not None:
            total_week += week
        if month is not None:
            total_month += month

        rows.append({
            "scope": "stablecoin",
            "key": (a.get("symbol") or a.get("name") or "?")[:10],
            "circulating_usd": f"{cur:.2f}",
            "prev_day_usd": f"{day:.2f}" if day is not None else "",
            "prev_week_usd": f"{week:.2f}" if week is not None else "",
            "prev_month_usd": f"{month:.2f}" if month is not None else "",
            "change_1d_pct": _pct(cur, day),
            "change_7d_pct": _pct(cur, week),
            "change_30d_pct": _pct(cur, month),
        })

        # Per-chain aggregation.
        chains = a.get("chainCirculating") or {}
        if isinstance(chains, dict):
            for chain_name, node in chains.items():
                if not isinstance(node, dict):
                    continue
                cv = _unwrap(node.get("current"))
                pd = _unwrap(node.get("circulatingPrevDay"))
                if cv is None:
                    continue
                chain_totals[chain_name] = chain_totals.get(
                    chain_name, 0.0) + cv
                if pd is not None:
                    chain_prev_day[chain_name] = chain_prev_day.get(
                        chain_name, 0.0) + pd

    # Prepend global aggregate row.
    rows.insert(0, {
        "scope": "global",
        "key": "total_pegged",
        "circulating_usd": f"{total_cur:.2f}",
        "prev_day_usd": f"{total_day:.2f}",
        "prev_week_usd": f"{total_week:.2f}",
        "prev_month_usd": f"{total_month:.2f}",
        "change_1d_pct": _pct(total_cur, total_day),
        "change_7d_pct": _pct(total_cur, total_week),
        "change_30d_pct": _pct(total_cur, total_month),
    })

    # Sort stablecoins (rows[1:]) by circulating desc.
    primary = [rows[0]]
    rest = rows[1:]
    rest.sort(key=lambda r: float(r["circulating_usd"]), reverse=True)
    rows = primary + rest[:30]  # top 30 by supply

    # Top 15 chains by stablecoin supply.
    top_chains = sorted(chain_totals.items(), key=lambda kv: kv[1],
                        reverse=True)[:15]
    for name, total in top_chains:
        pd = chain_prev_day.get(name)
        rows.append({
            "scope": "chain",
            "key": name[:30],
            "circulating_usd": f"{total:.2f}",
            "prev_day_usd": f"{pd:.2f}" if pd is not None else "",
            "prev_week_usd": "",
            "prev_month_usd": "",
            "change_1d_pct": _pct(total, pd),
            "change_7d_pct": "",
            "change_30d_pct": "",
        })

    if not rows:
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["scope", "key", "circulating_usd", "prev_day_usd",
                  "prev_week_usd", "prev_month_usd", "change_1d_pct",
                  "change_7d_pct", "change_30d_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    g = rows[0]
    top = next((r for r in rows[1:] if r["scope"] == "stablecoin"), None)
    top_chain = next((r for r in rows if r["scope"] == "chain"), None)
    bits = [f"total=${float(g['circulating_usd'])/1e9:.1f}B "
            f"({g['change_1d_pct']}% 1d, {g['change_7d_pct']}% 7d, "
            f"{g['change_30d_pct']}% 30d)"]
    if top:
        bits.append(f"top={top['key']}="
                    f"${float(top['circulating_usd'])/1e9:.1f}B")
    if top_chain:
        bits.append(f"top_chain={top_chain['key']}="
                    f"${float(top_chain['circulating_usd'])/1e9:.1f}B")
    print(f"stablecoins: {len(rows)} rows | {' | '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
