#!/usr/bin/env python3
"""Cross-feature interaction lookup classifier.

Replaces additive base_score with a conditional hit-rate lookup table built
from sec_outcome_rows.csv. Each ticker today gets scored against the historical
bucket (form_family × score_band × cap_band × sign) it belongs to.

This is Fix #4 — interaction terms — implemented as a stdlib lookup rather
than a model fit (no sklearn / xgboost dependency, see CLAUDE.md). It still
captures the bulk of the lift from feature crosses because we have an 8k+ row
labeled history and small enough cardinality.

Output: sec_interaction_table.json
  { bucket_key: {n, hit_rate_2pct, wilson_lower, lift_vs_baseline} }

Consumed by the next pipeline run to override base_score on borderline picks.
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
OUT_JSON = ROOT / "sec_interaction_table.json"

MIN_BUCKET = 8
Z = 1.96


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def score_band(s: float) -> str:
    if s < 10:
        return "S<10"
    if s < 15:
        return "S10-14"
    if s < 20:
        return "S15-19"
    return "S20+"


def cap_band(mcap: float) -> str:
    if mcap <= 0:
        return "C?"
    if mcap < 300_000_000:
        return "Cmicro"
    if mcap < 1_000_000_000:
        return "Csmall"
    if mcap < 10_000_000_000:
        return "Cmid"
    return "Clarge"


def form_family(form: str) -> str:
    f = (form or "").strip().upper()
    if f.startswith("424"):
        return "F_424"
    if f.startswith("S-3"):
        return "F_S3"
    if f.startswith("S-1"):
        return "F_S1"
    if f == "8-K":
        return "F_8K"
    if f.startswith("4"):
        return "F_4"
    if f.startswith("13D") or f.startswith("SC 13D"):
        return "F_13D"
    if f.startswith("13G") or f.startswith("SC 13G"):
        return "F_13G"
    if f.startswith("NT"):
        return "F_NT"
    return "F_other"


def wilson_lower(p: float, n: int) -> float:
    if n == 0:
        return 0.0
    phat = p
    denom = 1 + Z * Z / n
    center = phat + Z * Z / (2 * n)
    margin = Z * math.sqrt((phat * (1 - phat) + Z * Z / (4 * n)) / n)
    return max(0.0, (center - margin) / denom)


def main() -> int:
    if not ROWS_CSV.exists():
        print(f"missing {ROWS_CSV.name}")
        return 1

    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows: list[dict[str, str]] = []
    with ROWS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    if not rows:
        OUT_JSON.write_text(json.dumps({"buckets": {}}), encoding="utf-8")
        return 0

    overall = sum(1 for r in rows if r.get("hit_2pct") == "1") / len(rows)

    for r in rows:
        key = "|".join(
            (
                form_family(r.get("form", "")),
                score_band(to_float(r.get("base_score", 0))),
                cap_band(to_float(r.get("market_cap", 0))),
                f"sgn{r.get('catalyst_sign','0')}",
            )
        )
        buckets[key].append(r)

    table: dict[str, dict[str, Any]] = {}
    for key, grp in buckets.items():
        n = len(grp)
        if n < MIN_BUCKET:
            continue
        hits = sum(1 for r in grp if r.get("hit_2pct") == "1")
        p = hits / n
        wl = wilson_lower(p, n)
        avg_alpha = sum(to_float(r.get("alpha_close_pct", 0)) for r in grp) / n
        table[key] = {
            "n": n,
            "hit_rate_2pct": round(p * 100.0, 2),
            "wilson_lower_2pct": round(wl * 100.0, 2),
            "lift_vs_baseline": round((p - overall) * 100.0, 2),
            "avg_alpha_pct": round(avg_alpha, 3),
        }

    out = {
        "overall_baseline_hit_2pct": round(overall * 100.0, 2),
        "min_bucket_size": MIN_BUCKET,
        "n_buckets": len(table),
        "buckets": table,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON.name} buckets={len(table)} baseline={overall*100:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
