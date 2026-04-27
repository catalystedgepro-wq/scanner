#!/usr/bin/env python3
"""build_defillama_dexs.py — DEX volume + DeFi protocol revenue.

Total decentralized exchange volume across 1000+ protocols + 100+
chains, plus top-10 DEX ranking by 24h volume.

Signal: DEX volume > CEX volume rotation = crypto power shift (good
for DEX infra tokens). DEX volume crashes during vol spikes = risk-off
liquidity concentrates on CEX. Monthly/quarterly declines = bear cycle.

Drives:
- CEX equities (COIN, HOOD) — DEX substitutes their base layer
- ETH L1 throughput proxy (ETH, LDO, MKR)
- L2 adoption (ARB, OP, MATIC)
- Solana rotation (SOL, ONDO)
- DeFi governance tokens (UNI, CRV, AAVE, MKR, GMX)

Source: api.llama.fi/overview/dexs (free, no key).
Output: defillama_dexs.csv
Columns: metric, key, value_usd, change_1d_pct, change_7d_pct,
         change_1m_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "defillama_dexs.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.llama.fi/overview/dexs"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"defillama_dexs: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"defillama_dexs: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(payload, dict):
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"defillama_dexs: empty, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []

    # Global aggregates.
    for metric, key in [
        ("total24h", "global_24h_volume"),
        ("total7d", "global_7d_volume"),
        ("total30d", "global_30d_volume"),
        ("total1y", "global_1y_volume"),
        ("total7DaysAgo", "volume_7d_ago"),
        ("total30DaysAgo", "volume_30d_ago"),
    ]:
        val = payload.get(metric)
        if val is None:
            continue
        try:
            vf = float(val)
        except (TypeError, ValueError):
            continue
        rows.append({
            "metric": "global",
            "key": key,
            "value_usd": f"{vf:.2f}",
            "change_1d_pct": f"{float(payload.get('change_1d') or 0):+.2f}",
            "change_7d_pct": f"{float(payload.get('change_7d') or 0):+.2f}",
            "change_1m_pct": f"{float(payload.get('change_1m') or 0):+.2f}",
        })

    # Top-20 DEX protocols by 24h volume.
    protocols = payload.get("protocols") or []
    if isinstance(protocols, list):
        scored: list[tuple[float, dict]] = []
        for p in protocols:
            if not isinstance(p, dict):
                continue
            try:
                v24 = float(p.get("total24h") or 0)
            except (TypeError, ValueError):
                continue
            if v24 <= 0:
                continue
            scored.append((v24, p))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        for v24, p in scored[:20]:
            name = (p.get("name") or p.get("displayName")
                    or p.get("module") or "?")[:40]
            c1 = p.get("change_1d")
            c7 = p.get("change_7d")
            c1m = p.get("change_1m")
            rows.append({
                "metric": "dex",
                "key": name,
                "value_usd": f"{v24:.2f}",
                "change_1d_pct": (f"{float(c1):+.2f}"
                                  if c1 is not None else ""),
                "change_7d_pct": (f"{float(c7):+.2f}"
                                  if c7 is not None else ""),
                "change_1m_pct": (f"{float(c1m):+.2f}"
                                  if c1m is not None else ""),
            })

    # Per-chain DEX volume breakdown from allChains.
    chains = payload.get("allChains")
    breakdown24h = payload.get("breakdown24h") or {}
    if isinstance(chains, list) and isinstance(breakdown24h, dict):
        chain_totals: dict[str, float] = {}
        for chain_name, proto_map in breakdown24h.items():
            if not isinstance(proto_map, dict):
                continue
            total = 0.0
            for v in proto_map.values():
                try:
                    total += float(v or 0)
                except (TypeError, ValueError):
                    continue
            chain_totals[chain_name] = total
        for name, total in sorted(
                chain_totals.items(), key=lambda kv: kv[1],
                reverse=True)[:15]:
            if total <= 0:
                continue
            rows.append({
                "metric": "chain",
                "key": name[:30],
                "value_usd": f"{total:.2f}",
                "change_1d_pct": "",
                "change_7d_pct": "",
                "change_1m_pct": "",
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"defillama_dexs: parsed 0, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["metric", "key", "value_usd", "change_1d_pct",
                  "change_7d_pct", "change_1m_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    glob = next((r for r in rows
                 if r["key"] == "global_24h_volume"), None)
    top_dex = next((r for r in rows if r["metric"] == "dex"), None)
    top_chain = next((r for r in rows if r["metric"] == "chain"), None)
    bits = []
    if glob:
        bits.append(f"24h_vol=${float(glob['value_usd'])/1e9:.2f}B "
                    f"({glob['change_1d_pct']}% 1d)")
    if top_dex:
        bits.append(f"top_dex={top_dex['key']}="
                    f"${float(top_dex['value_usd'])/1e6:.1f}M")
    if top_chain:
        bits.append(f"top_chain={top_chain['key']}="
                    f"${float(top_chain['value_usd'])/1e6:.1f}M")
    print(f"defillama_dexs: {len(rows)} rows | {' | '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
