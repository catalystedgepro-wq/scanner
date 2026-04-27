#!/usr/bin/env python3
"""build_intl_edge.py — Asymmetric Edge Insights spoke.

Finds signals retail can't see by joining across our scanners:
  - Names firing in 3+ different scanners (gap + cross-border + DCF A/B)
  - Sector-rotation events (5+ names same direction same sector globally)
  - Cross-asset divergence (BTC ETF spike + crypto miner equities flat)
  - Volume-vs-price asymmetry (high relative vol, no price reaction)

Output: docs/data/intl_edge.json  →  consumed by /international/ Edge panel.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_intl_edge.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT = ROOT / "docs/data/intl_edge.json"
OUT.parent.mkdir(parents=True, exist_ok=True)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _f(v, default=0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    gappers = _read_csv(ROOT / "docs/intl_equity_gappers.csv")
    dcf_data = _read_json(ROOT / "docs/data/intl_dcf.json")
    cb_data = _read_json(ROOT / "docs/data/cross_border_convergence.json")
    etf_rows = _read_csv(ROOT / "docs/btc_etf_flows.csv")
    defi_rows = _read_csv(ROOT / "docs/defi_liquidations.csv")

    # ── 1. Multi-scanner overlap: name firing in 3+ scanners ──────────────
    flags: dict = defaultdict(lambda: {"scanners": set(), "data": {}})
    for r in gappers:
        t = r.get("ticker", "").strip()
        if not t:
            continue
        gp = _f(r.get("gap_pct"))
        if abs(gp) >= 1.5:
            flags[t]["scanners"].add("gap")
            flags[t]["data"]["gap_pct"] = round(gp, 2)
            flags[t]["data"]["country"] = r.get("country_full", "")
            flags[t]["data"]["country_iso"] = r.get("country_iso", "")
            flags[t]["data"]["name"] = r.get("name", "")
            flags[t]["data"]["currency"] = r.get("currency", "")

    for r in dcf_data.get("top_undervalued", []):
        t = r.get("ticker", "")
        if t and r.get("grade") in ("A", "B"):
            flags[t]["scanners"].add("dcf_" + r["grade"].lower())
            flags[t]["data"]["dcf_grade"] = r["grade"]
            flags[t]["data"]["upside_pct"] = r.get("upside_pct")
            if not flags[t]["data"].get("name"):
                flags[t]["data"]["name"] = r.get("name", "")
                flags[t]["data"]["country"] = r.get("country", "")
                flags[t]["data"]["currency"] = r.get("currency", "")

    for s in cb_data.get("top_setups", []):
        if s.get("conviction") in ("STRONG", "TRADE"):
            ft = s.get("foreign_ticker", "")
            ut = s.get("us_ticker", "")
            for tk in (ft, ut):
                if tk:
                    flags[tk]["scanners"].add("crossborder")
                    flags[tk]["data"]["cb_score"] = s.get("score")
                    flags[tk]["data"]["cb_entity"] = s.get("entity_name", "")

    multi_scanner = []
    for t, info in flags.items():
        if len(info["scanners"]) >= 2:
            multi_scanner.append({
                "ticker": t,
                "scanners": sorted(info["scanners"]),
                "scanner_count": len(info["scanners"]),
                **info["data"],
            })
    multi_scanner.sort(key=lambda x: (-x["scanner_count"],
                                       -abs(_f(x.get("gap_pct")))))

    # ── 2. Sector rotation: 5+ names same direction same sector globally ──
    sector_dir: dict = defaultdict(lambda: {"up": [], "down": []})
    for r in gappers:
        gp = _f(r.get("gap_pct"))
        sec = (r.get("sector_gics") or "").strip() or None
        if not sec or abs(gp) < 1.5:
            continue
        bucket = "up" if gp > 0 else "down"
        sector_dir[sec][bucket].append({
            "ticker": r["ticker"], "country": r.get("country_iso", ""),
            "gap_pct": round(gp, 2),
        })
    rotations = []
    for sec, buckets in sector_dir.items():
        for direction in ("up", "down"):
            names = buckets[direction]
            if len(names) >= 4:  # 4+ names same direction = rotation
                names.sort(key=lambda n: -abs(n["gap_pct"]))
                rotations.append({
                    "sector": sec, "direction": direction,
                    "count": len(names),
                    "avg_gap": round(
                        sum(n["gap_pct"] for n in names) / len(names), 2),
                    "names": names[:8],
                })
    rotations.sort(key=lambda r: r["count"], reverse=True)

    # ── 3. Volume-price asymmetry: 2x+ volume, <1% price reaction ─────────
    asymmetry = []
    for r in gappers:
        vol_ratio = _f(r.get("vol_ratio_20d"))
        gp = _f(r.get("gap_pct"))
        if vol_ratio >= 2.0 and abs(gp) < 1.0:
            asymmetry.append({
                "ticker": r["ticker"], "name": r.get("name", ""),
                "country": r.get("country_full", ""),
                "country_iso": r.get("country_iso", ""),
                "currency": r.get("currency", ""),
                "vol_ratio": round(vol_ratio, 2),
                "gap_pct": round(gp, 2),
            })
    asymmetry.sort(key=lambda r: r["vol_ratio"], reverse=True)

    # ── 4. Cross-asset divergence: BTC ETF complex hot, miners flat ───────
    btc_etf_total = sum(_f(r.get("dollar_volume_usd")) for r in etf_rows)
    btc_etf_spike = sum(1 for r in etf_rows if r.get("regime") in ("spike", "frenzy"))
    miner_tickers = {"RIOT", "MARA", "CLSK", "HUT", "WULF", "BITF", "CIFR"}
    miner_moves = []
    for r in gappers:
        if r["ticker"] in miner_tickers:
            miner_moves.append({"ticker": r["ticker"], "gap": _f(r.get("gap_pct"))})
    miner_avg = (sum(m["gap"] for m in miner_moves) / len(miner_moves)
                 if miner_moves else 0)
    cross_asset = {
        "btc_etf_24h_volume_usd": round(btc_etf_total, 0),
        "btc_etf_spike_funds": btc_etf_spike,
        "miner_avg_gap": round(miner_avg, 2),
        "miner_count": len(miner_moves),
        "divergence_signal": btc_etf_spike >= 2 and abs(miner_avg) < 1.0,
        "defi_cascade_count": sum(1 for r in defi_rows
                                  if r.get("stress_label") == "cascade"),
    }

    payload = {
        "generated_at": captured,
        "multi_scanner_count": len(multi_scanner),
        "rotations_count": len(rotations),
        "asymmetry_count": len(asymmetry),
        "multi_scanner": multi_scanner[:20],
        "rotations": rotations[:8],
        "volume_price_asymmetry": asymmetry[:15],
        "cross_asset": cross_asset,
    }
    OUT.write_text(json.dumps(payload, indent=2))

    print(f"intl_edge: multi_scanner={len(multi_scanner)} "
          f"rotations={len(rotations)} asymmetry={len(asymmetry)} "
          f"divergence={'yes' if cross_asset['divergence_signal'] else 'no'} "
          f"defi_cascade={cross_asset['defi_cascade_count']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
