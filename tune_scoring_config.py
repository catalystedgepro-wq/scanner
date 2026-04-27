#!/usr/bin/env python3
"""Auto-tune scoring_config.json from outcome summary metrics.

S.5 BLEND (added 2026-04-25):
The script primarily reads sec_outcome_summary.csv (per-list nightly outcomes
from the SEC catalyst pipeline). When agent_outcomes_summary.csv ALSO exists
and contains rows with rows >= 10 for a given list_name, the agent-derived
hit_rate_2pct gets blended into the SEC hit_rate_3pct at a 30% weight:

    blended_hit_rate = 0.7 * sec_hit_rate_3pct + 0.3 * agent_hit_rate_2pct

The agent ledger is small relative to the SEC outcome history, so we cap its
influence at 30% for the first iteration. Bump toward 50% once the agent ledger
crosses 200 rows on any single list_name.

The blend is additive: list_names absent from agent_outcomes_summary.csv get
the unblended SEC value (legacy behavior). If agent_outcomes_summary.csv is
missing or empty, this script behaves identically to its pre-S.5 version.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "scoring_config.json"
SUMMARY_PATH = ROOT / "sec_outcome_summary.csv"
AGENT_SUMMARY_PATH = ROOT / "agent_outcomes_summary.csv"
ROWS_PATH = ROOT / "sec_outcome_rows.csv"
LOG_PATH = ROOT / "scoring_tuning_log.csv"
WALK_FORWARD_PATH = ROOT / "sec_walk_forward_summary.json"

AGENT_BLEND_WEIGHT = 0.30
AGENT_MIN_ROWS = 10
WALK_FORWARD_TRAIN_DAYS = 90
WALK_FORWARD_HOLDOUT_DAYS = 30


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg: dict[str, Any]) -> None:
    cfg["version"] = int(cfg.get("version", 0)) + 1
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_summary() -> dict[str, dict[str, Any]]:
    if not SUMMARY_PATH.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with SUMMARY_PATH.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r.get("list_name", "")] = r
    # Blend agent outcomes if available + non-trivial.
    if AGENT_SUMMARY_PATH.exists():
        try:
            with AGENT_SUMMARY_PATH.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    name = r.get("list_name", "")
                    rows = to_float(r.get("rows"))
                    a_hit = to_float(r.get("hit_rate_2pct"))
                    if rows < AGENT_MIN_ROWS or a_hit <= 0:
                        continue
                    sec_row = out.get(name)
                    if sec_row:
                        s_hit = to_float(sec_row.get("hit_rate_3pct"))
                        blended = ((1 - AGENT_BLEND_WEIGHT) * s_hit
                                   + AGENT_BLEND_WEIGHT * a_hit)
                        sec_row["hit_rate_3pct"] = f"{blended:.2f}"
                        sec_row["_blend_source"] = (
                            f"sec={s_hit:.2f}*0.7 + agent={a_hit:.2f}*0.3 = {blended:.2f}"
                        )
                    else:
                        # New list_name from agent only: surface it for tuning.
                        out[name] = {
                            "list_name": name,
                            "rows": str(int(rows)),
                            "hit_rate_3pct": f"{a_hit:.2f}",
                            "_blend_source": f"agent_only={a_hit:.2f}",
                        }
        except Exception:
            pass
    return out


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def append_log(rows: list[dict[str, Any]]) -> None:
    exists = LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "timestamp_utc",
            "parameter",
            "old_value",
            "new_value",
            "reason",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerows(rows)


def walk_forward_split(list_name: str = "sec_clean_gappers") -> dict[str, Any]:
    """Compute T-90 to T-30 (train) vs T-30 to T (holdout) hit rate split.

    Fix #6 — walk-forward honesty. Tuner should not optimize on the same window
    it reports. Holdout window hit rate is what /trust/ should publish.
    """
    if not ROWS_PATH.exists():
        return {}
    today = dt.date.today()
    holdout_start = today - dt.timedelta(days=WALK_FORWARD_HOLDOUT_DAYS)
    train_start = holdout_start - dt.timedelta(days=WALK_FORWARD_TRAIN_DAYS)
    train_hits = train_n = hold_hits = hold_n = 0
    train_alpha_sum = hold_alpha_sum = 0.0
    train_real_sum = hold_real_sum = 0.0
    with ROWS_PATH.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("list_name", "") != list_name:
                continue
            try:
                d = dt.date.fromisoformat(r.get("list_date", ""))
            except Exception:
                continue
            hit = 1 if r.get("hit_2pct") == "1" else 0
            alpha = to_float(r.get("alpha_close_pct", 0))
            real = to_float(r.get("realistic_pnl_pct", 0))
            if train_start <= d < holdout_start:
                train_n += 1
                train_hits += hit
                train_alpha_sum += alpha
                train_real_sum += real
            elif holdout_start <= d <= today:
                hold_n += 1
                hold_hits += hit
                hold_alpha_sum += alpha
                hold_real_sum += real
    out = {
        "list_name": list_name,
        "train_window_days": WALK_FORWARD_TRAIN_DAYS,
        "holdout_window_days": WALK_FORWARD_HOLDOUT_DAYS,
        "train_n": train_n,
        "train_hit_rate_2pct": round(train_hits / train_n * 100.0, 2) if train_n else 0.0,
        "train_avg_alpha_pct": round(train_alpha_sum / train_n, 3) if train_n else 0.0,
        "train_avg_realistic_pnl_pct": round(train_real_sum / train_n, 3) if train_n else 0.0,
        "holdout_n": hold_n,
        "holdout_hit_rate_2pct": round(hold_hits / hold_n * 100.0, 2) if hold_n else 0.0,
        "holdout_avg_alpha_pct": round(hold_alpha_sum / hold_n, 3) if hold_n else 0.0,
        "holdout_avg_realistic_pnl_pct": (
            round(hold_real_sum / hold_n, 3) if hold_n else 0.0
        ),
        "computed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    out["decay_flag"] = (
        out["train_hit_rate_2pct"] - out["holdout_hit_rate_2pct"] >= 5.0
        if train_n and hold_n
        else False
    )
    return out


def main() -> int:
    cfg = load_config()
    if not cfg.get("auto_tune", {}).get("enabled", False):
        return 0

    wf = walk_forward_split("sec_clean_gappers")
    if wf:
        WALK_FORWARD_PATH.write_text(json.dumps(wf, indent=2), encoding="utf-8")
        print(
            f"walk_forward train={wf['train_hit_rate_2pct']}% (n={wf['train_n']}) "
            f"holdout={wf['holdout_hit_rate_2pct']}% (n={wf['holdout_n']}) "
            f"decay_flag={wf['decay_flag']}"
        )

    summary = load_summary()
    min_rows = int(cfg["auto_tune"]["min_rows_required"])
    targets = cfg["auto_tune"]["target_hit_rate_3pct"]
    steps = cfg["auto_tune"]["step_limits"]
    changes: list[dict[str, Any]] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    def metric(list_name: str) -> tuple[int, float]:
        row = summary.get(list_name, {})
        return int(to_float(row.get("rows"))), to_float(row.get("hit_rate_3pct"))

    # Tune clean gappers thresholds.
    g_rows, g_hit = metric("sec_clean_gappers")
    g_target = float(targets.get("sec_clean_gappers", 25.0))
    g_score = int(cfg["clean_presets"]["gappers"]["min_score"])
    g_rec = int(cfg["clean_presets"]["gappers"]["max_recency_min"])
    if g_rows >= min_rows:
        # F-6 fix: proportional step scaling — larger miss = larger adjustment.
        # Clamped to 2x base step to prevent overshoot.
        miss_ratio = min(2.0, max(1.0, abs(g_hit - g_target) / max(1, g_target)))
        if g_hit < g_target:
            # CORRECTED (2026-04-24): hit rate below target means signal is TOO
            # WEAK — picks are low-quality. RAISE min_score to tighten filter.
            # Also TIGHTEN recency (fresher = better) rather than loosen.
            # Empirical: score 10-15 bucket was 39.8% hit, score 15-20 was 45.1%.
            # Earlier logic moved us BACKWARDS on every tune cycle.
            base_score_step = int(steps["gappers_min_score"])
            base_rec_step = int(steps["gappers_max_recency_min"])
            new_score = min(25, g_score + int(base_score_step * miss_ratio))
            new_rec = max(240, g_rec - int(base_rec_step * miss_ratio))
            if new_score != g_score:
                changes.append(
                    {
                        "timestamp_utc": now,
                        "parameter": "clean_presets.gappers.min_score",
                        "old_value": g_score,
                        "new_value": new_score,
                        "reason": f"hit_rate_3pct {g_hit:.2f} < target {g_target:.2f}",
                    }
                )
                cfg["clean_presets"]["gappers"]["min_score"] = new_score
            if new_rec != g_rec:
                changes.append(
                    {
                        "timestamp_utc": now,
                        "parameter": "clean_presets.gappers.max_recency_min",
                        "old_value": g_rec,
                        "new_value": new_rec,
                        "reason": f"hit_rate_3pct {g_hit:.2f} < target {g_target:.2f}",
                    }
                )
                cfg["clean_presets"]["gappers"]["max_recency_min"] = new_rec
        elif g_hit > g_target + 7:
            # CORRECTED (2026-04-24): we're over-achieving — can safely lower
            # threshold to include more picks. Floor enforced at
            # score_min_floor_for_publication (Fix #1, default 15) so the
            # /scanner/ trust strip stays consistent with the published list.
            score_floor = int(cfg.get("score_min_floor_for_publication", 15))
            new_score = max(score_floor, g_score - int(steps["gappers_min_score"]))
            new_rec = min(1440, g_rec + int(steps["gappers_max_recency_min"]))
            if new_score != g_score:
                changes.append(
                    {
                        "timestamp_utc": now,
                        "parameter": "clean_presets.gappers.min_score",
                        "old_value": g_score,
                        "new_value": new_score,
                        "reason": f"hit_rate_3pct {g_hit:.2f} > target+7 {g_target+7:.2f}",
                    }
                )
                cfg["clean_presets"]["gappers"]["min_score"] = new_score
            if new_rec != g_rec:
                changes.append(
                    {
                        "timestamp_utc": now,
                        "parameter": "clean_presets.gappers.max_recency_min",
                        "old_value": g_rec,
                        "new_value": new_rec,
                        "reason": f"hit_rate_3pct {g_hit:.2f} > target+7 {g_target+7:.2f}",
                    }
                )
                cfg["clean_presets"]["gappers"]["max_recency_min"] = new_rec

    # Tune combined news weight against combined list performance.
    c_rows, c_hit = metric("combined_priority")
    c_target = float(targets.get("combined_priority", 20.0))
    news_w = to_float(cfg["news"]["combined_news_weight"])
    step = float(steps["combined_news_weight"])
    if c_rows >= min_rows:
        if c_hit < c_target:
            new_w = clamp(news_w - step, 0.4, 1.4)
            if new_w != news_w:
                changes.append(
                    {
                        "timestamp_utc": now,
                        "parameter": "news.combined_news_weight",
                        "old_value": news_w,
                        "new_value": new_w,
                        "reason": f"combined hit_rate_3pct {c_hit:.2f} < target {c_target:.2f}",
                    }
                )
                cfg["news"]["combined_news_weight"] = round(new_w, 4)
        elif c_hit > c_target + 5:
            new_w = clamp(news_w + step, 0.4, 1.4)
            if new_w != news_w:
                changes.append(
                    {
                        "timestamp_utc": now,
                        "parameter": "news.combined_news_weight",
                        "old_value": news_w,
                        "new_value": new_w,
                        "reason": f"combined hit_rate_3pct {c_hit:.2f} > target+5 {c_target+5:.2f}",
                    }
                )
                cfg["news"]["combined_news_weight"] = round(new_w, 4)

    if changes:
        save_config(cfg)
        append_log(changes)

    print(f"tune_changes={len(changes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
