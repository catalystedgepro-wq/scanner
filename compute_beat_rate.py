#!/usr/bin/env python3
"""Journalist Beat-Rate Disclosure.

For every Catalyst Edge /scoops/ page we publish, measure how long after
our publish time tier-1 wires (Reuters, BusinessWire, GlobeNewswire,
Bloomberg via AlphaVantage) cover the same ticker. Output a public stat:
"median X minutes ahead of Reuters, Y% of catalysts beat Bloomberg."

This is a credibility metric NO retail platform publishes — quantifies
our latency advantage with reproducible math.

Output:
  beat_rate.json — last 30/90 days median latency advantage per source
  beat_rate.csv  — per-scoop record (ticker, scoop_publish_time, first_wire_time, delta_min)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
SCOOPS_DIR = ROOT / "docs" / "scoops"
NEWS_SIGNALS = ROOT / "news_signals.csv"
SCOOPS_STATUS = ROOT / "scoops_status.json"
OUT_JSON = ROOT / "beat_rate.json"
OUT_CSV = ROOT / "beat_rate.csv"

WIRE_SOURCES = {
    "alphavantage": "Reuters/Bloomberg/WSJ wires (via AlphaVantage)",
    "businesswire": "BusinessWire",
    "globenewswire": "GlobeNewswire",
    "prnewswire": "PR Newswire",
    "reuters_business": "Reuters Business",
    "reuters_world": "Reuters World",
    "yahoo_finance": "Yahoo Finance",
    "marketwatch_top": "MarketWatch",
}


def parse_iso(s: str) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d
    except ValueError:
        return None


def load_scoops() -> list[dict[str, Any]]:
    """Each scoop has a directory like docs/scoops/YYYY-MM-DD-TICKER/.
    The publish time is the directory mtime — close enough for stat purposes.
    Plus we cross-check scoops_status.json if available.
    """
    if not SCOOPS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    statuses: dict[str, dict[str, Any]] = {}
    if SCOOPS_STATUS.exists():
        try:
            data = json.loads(SCOOPS_STATUS.read_text(encoding="utf-8"))
            for item in (data.get("items") or []):
                statuses[item.get("slug", "")] = item
        except json.JSONDecodeError:
            pass
    for sub in sorted(SCOOPS_DIR.iterdir()):
        if not sub.is_dir():
            continue
        slug = sub.name
        parts = slug.split("-")
        if len(parts) < 4:
            continue
        date_str = "-".join(parts[:3])
        ticker = "-".join(parts[3:]).upper()
        try:
            mtime = dt.datetime.fromtimestamp(sub.stat().st_mtime, dt.timezone.utc)
        except OSError:
            continue
        out.append({
            "slug": slug,
            "ticker": ticker,
            "scoop_date": date_str,
            "scoop_published_utc": mtime.isoformat(),
            "validation": (statuses.get(slug) or {}).get("validation", "unknown"),
        })
    return out


def first_wire_after(news_rows: list[dict], ticker: str, after_ts: dt.datetime) -> dict[str, Any] | None:
    """Find the earliest tier-1 wire mention of ticker AFTER our scoop publish."""
    candidates = []
    for r in news_rows:
        src = (r.get("source") or "").lower()
        if src not in WIRE_SOURCES:
            continue
        cand_ticker = (r.get("ticker_candidates") or "").upper()
        if cand_ticker != ticker:
            continue
        ts = parse_iso(r.get("published_utc") or "")
        if not ts or ts < after_ts:
            continue
        candidates.append((ts, src, r.get("headline", ""), r.get("link", "")))
    if not candidates:
        return None
    candidates.sort()
    ts, src, head, link = candidates[0]
    return {
        "first_wire_source": src,
        "first_wire_published_utc": ts.isoformat(),
        "first_wire_headline": head,
        "first_wire_link": link,
    }


def main() -> int:
    scoops = load_scoops()
    if not scoops:
        OUT_JSON.write_text(json.dumps({"status": "no_scoops"}))
        print("beat_rate: no scoops to analyze")
        return 0
    if not NEWS_SIGNALS.exists():
        OUT_JSON.write_text(json.dumps({"status": "no_news"}))
        print("beat_rate: no news_signals.csv")
        return 0

    news_rows: list[dict] = []
    with NEWS_SIGNALS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            news_rows.append(r)

    rows: list[dict[str, Any]] = []
    deltas_per_source: dict[str, list[float]] = {}
    overall_deltas: list[float] = []
    beat_count = 0
    no_coverage_count = 0

    for sc in scoops:
        scoop_ts = parse_iso(sc["scoop_published_utc"])
        if not scoop_ts:
            continue
        match = first_wire_after(news_rows, sc["ticker"], scoop_ts)
        if not match:
            no_coverage_count += 1
            rows.append({**sc, "first_wire_source": "", "first_wire_published_utc": "",
                         "delta_minutes": "", "first_wire_headline": "",
                         "first_wire_link": "", "status": "no_wire_coverage"})
            continue
        wire_ts = parse_iso(match["first_wire_published_utc"])
        delta_min = (wire_ts - scoop_ts).total_seconds() / 60.0 if wire_ts else 0
        if delta_min > 0:
            beat_count += 1
        overall_deltas.append(delta_min)
        deltas_per_source.setdefault(match["first_wire_source"], []).append(delta_min)
        rows.append({**sc, **match,
                     "delta_minutes": f"{delta_min:.1f}",
                     "status": "beat" if delta_min > 0 else "tied_or_behind"})

    summary: dict[str, Any] = {
        "computed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_scoops_total": len(scoops),
        "n_with_wire_match": len(scoops) - no_coverage_count,
        "n_beat": beat_count,
        "no_wire_coverage": no_coverage_count,
        "overall_median_minutes_ahead": round(statistics.median(overall_deltas), 1) if overall_deltas else 0,
        "overall_mean_minutes_ahead": round(statistics.fmean(overall_deltas), 1) if overall_deltas else 0,
        "by_source": {
            src: {
                "n": len(deltas),
                "median_minutes_ahead": round(statistics.median(deltas), 1),
                "label": WIRE_SOURCES.get(src, src),
            }
            for src, deltas in deltas_per_source.items()
        },
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    fields = ["slug", "ticker", "scoop_date", "scoop_published_utc",
              "validation", "first_wire_source", "first_wire_published_utc",
              "delta_minutes", "first_wire_headline", "first_wire_link", "status"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in rows])
    print(
        f"beat_rate: scoops={len(scoops)} wire_matched={len(scoops)-no_coverage_count} "
        f"beat={beat_count} no_coverage={no_coverage_count} "
        f"median_ahead={summary['overall_median_minutes_ahead']}min"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
