#!/usr/bin/env python3
"""build_compelling_subject.py — Generate a high-open-rate newsletter subject line.

Reads pipeline output data and selects the most compelling template based on
what actually happened today: real alert fires, gap sizes, squeeze setups.

Priority (highest impact first):
  1. Alert fired with >30% gap  -> "$TICKER +{gap}% -- caught at {time} ET before the move"
  2. Multiple gappers           -> "{N} pre-market gap plays for {date} -- scanner results"
  3. Squeeze candidate          -> "$TICKER is COILED -- short interest + catalyst = setup"
  4. Default (top pick)         -> "SEC Scanner: {top_pick} + {N} plays for {date}"

Output: newsletter_subject.txt

Optional env var: NEWSLETTER_URL
"""
from __future__ import annotations

import csv
import datetime
import json
import os
from pathlib import Path

ROOT    = Path(__file__).parent
OUTPUT  = ROOT / "newsletter_subject.txt"


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_csv(name: str) -> list[dict]:
    p = ROOT / name
    if not p.exists():
        return []
    try:
        with p.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def load_today_alerts() -> list[dict]:
    """Return alerts from gap_alert_log.csv for today only."""
    today = datetime.date.today().isoformat()
    rows  = load_csv("gap_alert_log.csv")
    return [r for r in rows if r.get("alert_date") == today]


# ── Subject generator ─────────────────────────────────────────────────────────

def build_subject() -> str:
    today     = datetime.date.today()
    date_str  = today.strftime("%b %-d")

    picks     = load_picks()
    gap_rows  = load_csv("gap_scanner_top.csv")
    sq_rows   = load_csv("squeeze_candidates.csv")
    alerts    = load_today_alerts()

    top_pick  = picks.get("top_pick", "")
    gappers   = int(picks.get("gapper_count", 0) or 0)

    # ── Priority 1: Alert fired with >30% gap ────────────────────────────────
    big_alerts = []
    for row in alerts:
        try:
            gap_pct = float(row.get("gap_pct") or 0)
        except (TypeError, ValueError):
            gap_pct = 0.0
        if gap_pct >= 30:
            big_alerts.append((gap_pct, row))

    if big_alerts:
        big_alerts.sort(key=lambda x: -x[0])
        best_gap, best_row = big_alerts[0]
        ticker     = best_row.get("ticker", "").upper()
        alert_time = best_row.get("alert_time", "")
        time_str   = f"{alert_time} ET" if alert_time else "before the move"
        subject = f"${ticker} +{best_gap:.0f}% -- caught at {time_str} before the move"
        print(f"build_compelling_subject: template=big_alert subject={subject!r}")
        return subject

    # ── Priority 2: Best gapper from gap_scanner_top.csv ─────────────────────
    if gap_rows:
        # Find biggest gap in the scanner
        best_gap_row = None
        best_gap_pct = 0.0
        for row in gap_rows:
            try:
                g = float(row.get("gap_pct", row.get("gap", 0)) or 0)
            except (TypeError, ValueError):
                g = 0.0
            if g > best_gap_pct:
                best_gap_pct = g
                best_gap_row = row

        if gappers >= 3 or (best_gap_row and best_gap_pct >= 10):
            n       = gappers if gappers >= 3 else len(gap_rows)
            subject = f"{n} pre-market gap plays for {date_str} -- scanner results"
            print(f"build_compelling_subject: template=multi_gapper subject={subject!r}")
            return subject

    # ── Priority 3: Squeeze / coiled candidate ────────────────────────────────
    coiled_tickers = [
        r.get("ticker", "").upper()
        for r in sq_rows
        if r.get("stage") in ("COILED", "IGNITION")
    ]
    if coiled_tickers:
        ticker  = coiled_tickers[0]
        subject = f"${ticker} is COILED -- short interest + catalyst = setup"
        print(f"build_compelling_subject: template=squeeze subject={subject!r}")
        return subject

    # ── Priority 4: Default ───────────────────────────────────────────────────
    n = gappers + int(picks.get("value_count", 0) or 0) + int(picks.get("moat_count", 0) or 0)
    if top_pick and n > 0:
        subject = f"SEC Scanner: ${top_pick} + {n} plays for {date_str}"
    elif top_pick:
        subject = f"Today's top SEC catalyst: ${top_pick} -- {date_str}"
    else:
        subject = f"SEC Catalyst Scan -- {date_str} pre-market results"

    print(f"build_compelling_subject: template=default subject={subject!r}")
    return subject


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    subject = build_subject()
    OUTPUT.write_text(subject, encoding="utf-8")
    print(f"build_compelling_subject: wrote to {OUTPUT.name}")
    print(f"  Subject: {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
