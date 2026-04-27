#!/usr/bin/env python3
"""tune_gap_scanner.py — Auto-tune gap scanner parameters from outcome data.

Runs in the morning pipeline after evaluate_gap_outcomes.py (EOD previous day).
Reads gap_outcome_log.csv, analyzes what's working vs failing, adjusts
gap_scanner_config.json, and writes a human-readable tuning note for the
newsletter performance section.

Logic:
  - Need ≥ 10 evaluated alerts to tune (avoid over-fitting small samples)
  - Compares win rates across vol_ratio bands and gap_pct bands
  - Raises thresholds when low-end setups underperform
  - Loosens thresholds when tightening too much causes zero alerts
  - Logs every change with reason so the newsletter can explain it honestly
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Any

ROOT           = Path(__file__).parent
OUTCOME_LOG    = ROOT / "gap_outcome_log.csv"
SUMMARY_JSON   = ROOT / "gap_outcome_summary.json"
CONFIG_FILE    = ROOT / "gap_scanner_config.json"
TUNING_LOG     = ROOT / "gap_tuning_log.csv"

MIN_SAMPLE     = 10    # minimum alerts needed before tuning
TARGET_HIT10   = 50.0  # target hit rate for >=10% within 2hrs (%)
WEAK_HIT10     = 35.0  # below this = underperforming, tighten
STRONG_HIT10   = 65.0  # above this = can loosen slightly

# Parameter bounds
BOUNDS = {
    "gap_threshold_pct": (1.0, 3.0),
    "min_vol_ratio":     (1.5, 4.0),
    "fade_floor":        (0.75, 0.95),
}

STEP = {
    "gap_threshold_pct": 0.25,
    "min_vol_ratio":     0.25,
    "fade_floor":        0.05,
}


def to_f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {
            "gap_threshold_pct": 1.0,
            "min_volume":        50_000,
            "min_vol_ratio":     1.5,
            "fade_floor":        0.85,
            "min_price":         0.50,
            "max_price":         10.00,
            "last_tuned":        None,
            "tuning_note":       "Default parameters",
        }
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_outcomes() -> list[dict]:
    if not OUTCOME_LOG.exists():
        return []
    try:
        return list(csv.DictReader(OUTCOME_LOG.open(newline="", encoding="utf-8")))
    except Exception:
        return []


def hit_rate(rows: list[dict], field: str = "hit_10pct") -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get(field) == "1") / len(rows) * 100


def analyze_bands(outcomes: list[dict]) -> dict:
    """Break outcomes into bands to find what's working vs failing."""

    # Vol ratio bands
    low_vol   = [r for r in outcomes if to_f(r.get("vol_ratio", 0)) < 2.5]
    high_vol  = [r for r in outcomes if to_f(r.get("vol_ratio", 0)) >= 2.5]

    # Gap size bands
    small_gap = [r for r in outcomes if to_f(r.get("gap_pct", 0)) < 3.0]
    large_gap = [r for r in outcomes if to_f(r.get("gap_pct", 0)) >= 3.0]

    # Fade outcomes (proxied by max_2hr vs gap_pct)
    faded     = [r for r in outcomes
                 if to_f(r.get("max_2hr_pct", 0)) < to_f(r.get("gap_pct", 0)) * 0.5]

    return {
        "low_vol_hit10":   hit_rate(low_vol),
        "high_vol_hit10":  hit_rate(high_vol),
        "small_gap_hit10": hit_rate(small_gap),
        "large_gap_hit10": hit_rate(large_gap),
        "fade_rate":       len(faded) / len(outcomes) * 100 if outcomes else 0,
        "n_low_vol":       len(low_vol),
        "n_high_vol":      len(high_vol),
        "n_small_gap":     len(small_gap),
        "n_large_gap":     len(large_gap),
    }


def clamp(val: float, param: str) -> float:
    lo, hi = BOUNDS[param]
    return max(lo, min(hi, val))


