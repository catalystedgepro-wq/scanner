# Catalyst ML Baseline (frozen 2026-04-14)

Source: `/home/operator/.openclaw/workspace/sec_outcome_summary.csv`

| list_name | rows | hit_2pct | hit_3pct | hit_5pct | avg_run_pct |
|---|---|---|---|---|---|
| sec_clean_gappers | 602 | 44.52 | 36.54 | 23.75 | 5.12 |
| sec_clean_value | 109 | 46.79 | 33.03 | 20.18 | 2.67 |
| sec_clean_moat_core | 74 | 41.89 | 29.73 | 18.92 | 2.27 |
| sec_top_gappers | 2553 | 43.83 | 35.14 | 22.33 | 4.17 |
| sec_top_value | 2553 | 43.83 | 35.14 | 22.33 | 4.17 |
| sec_top_moat_emerging | 2416 | 44.08 | 35.64 | 22.85 | 4.29 |
| sec_top_moat_core | 137 | 39.42 | 26.28 | 13.14 | 2.08 |

**ML must beat these numbers on walk-forward holdout. Any model worse than baseline blocks deploy.**

Targets (day-30):
- sec_clean_gappers hit_2pct >= 65%
- sec_clean_gappers hit_5pct >= 45%
- sec_clean_gappers avg_run >= 10%
- top-10 daily picks precision @ +5% >= 60%
