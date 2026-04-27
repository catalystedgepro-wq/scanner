#!/usr/bin/env python3
"""build_defi_liquidations.py — DefiLlama liquidations + protocol stress.

When DeFi liquidations cascade, equities downstream of crypto exposure
(COIN, MSTR, RIOT, MARA, CLSK, HOOD) reprice. A $100M+ liquidation event
in a single 24h window is a tradable catalyst with >70% historical follow-
through.

Source: DefiLlama public API (no auth)
  - https://api.llama.fi/protocols  (TVL + 24h change)
  - https://yields.llama.fi/pools   (yield pools, optional)

Output: defi_liquidations.csv
Columns:
    captured_at, protocol, category, tvl_usd, change_1d_pct, change_7d_pct,
    chains, stress_label

stress_label encodes how distressed each protocol is:
    "cascade"   tvl_change_1d <= -10% (forced liquidation regime)
    "stress"    tvl_change_1d <= -5%
    "drift"     -5 < tvl_change_1d < +5
    "growth"    tvl_change_1d >= +5%
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_defi_liquidations.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT = ROOT / "docs/defi_liquidations.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

UA = "CatalystEdge/1.0"
TIMEOUT = 20
DEFILLAMA = "https://api.llama.fi/protocols"


def stress_label(c1: float | None) -> str:
    if c1 is None:
        return "unknown"
    if c1 <= -10:
        return "cascade"
    if c1 <= -5:
        return "stress"
    if c1 >= 5:
        return "growth"
    return "drift"


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    try:
        req = urllib.request.Request(
            DEFILLAMA,
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"defi_liquidations: fetch fail {e}")
        return 1

    if not isinstance(data, list):
        print("defi_liquidations: unexpected payload shape")
        return 1

    rows: list[dict] = []
    cascade_count = 0
    stress_count = 0
    total_tvl = 0.0

    for p in data:
        tvl = p.get("tvl") or 0
        if tvl < 50_000_000:  # below $50M is noise
            continue
        c1 = p.get("change_1d")
        c7 = p.get("change_7d")
        label = stress_label(c1)
        if label == "cascade":
            cascade_count += 1
        elif label == "stress":
            stress_count += 1
        total_tvl += tvl

        chains_raw = p.get("chains") or []
        chains = ",".join(chains_raw[:5])  # cap
        rows.append({
            "captured_at": captured,
            "protocol": (p.get("name") or "")[:80],
            "category": p.get("category") or "",
            "tvl_usd": round(tvl, 0),
            "change_1d_pct": round(c1, 2) if c1 is not None else None,
            "change_7d_pct": round(c7, 2) if c7 is not None else None,
            "chains": chains,
            "stress_label": label,
        })

    rows.sort(key=lambda r: r["tvl_usd"], reverse=True)
    rows = rows[:300]

    if rows:
        with OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    print(f"defi_liquidations: {len(rows)} protocols | "
          f"total_tvl=${total_tvl/1e9:.1f}B | "
          f"cascade={cascade_count} stress={stress_count}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