def main() -> int:
    outcomes = load_outcomes()

    if len(outcomes) < MIN_SAMPLE:
        print(f"tune_gap_scanner: only {len(outcomes)} outcomes — need {MIN_SAMPLE} to tune")
        # Write a building note so newsletter shows something
        cfg = load_config()
        cfg["tuning_note"] = (
            f"Building track record ({len(outcomes)}/{MIN_SAMPLE} alerts evaluated). "
            f"Parameters unchanged — tuning begins after {MIN_SAMPLE} verified outcomes."
        )
        cfg["week_hit_rate"]   = None
        cfg["week_alert_count"] = len(outcomes)
        save_config(cfg)
        return 0

    cfg      = load_config()
    changes  = []
    today    = dt.date.today().isoformat()

    # Last 7 days for weekly assessment
    cutoff_7d  = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    cutoff_30d = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    week_outs  = [r for r in outcomes if r.get("alert_date", "") >= cutoff_7d]
    month_outs = [r for r in outcomes if r.get("alert_date", "") >= cutoff_30d]

    week_hit10  = hit_rate(week_outs)
    month_hit10 = hit_rate(month_outs)
    overall_hit = hit_rate(outcomes)

    bands = analyze_bands(month_outs if len(month_outs) >= MIN_SAMPLE else outcomes)

    print(f"tune_gap_scanner: {len(outcomes)} total outcomes")
    print(f"  week hit10={week_hit10:.1f}%  month hit10={month_hit10:.1f}%  overall={overall_hit:.1f}%")
    print(f"  bands: low_vol={bands['low_vol_hit10']:.1f}%  high_vol={bands['high_vol_hit10']:.1f}%")
    print(f"         small_gap={bands['small_gap_hit10']:.1f}%  large_gap={bands['large_gap_hit10']:.1f}%")
    print(f"         fade_rate={bands['fade_rate']:.1f}%")

    # ── Tuning rules ──────────────────────────────────────────────────────

    # Rule 1: overall underperforming → raise vol_ratio filter
    if week_hit10 < WEAK_HIT10 and bands["low_vol_hit10"] < bands["high_vol_hit10"] - 10:
        old = cfg["min_vol_ratio"]
        cfg["min_vol_ratio"] = clamp(old + STEP["min_vol_ratio"], "min_vol_ratio")
        if cfg["min_vol_ratio"] != old:
            changes.append(
                f"Raised vol filter {old:.2f}× → {cfg['min_vol_ratio']:.2f}× "
                f"(low-vol setups hit {bands['low_vol_hit10']:.0f}% vs "
                f"high-vol {bands['high_vol_hit10']:.0f}%)"
            )

    # Rule 2: small gaps underperforming → raise gap threshold
    if (bands["small_gap_hit10"] < WEAK_HIT10
            and bands["small_gap_hit10"] < bands["large_gap_hit10"] - 10
            and bands["n_small_gap"] >= 5):
        old = cfg["gap_threshold_pct"]
        cfg["gap_threshold_pct"] = clamp(old + STEP["gap_threshold_pct"], "gap_threshold_pct")
        if cfg["gap_threshold_pct"] != old:
            changes.append(
                f"Raised gap threshold {old:.2f}% → {cfg['gap_threshold_pct']:.2f}% "
                f"(small gaps hit {bands['small_gap_hit10']:.0f}% vs "
                f"large {bands['large_gap_hit10']:.0f}%)"
            )

    # Rule 3: high fade rate → tighten fade floor
    if bands["fade_rate"] > 40 and cfg["fade_floor"] < BOUNDS["fade_floor"][1]:
        old = cfg["fade_floor"]
        cfg["fade_floor"] = clamp(old + STEP["fade_floor"], "fade_floor")
        if cfg["fade_floor"] != old:
            changes.append(
                f"Tightened fade floor {old:.2f} → {cfg['fade_floor']:.2f} "
                f"({bands['fade_rate']:.0f}% of alerts faded below half their gap)"
            )

    # Rule 4: performing well + thresholds are above default → loosen slightly
    if week_hit10 >= STRONG_HIT10 and len(week_outs) >= 5:
        if cfg["min_vol_ratio"] > BOUNDS["min_vol_ratio"][0]:
            old = cfg["min_vol_ratio"]
            cfg["min_vol_ratio"] = clamp(old - STEP["min_vol_ratio"], "min_vol_ratio")
            if cfg["min_vol_ratio"] != old:
                changes.append(
                    f"Loosened vol filter {old:.2f}× → {cfg['min_vol_ratio']:.2f}× "
                    f"(strong week at {week_hit10:.0f}% — expanding coverage)"
                )

    # ── Build tuning note ─────────────────────────────────────────────────
    if week_hit10 >= TARGET_HIT10:
        perf_label = "on target"
        perf_tone  = "This week's gap alerts performed well."
    elif week_hit10 >= WEAK_HIT10:
        perf_label = "below target"
        perf_tone  = "Performance was below our 50% target this week."
    else:
        perf_label = "weak week"
        perf_tone  = "This was a tough week for gap setups."

    if changes:
        change_text = " | ".join(changes)
        note = (
            f"{perf_tone} "
            f"Week hit rate: {week_hit10:.0f}% ({len(week_outs)} alerts). "
            f"Adjustments made: {change_text}."
        )
    else:
        note = (
            f"{perf_tone} "
            f"Week hit rate: {week_hit10:.0f}% ({len(week_outs)} alerts). "
            f"No parameter changes — current thresholds are holding."
        )

    cfg["last_tuned"]       = today
    cfg["tuning_note"]      = note
    cfg["week_hit_rate"]    = round(week_hit10, 1)
    cfg["month_hit_rate"]   = round(month_hit10, 1)
    cfg["overall_hit_rate"] = round(overall_hit, 1)
    cfg["week_alert_count"] = len(week_outs)
    save_config(cfg)

    # ── Append to tuning log ──────────────────────────────────────────────
    log_fields = [
        "date", "week_hit10", "month_hit10", "overall_hit10",
        "week_alerts", "gap_threshold_pct", "min_vol_ratio", "fade_floor",
        "changes",
    ]
    log_exists = TUNING_LOG.exists()
    with TUNING_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=log_fields)
        if not log_exists:
            w.writeheader()
        w.writerow({
            "date":               today,
            "week_hit10":         round(week_hit10, 1),
            "month_hit10":        round(month_hit10, 1),
            "overall_hit10":      round(overall_hit, 1),
            "week_alerts":        len(week_outs),
            "gap_threshold_pct":  cfg["gap_threshold_pct"],
            "min_vol_ratio":      cfg["min_vol_ratio"],
            "fade_floor":         cfg["fade_floor"],
            "changes":            " | ".join(changes) if changes else "none",
        })

    if changes:
        print(f"  {len(changes)} adjustment(s) made:")
        for c in changes:
            print(f"    • {c}")
    else:
        print("  no changes — parameters holding")

    print(f"  note: {note[:100]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
