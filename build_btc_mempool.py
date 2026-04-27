#!/usr/bin/env python3
"""build_btc_mempool.py — Bitcoin network health via mempool.space.

Bitcoin onchain utility demand is a forward read on miner revenue,
exchange flows, and stablecoin network settlement. Mempool congestion
+ fee spikes = onchain activity surge (CME basis, miner profitability,
stablecoin settlement demand).

Signal:
- mempool_vsize > 50M vbytes + fastest_fee > 20 sat/vB = congestion =
  miner revenue tailwind (MARA, CLSK, RIOT, CIFR, WULF, HUT, IREN)
- difficulty adjustment > +3% = hashrate inflow = miner margin
  compression short-term
- lightning total_capacity YoY = Bitcoin-as-payment adoption curve
  (relevant to BTC-adjacent fintechs, Cash App via SQ/BLOCK)
- 7d avg hashrate trend = miner capitulation or buildout indicator

Drives:
- Bitcoin miners (MARA, CLSK, RIOT, CIFR, WULF, HUT, IREN, BITF, HIVE)
- Crypto exchanges (COIN, HOOD)
- MSTR (treasury leverage proxy)
- Payment rails (SQ/BLOCK via Cash App BTC, PYPL)
- Crypto infra (CORZ, BTCS, SDIG)

Source: mempool.space (free, public, no key).
Output: btc_mempool.csv
Columns: metric, value, unit, meta, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "btc_mempool.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://mempool.space/api"


def _get(path: str):
    req = urllib.request.Request(f"{BASE}{path}",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"btc_mempool: {path}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []

    # Fee recommendations.
    fees = _get("/v1/fees/recommended")
    if isinstance(fees, dict):
        for k in ("fastestFee", "halfHourFee", "hourFee", "economyFee",
                  "minimumFee"):
            v = fees.get(k)
            if v is not None:
                rows.append({
                    "metric": f"fee_{k}",
                    "value": f"{float(v):.2f}",
                    "unit": "sat/vB",
                    "meta": "",
                })

    # Mempool snapshot.
    mp = _get("/mempool")
    if isinstance(mp, dict):
        for k, unit in (("count", "tx"), ("vsize", "vB"),
                        ("total_fee", "sat")):
            v = mp.get(k)
            if v is not None:
                rows.append({
                    "metric": f"mempool_{k}",
                    "value": f"{float(v):.0f}",
                    "unit": unit,
                    "meta": "",
                })

    # Difficulty adjustment.
    da = _get("/v1/difficulty-adjustment")
    if isinstance(da, dict):
        for k, unit in (("progressPercent", "%"),
                        ("difficultyChange", "%"),
                        ("remainingBlocks", "blk"),
                        ("timeAvg", "ms")):
            v = da.get(k)
            if v is not None:
                rows.append({
                    "metric": f"difficulty_{k}",
                    "value": f"{float(v):.4f}",
                    "unit": unit,
                    "meta": "",
                })
        nrh = da.get("nextRetargetHeight")
        if nrh is not None:
            rows.append({
                "metric": "difficulty_nextRetargetHeight",
                "value": f"{nrh}",
                "unit": "block",
                "meta": "",
            })

    # 7d hashrate trend.
    hr = _get("/v1/mining/hashrate/1w")
    if isinstance(hr, dict):
        series = hr.get("hashrates") or []
        if series:
            latest = series[-1].get("avgHashrate")
            first = series[0].get("avgHashrate")
            if latest is not None:
                rows.append({
                    "metric": "hashrate_latest_EH_s",
                    "value": f"{float(latest) / 1e18:.2f}",
                    "unit": "EH/s",
                    "meta": f"ts={series[-1].get('timestamp')}",
                })
            if first is not None and latest is not None and first > 0:
                pct = (float(latest) / float(first) - 1) * 100
                rows.append({
                    "metric": "hashrate_7d_change_pct",
                    "value": f"{pct:+.2f}",
                    "unit": "%",
                    "meta": f"n={len(series)}",
                })
        adiff = hr.get("currentDifficulty")
        if adiff is not None:
            rows.append({
                "metric": "current_difficulty",
                "value": f"{float(adiff):.0f}",
                "unit": "hash",
                "meta": "",
            })

    # Lightning network capacity/adoption.
    ln = _get("/v1/lightning/statistics/latest")
    if isinstance(ln, dict):
        latest = ln.get("latest") or {}
        for k, unit in (("channel_count", "ch"),
                        ("node_count", "nd"),
                        ("total_capacity", "sat"),
                        ("avg_capacity", "sat"),
                        ("avg_fee_rate", "ppm"),
                        ("clearnet_nodes", "nd"),
                        ("tor_nodes", "nd")):
            v = latest.get(k)
            if v is not None:
                rows.append({
                    "metric": f"lightning_{k}",
                    "value": f"{float(v):.0f}",
                    "unit": unit,
                    "meta": f"as_of={latest.get('added','')[:10]}",
                })

    # Tip block height (latest).
    tip = _get("/blocks/tip/height")
    if isinstance(tip, int):
        rows.append({
            "metric": "tip_height",
            "value": f"{tip}",
            "unit": "block",
            "meta": "",
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"btc_mempool: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["metric", "value", "unit", "meta", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    keyed = {r["metric"]: r["value"] for r in rows}
    bits = []
    if "fee_fastestFee" in keyed:
        bits.append(f"fastfee={keyed['fee_fastestFee']}sat/vB")
    if "mempool_count" in keyed:
        bits.append(f"mempool={keyed['mempool_count']}tx")
    if "hashrate_latest_EH_s" in keyed:
        bits.append(f"hashrate={keyed['hashrate_latest_EH_s']}EH/s")
    if "difficulty_difficultyChange" in keyed:
        bits.append(f"diffΔ={keyed['difficulty_difficultyChange']}%")
    if "lightning_total_capacity" in keyed:
        btc = float(keyed["lightning_total_capacity"]) / 1e8
        bits.append(f"LN={btc:.0f}BTC")
    if "tip_height" in keyed:
        bits.append(f"tip={keyed['tip_height']}")
    print(f"btc_mempool: {len(rows)} rows | {' '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
