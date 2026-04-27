#!/usr/bin/env python3
"""build_crossborder_convergence.py — flag setups where the same entity is
moving on its home exchange AND its US ADR/dual-listing the same day.

Why this matters: when Petrobras gaps in São Paulo AND PBR gaps in NY in the
same direction with elevated volume on both sides, the move is rarely noise.
Bloomberg surfaces this with a half-dozen windows; we surface it on one page.

Logic:
  For each (foreign_ticker, us_ticker) pair in adr_map.csv:
    1. Pull both listings' last 2-month chart from Yahoo (free).
    2. Compute gap_pct (close vs prev close) and 20d volume ratio per side.
    3. Score 0-4:
         +1 abs(foreign_gap) >= 1.5%
         +1 abs(us_gap)      >= 1.5%
         +1 same direction (both green or both red)
         +1 BOTH sides vol_ratio >= 1.5x
       Score >= 3 = cross-border convergence (TRADE).
       Score == 2 = watch.

Output: cross_border_convergence.csv + docs/data/cross_border_convergence.json
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_crossborder_convergence.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
ADR_MAP = ROOT / "adr_map.csv"
OUT_CSV = ROOT / "cross_border_convergence.csv"
OUT_JSON = ROOT / "docs/data/cross_border_convergence.json"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

UA = "CatalystEdge/1.0"
TIMEOUT = 12


def fetch_chart(ticker: str) -> dict | None:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(ticker)
        + "?range=2mo&interval=1d"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def compute_side(ticker: str) -> dict | None:
    chart = fetch_chart(ticker)
    if not chart:
        return None
    result = (chart.get("chart") or {}).get("result") or []
    if not result:
        return None
    ind = (result[0].get("indicators") or {}).get("quote") or [{}]
    closes = [c for c in (ind[0].get("close") or []) if c is not None]
    vols = [v for v in (ind[0].get("volume") or []) if v is not None]
    if len(closes) < 2:
        return None
    close = closes[-1]
    prev = closes[-2]
    gap_pct = ((close - prev) / prev * 100.0) if prev else 0.0
    vol = vols[-1] if vols else 0
    n = min(20, len(vols))
    avg20 = (sum(vols[-n:]) / n) if n else 0
    vol_ratio = (vol / avg20) if avg20 else 0
    return {
        "ticker": ticker, "close": round(close, 4),
        "prev_close": round(prev, 4), "gap_pct": round(gap_pct, 2),
        "volume": int(vol), "vol_ratio_20d": round(vol_ratio, 2),
    }


def conviction_label(score: int) -> str:
    if score >= 4: return "STRONG"
    if score >= 3: return "TRADE"
    if score >= 2: return "watch"
    return "noise"


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    if not ADR_MAP.exists():
        print(f"adr_map missing: {ADR_MAP}")
        return 1

    pairs: list[dict] = []
    with ADR_MAP.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pairs.append(r)

    rows: list[dict] = []
    trade_count = 0
    watch_count = 0

    for p in pairs:
        ft = p.get("foreign_ticker", "").strip()
        ut = p.get("us_ticker", "").strip()
        if not (ft and ut):
            continue

        foreign = compute_side(ft)
        us = compute_side(ut)
        if not (foreign and us):
            continue

        score = 0
        if abs(foreign["gap_pct"]) >= 1.5: score += 1
        if abs(us["gap_pct"]) >= 1.5: score += 1
        same_dir = (foreign["gap_pct"] >= 0) == (us["gap_pct"] >= 0)
        if same_dir and (abs(foreign["gap_pct"]) >= 0.5 or abs(us["gap_pct"]) >= 0.5):
            score += 1
        if foreign["vol_ratio_20d"] >= 1.5 and us["vol_ratio_20d"] >= 1.5:
            score += 1

        label = conviction_label(score)
        if label == "TRADE" or label == "STRONG":
            trade_count += 1
        elif label == "watch":
            watch_count += 1

        rows.append({
            "captured_at": captured,
            "entity_name": p.get("entity_name", ""),
            "foreign_ticker": ft,
            "foreign_market": p.get("foreign_market", ""),
            "foreign_gap_pct": foreign["gap_pct"],
            "foreign_close": foreign["close"],
            "foreign_vol_ratio": foreign["vol_ratio_20d"],
            "us_ticker": ut,
            "us_listing_type": p.get("us_listing_type", "ADR"),
            "us_gap_pct": us["gap_pct"],
            "us_close": us["close"],
            "us_vol_ratio": us["vol_ratio_20d"],
            "same_direction": same_dir,
            "score": score,
            "conviction": label,
            "sector_gics": p.get("sector_gics", ""),
        })

    # Rank: TRADE/STRONG first, then by abs avg gap
    rows.sort(key=lambda r: (
        -r["score"],
        -((abs(r["foreign_gap_pct"]) + abs(r["us_gap_pct"])) / 2),
    ))

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # JSON for the /cross-border/ page
    payload = {
        "generated_at": captured,
        "pair_count": len(rows),
        "trade_count": trade_count,
        "watch_count": watch_count,
        "top_setups": rows[:25],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    print(f"crossborder: {len(rows)} pairs analyzed | "
          f"TRADE={trade_count} watch={watch_count}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
