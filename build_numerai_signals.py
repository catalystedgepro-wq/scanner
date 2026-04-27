#!/usr/bin/env python3
"""build_numerai_signals.py — transform our convergence + DCF output into
the Numerai Signals weekly submission format.

Numerai Signals requires per-ticker predictions in CSV with:
    bloomberg_ticker,signal,friday_date

Signal must be a [0, 1] float where 0 = most bearish, 1 = most bullish.
Numerai internally ranks signals and pays stake-weighted for accuracy.

We translate our convergence score into that [0,1] space:
    1. Rank all tickers in convergence_alerts.csv by score
    2. Fractional rank becomes the signal (percentile rank / N)
    3. Blend DCF grade adjustment:  A=+0.10, B=+0.05, C=0, D=-0.05, F=-0.10
    4. Clip to [0.001, 0.999] (Numerai requires non-extremes)
    5. Snap friday_date to the next Friday for this week's submission

Output: numerai_signals.csv
Also writes numerai_manifest.json with submission metadata.

Reference: https://docs.numer.ai/numerai-signals/data
Stdlib only.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "numerai_signals.csv"
OUT_MANIFEST = ROOT / "docs/data/numerai_signals_manifest.json"

CONVERGENCE = ROOT / "convergence_alerts.csv"
DCF = ROOT / "sec_xbrl_dcf.csv"


def next_friday(today: dt.date | None = None) -> dt.date:
    if today is None:
        today = dt.date.today()
    days_ahead = (4 - today.weekday()) % 7  # Monday=0 ... Friday=4
    if days_ahead == 0:
        return today  # already Friday
    return today + dt.timedelta(days=days_ahead)


def load_convergence_rank() -> list[tuple[str, int]]:
    if not CONVERGENCE.exists():
        return []
    rows: list[tuple[str, int]] = []
    with CONVERGENCE.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            if not t or not t.isalpha() or not (1 <= len(t) <= 5):
                continue
            try:
                score = int(float(r.get("convergence_score") or 0))
            except (TypeError, ValueError):
                continue
            rows.append((t, score))
    # Sort ascending so rank 0 = most bearish, rank N-1 = most bullish
    rows.sort(key=lambda x: x[1])
    return rows


def load_dcf_grades() -> dict[str, str]:
    out: dict[str, str] = {}
    if not DCF.exists():
        return out
    with DCF.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            g = (r.get("dcf_grade") or "").strip().upper()
            if t and g:
                out[t] = g
    return out


def main() -> int:
    ranked = load_convergence_rank()
    if not ranked:
        print("numerai_signals: convergence_alerts.csv empty — abort")
        return 1
    dcf_grades = load_dcf_grades()
    total = len(ranked)

    dcf_adj = {"A": 0.10, "B": 0.05, "C": 0.0, "D": -0.05, "F": -0.10}

    friday = next_friday()
    rows: list[dict[str, str]] = []
    dcf_enriched = 0

    for i, (ticker, _score) in enumerate(ranked):
        # Percentile rank in [0, 1]
        pct = (i + 0.5) / total
        # DCF tilt
        grade = dcf_grades.get(ticker, "")
        adj = dcf_adj.get(grade, 0.0)
        if adj != 0.0:
            dcf_enriched += 1
        signal = max(0.001, min(0.999, pct + adj))
        # Numerai uses bloomberg_ticker; domestic US stocks append " US"
        rows.append({
            "bloomberg_ticker": f"{ticker} US",
            "signal": f"{signal:.4f}",
            "friday_date": friday.isoformat().replace("-", ""),  # YYYYMMDD
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bloomberg_ticker", "signal", "friday_date"])
        w.writeheader()
        w.writerows(rows)

    # Manifest for dashboard consumption
    OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "friday_date": friday.isoformat(),
        "total_signals": total,
        "dcf_enriched": dcf_enriched,
        "upload_url": "https://signals.numer.ai/submissions",
        "model_notes": "rank-percentile convergence_score + DCF grade tilt ±0.10",
        "top_10_bullish": [r["bloomberg_ticker"] for r in rows[-10:][::-1]],
        "top_10_bearish": [r["bloomberg_ticker"] for r in rows[:10]],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2))

    print(f"numerai_signals: {total} rows | friday={friday} | dcf_enriched={dcf_enriched}")
    print(f"  top bullish: {', '.join(r['bloomberg_ticker'] for r in rows[-5:][::-1])}")
    print(f"  top bearish: {', '.join(r['bloomberg_ticker'] for r in rows[:5])}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
