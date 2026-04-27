#!/usr/bin/env python3
"""build_btc_mining.py — Bitcoin mining economics (difficulty + hashrate).

Bitcoin miner fundamentals drive MARA, RIOT, CLSK, CIFR, HUT, HIVE, BITF,
BTDR, IREN equity prices with 70-85% correlation on a 5-day lag. Rising
difficulty + stable/rising hashrate = margin compression; falling
difficulty = miner bull case.

Trade uses:
- Next difficulty adjustment > +5%: miner equities face margin squeeze,
  short/underweight MARA/RIOT on the 1-2 day before adjustment.
- Hashrate dropping > 10% week/week (miner capitulation): historically
  marks local BTC bottoms; long crypto miners for mean reversion.
- Difficulty decrease > 3%: rare "easy money" window for miners; long
  CLSK/MARA outperforms BTC 2-4x over next 14 days.
- Progress to retarget > 90% + positive expected adjustment: pre-position
  hedges before forced recalibration.

Source: mempool.space/api/v1 (free, no key, public Bitcoin node stats).
- /difficulty-adjustment — current epoch progress + estimated next change
- /mining/hashrate/3m — 90-day network hashrate (EH/s)
- /mining/difficulty-adjustments/3m — historical adjustment multipliers

Output: btc_mining.csv
Columns: date, hashrate_ehs, difficulty, adjustment_pct, captured_at

Also emits snapshot stdout with the current adjustment-in-progress state.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "btc_mining.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://mempool.space/api/v1"


def fetch_json(path: str) -> dict | list | None:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"btc_mining: {path} -> {e}")
        return None


def main() -> None:
    adj = fetch_json("/difficulty-adjustment") or {}
    hashrates = fetch_json("/mining/hashrate/3m") or {}
    adj_history = fetch_json("/mining/difficulty-adjustments/3m") or []

    # Build date -> hashrate (EH/s)
    hr_series = (hashrates or {}).get("hashrates") or []
    hr_by_date: dict[str, float] = {}
    for h in hr_series:
        ts = h.get("timestamp")
        rate = h.get("avgHashrate")
        if ts is None or rate is None:
            continue
        try:
            d = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).date().isoformat()
            hr_by_date[d] = float(rate) / 1e18  # H/s -> EH/s
        except (ValueError, TypeError):
            continue

    # Build date -> (difficulty, adjustment_pct) from history
    # Entry: [timestamp, block_height, difficulty, adjustment_multiplier]
    diff_by_date: dict[str, tuple[float, float]] = {}
    for row in adj_history or []:
        if not isinstance(row, list) or len(row) < 4:
            continue
        try:
            ts, _bh, difficulty, mult = row[0], row[1], row[2], row[3]
            d = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).date().isoformat()
            pct = (float(mult) - 1.0) * 100.0
            diff_by_date[d] = (float(difficulty), pct)
        except (ValueError, TypeError):
            continue

    # Merge: union of dates, prefer nearest difficulty (difficulty only
    # changes every ~2 weeks, so carry-forward)
    all_dates = sorted(set(hr_by_date) | set(diff_by_date))
    if not all_dates and OUT_CSV.exists() and OUT_CSV.stat().st_size > 150:
        print(f"btc_mining: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    last_diff = 0.0
    last_pct = 0.0
    for d in all_dates:
        if d in diff_by_date:
            last_diff, last_pct = diff_by_date[d]
        rows.append({
            "date": d,
            "hashrate_ehs": f"{hr_by_date.get(d, 0.0):.2f}",
            "difficulty": f"{last_diff:.0f}" if last_diff else "",
            "adjustment_pct": f"{last_pct:+.2f}" if last_pct else "",
        })

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "hashrate_ehs", "difficulty",
                        "adjustment_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Snapshot print
    progress = adj.get("progressPercent", 0)
    next_change = adj.get("difficultyChange", 0)
    remaining = adj.get("remainingBlocks", 0)
    prev = adj.get("previousRetarget", 0)
    latest_hr = rows[-1]["hashrate_ehs"] if rows else "?"
    print(f"btc_mining: {len(rows)} days | hashrate {latest_hr} EH/s | "
          f"epoch {progress:.1f}% ({remaining} blocks left) | next "
          f"adj {next_change:+.2f}% | prev {prev:+.2f}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
