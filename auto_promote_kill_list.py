#!/usr/bin/env python3
"""Closed-loop kill-list promoter.

Reads sec_loser_clusters.json (built by analyze_loser_clusters.py) and
auto-extends scoring_config.json:clean_presets.blocked_forms +
clean_presets.blocked_when_largecap when historical buckets prove
persistently bad.

Promotion rules (intentionally conservative — anti-overfit):
  * Bucket must have n >= MIN_PROMOTION_N (default 25)
  * Wilson lower bound must be <= MAX_WILSON_LOWER (default 25%)
  * Bucket label must be a form-only or form|cap_large_gt10b cross
  * Total kill-list growth capped at MAX_NEW_PER_CYCLE (default 2 per run)
  * Existing kill-listed forms are skipped (idempotent)
  * Promotion is logged to scoring_tuning_log.csv with the bucket stats

The loop runs every 2 hours; this means at most 24 promotions per day, but
the data drives convergence — once the worst buckets are killed the rest
clear MAX_WILSON_LOWER and stop being eligible.

Output:
  - scoring_config.json updated in-place (version bumped)
  - scoring_tuning_log.csv appended
  - kill_list_promotions.json — audit trail consumable by /trust/
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
CLUSTERS_PATH = ROOT / "sec_loser_clusters.json"
CONFIG_PATH = ROOT / "scoring_config.json"
LOG_PATH = ROOT / "scoring_tuning_log.csv"
PROMOTIONS_PATH = ROOT / "kill_list_promotions.json"

MIN_PROMOTION_N = 25
MAX_WILSON_LOWER = 25.0  # 95% lower bound
MAX_NEW_PER_CYCLE = 2

# Cluster bucket labels → scoring_config keys + values.
# Map FORM_FAMILY token from analyze_loser_clusters.py back to canonical SEC form.
FAMILY_TO_FORMS = {
    "form_424_dilution": ["424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424"],
    "form_S3_shelf": ["S-3", "S-3/A", "S-3ASR"],
    "form_S1_offering": ["S-1", "S-1/A"],
    "form_8K_general": ["8-K"],
    "form_4_insider": ["4"],
    "form_13D_activist": ["13D", "SC 13D", "SC 13D/A"],
    "form_13G_passive": ["13G", "SC 13G", "SC 13G/A"],
    "form_NT_late": ["NT 10-K", "NT 10-Q"],
}


def parse_bucket(label: str) -> tuple[str, str]:
    """Return (form_family, modifier) or ('','') if not a candidate."""
    parts = label.split("|")
    if len(parts) == 1 and parts[0] in FAMILY_TO_FORMS:
        return parts[0], ""
    if len(parts) == 2:
        family, mod = parts
        if family in FAMILY_TO_FORMS and mod == "cap_large_gt10b":
            return family, "largecap"
    return "", ""


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> int:
    clusters = load_json(CLUSTERS_PATH)
    cfg = load_json(CONFIG_PATH)
    if not clusters or not cfg:
        print("auto_promote: missing input — clusters or config")
        return 0

    blocked_set = {f.upper() for f in cfg.get("clean_presets", {}).get("blocked_forms", [])}
    blocked_lc_set = {
        f.upper() for f in cfg.get("clean_presets", {}).get("blocked_when_largecap", [])
    }

    candidates: list[dict[str, Any]] = []
    for b in clusters.get("worst_buckets", []) + clusters.get("all_buckets", []):
        if b.get("n", 0) < MIN_PROMOTION_N:
            continue
        if b.get("hit_rate_2pct_wilson_lo", 100) > MAX_WILSON_LOWER:
            continue
        family, modifier = parse_bucket(b.get("bucket", ""))
        if not family:
            continue
        forms = FAMILY_TO_FORMS[family]
        if modifier == "largecap":
            # Skip if form is already universally blocked (redundant).
            new_forms = [
                f for f in forms
                if f.upper() not in blocked_lc_set and f.upper() not in blocked_set
            ]
            target_key = "blocked_when_largecap"
        else:
            new_forms = [f for f in forms if f.upper() not in blocked_set]
            target_key = "blocked_forms"
        if not new_forms:
            continue
        candidates.append(
            {"family": family, "modifier": modifier, "forms": new_forms,
             "target_key": target_key, "bucket": b}
        )

    # De-duplicate by (target_key, family) so we don't promote a bucket twice.
    seen = set()
    unique = []
    for c in candidates:
        key = (c["target_key"], c["family"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
        if len(unique) >= MAX_NEW_PER_CYCLE:
            break

    if not unique:
        # Idempotent: write an empty audit row so /trust/ knows the loop ran.
        PROMOTIONS_PATH.write_text(
            json.dumps(
                {
                    "computed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "promoted": [],
                    "note": "no_eligible_buckets",
                    "thresholds": {
                        "min_n": MIN_PROMOTION_N,
                        "max_wilson_lower": MAX_WILSON_LOWER,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("auto_promote: no eligible buckets")
        return 0

    # Apply promotions.
    cfg.setdefault("clean_presets", {}).setdefault("blocked_forms", [])
    cfg.setdefault("clean_presets", {}).setdefault("blocked_when_largecap", [])
    promoted: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    for c in unique:
        target_list = cfg["clean_presets"][c["target_key"]]
        # Insert preserving order, no duplicates.
        for f in c["forms"]:
            if f.upper() not in {x.upper() for x in target_list}:
                target_list.append(f)
        promoted.append(
            {
                "family": c["family"],
                "modifier": c["modifier"],
                "forms_added": c["forms"],
                "target_key": c["target_key"],
                "bucket_n": c["bucket"]["n"],
                "bucket_hit_rate_2pct": c["bucket"]["hit_rate_2pct"],
                "bucket_wilson_lower": c["bucket"]["hit_rate_2pct_wilson_lo"],
                "bucket_alpha_pct": c["bucket"].get("avg_alpha_pct", 0),
            }
        )
        log_rows.append(
            {
                "timestamp_utc": now,
                "parameter": f"clean_presets.{c['target_key']}",
                "old_value": "",
                "new_value": ",".join(c["forms"]),
                "reason": (
                    f"bucket {c['family']}{'|largecap' if c['modifier'] else ''} "
                    f"n={c['bucket']['n']} wilson={c['bucket']['hit_rate_2pct_wilson_lo']}%"
                ),
            }
        )

    cfg["version"] = int(cfg.get("version", 0)) + 1
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    exists = LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["timestamp_utc", "parameter", "old_value", "new_value", "reason"],
        )
        if not exists:
            w.writeheader()
        w.writerows(log_rows)

    PROMOTIONS_PATH.write_text(
        json.dumps(
            {
                "computed_at_utc": now,
                "promoted": promoted,
                "thresholds": {
                    "min_n": MIN_PROMOTION_N,
                    "max_wilson_lower": MAX_WILSON_LOWER,
                    "max_per_cycle": MAX_NEW_PER_CYCLE,
                },
                "config_version": cfg["version"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"auto_promote: promoted {len(promoted)} buckets, config v{cfg['version']}")
    for p in promoted:
        print(
            f"  {p['family']}{'|largecap' if p['modifier'] else ''} "
            f"n={p['bucket_n']} hit={p['bucket_hit_rate_2pct']}% "
            f"wilson_lo={p['bucket_wilson_lower']}% → +{p['forms_added']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
