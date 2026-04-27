#!/usr/bin/env python3
"""Loser-cluster analysis: find features that separate wins from losses.

Reads sec_outcome_rows.csv, runs a stdlib decision-tree splitter on engineered
features (form, score band, gap direction, catalyst sign, market-cap band),
and emits sec_loser_clusters.json describing the worst-performing buckets.

This is Fix #8 in the loss-rate diagnostic sprint. The output is consumed by
the /trust/ page so visitors see EXACTLY what bins drag hit rate down.

Pure Python — no sklearn, no pandas.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
ROWS_CSV = ROOT / "sec_outcome_rows.csv"
OUT_JSON = ROOT / "sec_loser_clusters.json"
OUT_CSV = ROOT / "sec_loser_clusters.csv"

MIN_BUCKET = 10  # ignore buckets thinner than this — Wilson-stable floor


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def score_band(s: float) -> str:
    if s < 10:
        return "score_lt10"
    if s < 15:
        return "score_10_14"
    if s < 20:
        return "score_15_19"
    return "score_20plus"


def gap_band(gap: float) -> str:
    if gap < -2:
        return "gap_down_lt_-2"
    if gap < 0:
        return "gap_down_0to-2"
    if gap < 2:
        return "gap_flat_0to2"
    if gap < 5:
        return "gap_up_2to5"
    return "gap_up_gt5"


def cap_band(mcap: float) -> str:
    if mcap <= 0:
        return "cap_unknown"
    if mcap < 300_000_000:
        return "cap_micro_lt300m"
    if mcap < 1_000_000_000:
        return "cap_small_300m_1b"
    if mcap < 10_000_000_000:
        return "cap_mid_1b_10b"
    return "cap_large_gt10b"


def form_family(form: str) -> str:
    f = (form or "").strip().upper()
    if f.startswith("424"):
        return "form_424_dilution"
    if f.startswith("S-3"):
        return "form_S3_shelf"
    if f.startswith("S-1"):
        return "form_S1_offering"
    if f == "8-K":
        return "form_8K_general"
    if f.startswith("4"):
        return "form_4_insider"
    if f.startswith("13D") or f.startswith("SC 13D"):
        return "form_13D_activist"
    if f.startswith("13G") or f.startswith("SC 13G"):
        return "form_13G_passive"
    if f.startswith("NT"):
        return "form_NT_late"
    return "form_other"


def wilson_lower(p: float, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound (95% CI by default).

    Stable for small n where naive proportion is misleading.
    """
    if n == 0:
        return 0.0
    phat = p
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (center - margin) / denom)


def main() -> int:
    if not ROWS_CSV.exists():
        print(f"missing {ROWS_CSV.name}")
        return 1

    rows: list[dict[str, str]] = []
    with ROWS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    if not rows:
        OUT_JSON.write_text(
            json.dumps({"buckets": [], "n": 0, "note": "no_rows"}), encoding="utf-8"
        )
        return 0

    # Engineer feature buckets and compute hit_2pct in each.
    feat_buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        score = to_float(r.get("base_score", 0))
        gap = to_float(r.get("gap_next_open_pct", 0))
        mcap = to_float(r.get("market_cap", 0))
        form = r.get("form", "")
        sign = r.get("catalyst_sign", "0")
        for label in (
            score_band(score),
            gap_band(gap),
            cap_band(mcap),
            form_family(form),
            f"sign_{sign}",
        ):
            feat_buckets[label].append(r)
        # Cross-features — top interactions only to avoid combinatorial blowup.
        feat_buckets[f"{score_band(score)}|{gap_band(gap)}"].append(r)
        feat_buckets[f"{form_family(form)}|{cap_band(mcap)}"].append(r)
        feat_buckets[f"sign_{sign}|{score_band(score)}"].append(r)

    overall_hit2 = sum(1 for r in rows if r.get("hit_2pct") == "1") / len(rows)

    summary: list[dict[str, Any]] = []
    for label, group in feat_buckets.items():
        n = len(group)
        if n < MIN_BUCKET:
            continue
        hits = sum(1 for r in group if r.get("hit_2pct") == "1")
        net_hits = sum(1 for r in group if r.get("hit_2pct_net", "0") == "1")
        wilson_lo = wilson_lower(hits / n, n) * 100.0
        avg_close = sum(to_float(r.get("next_day_close_pct", 0)) for r in group) / n
        avg_alpha = sum(to_float(r.get("alpha_close_pct", 0)) for r in group) / n
        avg_realistic = sum(to_float(r.get("realistic_pnl_pct", 0)) for r in group) / n
        summary.append(
            {
                "bucket": label,
                "n": n,
                "hit_rate_2pct": round(hits / n * 100.0, 2),
                "hit_rate_2pct_net": round(net_hits / n * 100.0, 2),
                "hit_rate_2pct_wilson_lo": round(wilson_lo, 2),
                "delta_vs_overall": round(hits / n * 100.0 - overall_hit2 * 100.0, 2),
                "avg_close_pct": round(avg_close, 3),
                "avg_alpha_pct": round(avg_alpha, 3),
                "avg_realistic_pnl_pct": round(avg_realistic, 3),
            }
        )

    # Worst buckets first — by Wilson lower bound for honesty.
    summary.sort(key=lambda x: x["hit_rate_2pct_wilson_lo"])
    worst = summary[:15]
    best = sorted(summary, key=lambda x: -x["hit_rate_2pct_wilson_lo"])[:15]

    out = {
        "n_rows": len(rows),
        "overall_hit_rate_2pct": round(overall_hit2 * 100.0, 2),
        "min_bucket_size": MIN_BUCKET,
        "worst_buckets": worst,
        "best_buckets": best,
        "all_buckets": summary,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        if summary:
            w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            w.writeheader()
            w.writerows(summary)
    print(
        f"wrote {OUT_JSON.name} buckets={len(summary)} "
        f"worst_lo={worst[0]['hit_rate_2pct_wilson_lo']}% "
        f"best_lo={best[0]['hit_rate_2pct_wilson_lo']}%"
        if summary
        else f"wrote {OUT_JSON.name} (empty)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
