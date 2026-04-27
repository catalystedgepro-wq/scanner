#!/usr/bin/env python3
"""build_performance_breakdown.py — Generate premium performance breakdown data.

Produces sec_performance_breakdown.json with:
  - form_type_stats: win rate by SEC form type (8-K, Form 4, 13D, etc.)
  - catalyst_tag_stats: win rate by catalyst tag (+fda_approval, +merger, etc.)
  - list_by_form_stats: cross-tab of list × form type

Reads sec_outcome_rows.csv + archived daily CSVs to pull tags.
Run after evaluate_sec_outcomes.py each morning.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT        = Path(__file__).parent
OUTCOME_CSV = ROOT / "sec_outcome_rows.csv"
OUT_JSON    = ROOT / "sec_performance_breakdown.json"

# Map raw tag prefixes → readable catalyst labels
TAG_LABELS: dict[str, str] = {
    "fda approval":         "FDA Approval",
    "fda clearance":        "FDA Clearance",
    "fda breakthrough":     "FDA Breakthrough",
    "definitive agreement": "Merger / Acquisition",
    "merger agreement":     "Merger / Acquisition",
    "contract award":       "Contract Award",
    "awarded contract":     "Contract Award",
    "raises guidance":      "Guidance Raise",
    "record revenue":       "Record Revenue",
    "earnings beat":        "Earnings Beat",
    "share repurchase":     "Share Buyback",
    "buyback":              "Share Buyback",
    "dividend":             "Dividend",
    "insider_buy":          "Insider Buy",
    "patent":               "Patent / IP",
    "partnership":          "Partnership / JV",
    "joint venture":        "Partnership / JV",
    "restructuring":        "Restructuring",
    "strategic review":     "Strategic Review",
    "cash flow":            "Cash Flow Signal",
    "cost reduction":       "Cost Reduction",
}

FORM_LABELS: dict[str, str] = {
    "8-K":    "8-K (Material Event)",
    "6-K":    "6-K (Foreign Issuer)",
    "4":      "Form 4 (Insider Trade)",
    "SC 13D": "SC 13D (Activist)",
    "SC 13G": "SC 13G (Institutional)",
    "S-3":    "S-3 (Shelf Registration)",
    "424B4":  "424B4 (Prospectus)",
    "NT 10-K":"NT 10-K (Late Annual)",
    "NT 10-Q":"NT 10-Q (Late Quarterly)",
}

LIST_LABELS: dict[str, str] = {
    "sec_clean_gappers":      "⚡ Gappers",
    "sec_top_gappers":        "⚡ Gappers (All)",
    "sec_clean_value":        "💎 Value",
    "sec_top_value":          "💎 Value (All)",
    "sec_clean_moat_core":    "🏰 Moat Core",
    "sec_top_moat_core":      "🏰 Moat Core (All)",
    "sec_top_moat_emerging":  "🌱 Moat Emerging",
}

MIN_PICKS = 8  # Minimum picks required to show a stat (avoid misleading small samples)


def to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def tag_to_catalyst(tag: str) -> str | None:
    t = tag.strip().lstrip("+-").lower()
    for key, label in TAG_LABELS.items():
        if key in t:
            return label
    return None


def load_tags_from_archives(outcome_rows: list[dict]) -> dict[tuple[str, str], str]:
    """Build a (ticker, date) → tags mapping from archived daily CSVs."""
    # Collect all dates we need
    needed_dates: set[str] = {r["list_date"] for r in outcome_rows}

    tags_map: dict[tuple[str, str], str] = {}

    archive_patterns = [
        "sec_top_gappers_{date}.csv",
        "sec_top_value_{date}.csv",
        "sec_clean_gappers_{date}.csv",
        "sec_clean_value_{date}.csv",
        "sec_top_moat_core_{date}.csv",
        "sec_top_moat_emerging_{date}.csv",
    ]

    for date_str in needed_dates:
        for pattern in archive_patterns:
            path = ROOT / pattern.format(date=date_str)
            if not path.exists():
                continue
            try:
                with path.open(newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        ticker = row.get("ticker", "").strip().upper()
                        tags   = row.get("tags", "").strip()
                        if ticker and tags:
                            key = (ticker, date_str)
                            if key not in tags_map:
                                tags_map[key] = tags
            except Exception:
                continue

    return tags_map


def compute_stats(rows: list[dict]) -> dict:
    if not rows:
        return {}
    n      = len(rows)
    hits3  = sum(1 for r in rows if r.get("hit_3pct") == "1")
    hits5  = sum(1 for r in rows if r.get("hit_5pct") == "1")
    moves  = [to_float(r["next_day_max_run_pct"]) for r in rows]
    closes = [to_float(r["next_day_close_pct"]) for r in rows]
    wins   = sum(1 for c in closes if c > 0)
    losses = sum(1 for c in closes if c < 0)
    return {
        "picks":        n,
        "hit_rate_3pct": round(hits3 / n * 100, 1),
        "hit_rate_5pct": round(hits5 / n * 100, 1),
        "avg_move":     round(statistics.fmean(moves), 2),
        "wins":         wins,
        "losses":       losses,
    }


def main() -> int:
    if not OUTCOME_CSV.exists():
        print("build_performance_breakdown: sec_outcome_rows.csv not found — skipping")
        return 0

    outcome_rows = list(csv.DictReader(OUTCOME_CSV.open(newline="", encoding="utf-8")))
    if not outcome_rows:
        print("build_performance_breakdown: no outcome rows yet")
        return 0

    print(f"build_performance_breakdown: {len(outcome_rows)} outcome rows loaded")

    # Load tags from archived daily CSVs
    tags_map = load_tags_from_archives(outcome_rows)
    print(f"  tags resolved for {len(tags_map)} ticker-date pairs")

    # ── 1. Form-type stats ────────────────────────────────────────────────────
    by_form: dict[str, list[dict]] = defaultdict(list)
    for r in outcome_rows:
        form = r.get("form", "").strip()
        if form:
            by_form[form].append(r)

    form_type_stats = []
    for form, rows in sorted(by_form.items(), key=lambda x: -len(x[1])):
        s = compute_stats(rows)
        if s["picks"] < MIN_PICKS:
            continue
        form_type_stats.append({
            "form":          form,
            "label":         FORM_LABELS.get(form, form),
            **s,
        })
    # Sort by hit rate descending
    form_type_stats.sort(key=lambda x: -x["hit_rate_3pct"])

    # ── 2. Catalyst tag stats ─────────────────────────────────────────────────
    by_catalyst: dict[str, list[dict]] = defaultdict(list)
    for r in outcome_rows:
        ticker    = r.get("ticker", "").upper()
        list_date = r.get("list_date", "")
        tags_raw  = tags_map.get((ticker, list_date), "")
        catalysts_seen: set[str] = set()
        for tag in tags_raw.split(";"):
            cat = tag_to_catalyst(tag)
            if cat and cat not in catalysts_seen:
                by_catalyst[cat].append(r)
                catalysts_seen.add(cat)

    catalyst_tag_stats = []
    for cat, rows in sorted(by_catalyst.items(), key=lambda x: -len(x[1])):
        s = compute_stats(rows)
        if s["picks"] < MIN_PICKS:
            continue
        catalyst_tag_stats.append({"catalyst": cat, **s})
    catalyst_tag_stats.sort(key=lambda x: -x["hit_rate_3pct"])

    # ── 3. List × Form cross-tab ──────────────────────────────────────────────
    by_list_form: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in outcome_rows:
        key = (r.get("list_name", ""), r.get("form", "").strip())
        by_list_form[key].append(r)

    list_by_form_stats = []
    for (list_name, form), rows in sorted(by_list_form.items()):
        s = compute_stats(rows)
        if s["picks"] < MIN_PICKS:
            continue
        list_by_form_stats.append({
            "list":  LIST_LABELS.get(list_name, list_name),
            "form":  FORM_LABELS.get(form, form),
            **s,
        })
    list_by_form_stats.sort(key=lambda x: (-x["hit_rate_3pct"], -x["picks"]))

    out = {
        "generated_at":      dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_picks_scored": len(outcome_rows),
        "form_type_stats":   form_type_stats,
        "catalyst_tag_stats": catalyst_tag_stats,
        "list_by_form_stats": list_by_form_stats,
    }

    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"  form types: {len(form_type_stats)}, catalysts: {len(catalyst_tag_stats)}, cross-tab: {len(list_by_form_stats)}")
    print(f"  saved → {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
