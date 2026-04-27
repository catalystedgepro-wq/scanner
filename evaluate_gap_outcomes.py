#!/usr/bin/env python3
"""evaluate_gap_outcomes.py — Measure penny gap alert outcomes.

Runs at 4:15 PM ET (EOD recap job). For each alert in gap_alert_log.csv
that hasn't been evaluated yet, fetches intraday 5-min bars and measures:
  - Max gain in first 30 min, 1 hr, 2 hr after alert
  - Whether it hit 5%, 10%, 20%, 50% thresholds
  - Final close vs alert price (win/loss)

Outputs:
  gap_outcome_log.csv   — per-alert outcomes (appended daily)
  gap_outcome_summary.json — aggregated stats for newsletter rendering
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT            = Path(__file__).parent
ALERT_LOG       = ROOT / "gap_alert_log.csv"
OUTCOME_LOG     = ROOT / "gap_outcome_log.csv"
SUMMARY_JSON    = ROOT / "gap_outcome_summary.json"
CACHE_FILE      = ROOT / ".gap_intraday_cache.json"
CACHE_TTL_SEC   = 6 * 3600

YAHOO_INTRADAY  = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=5m&range=5d"
)

OUTCOME_FIELDS = [
    "ticker", "alert_date", "alert_time", "alert_price",
    "prev_close", "gap_pct", "vol_ratio",
    "max_30min_pct", "max_1hr_pct", "max_2hr_pct",
    "final_close_pct",
    "hit_5pct", "hit_10pct", "hit_20pct", "hit_50pct",
    "outcome", "evaluated_at",
]


# ── Cache ─────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


# ── Intraday data fetch ───────────────────────────────────────────────────

def fetch_intraday(symbol: str, cache: dict) -> list[dict]:
    """Fetch 5-min bars for past 5 days. Returns list of {ts, open, high, low, close}."""
    now_ts = int(dt.datetime.now().timestamp())
    entry  = cache.get(symbol.upper())
    if entry and now_ts - int(entry.get("ts", 0)) <= CACHE_TTL_SEC:
        return entry.get("rows", [])

    url = YAHOO_INTRADAY.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        q = result["indicators"]["quote"][0]
        rows = []
        for i, ts in enumerate(timestamps):
            try:
                h = q["high"][i]
                c = q["close"][i]
                if h is None or c is None:
                    continue
                rows.append({
                    "ts":    ts,
                    "high":  float(h),
                    "close": float(c),
                })
            except (TypeError, IndexError):
                continue
        cache[symbol.upper()] = {"ts": now_ts, "rows": rows}
        return rows
    except Exception as e:
        print(f"  intraday fetch error {symbol}: {e}")
        cache[symbol.upper()] = {"ts": now_ts, "rows": []}
        return []


# ── Outcome calculation ───────────────────────────────────────────────────

def calc_outcome(alert: dict, bars: list[dict]) -> dict | None:
    """Find bars after alert_time and measure max gains in each window."""
    try:
        alert_price = float(alert["alert_price"])
        alert_date  = alert["alert_date"]
        alert_time  = alert["alert_time"]
        if alert_price <= 0:
            return None
    except (KeyError, ValueError):
        return None

    # Parse alert datetime (ET — treat as naive for comparison)
    try:
        alert_dt = dt.datetime.strptime(
            f"{alert_date} {alert_time}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        return None

    # Yahoo timestamps are UTC — convert to ET (rough -4 offset, good enough for windowing)
    def to_et(ts: int) -> dt.datetime:
        return dt.datetime.utcfromtimestamp(ts) - dt.timedelta(hours=4)

    # Collect bars on the alert date, after alert time
    relevant = [
        b for b in bars
        if to_et(b["ts"]).date() == alert_dt.date()
        and to_et(b["ts"]) >= alert_dt
    ]
    if not relevant:
        return None

    window_30  = alert_dt + dt.timedelta(minutes=30)
    window_1hr = alert_dt + dt.timedelta(hours=1)
    window_2hr = alert_dt + dt.timedelta(hours=2)

    def max_pct(end_dt: dt.datetime) -> float:
        subset = [b["high"] for b in relevant if to_et(b["ts"]) <= end_dt]
        if not subset:
            return 0.0
        return (max(subset) - alert_price) / alert_price * 100

    max_30  = round(max_pct(window_30),  2)
    max_1hr = round(max_pct(window_1hr), 2)
    max_2hr = round(max_pct(window_2hr), 2)

    # Final close: last bar of the day
    day_bars = [b for b in bars if to_et(b["ts"]).date() == alert_dt.date()]
    final_close_pct = round(
        (day_bars[-1]["close"] - alert_price) / alert_price * 100, 2
    ) if day_bars else 0.0

    hit_5   = "1" if max_2hr >= 5   else "0"
    hit_10  = "1" if max_2hr >= 10  else "0"
    hit_20  = "1" if max_2hr >= 20  else "0"
    hit_50  = "1" if max_2hr >= 50  else "0"

    if max_2hr >= 20:
        outcome = "BIG WIN"
    elif max_2hr >= 10:
        outcome = "WIN"
    elif max_2hr >= 5:
        outcome = "SMALL WIN"
    elif final_close_pct > 0:
        outcome = "FLAT/UP"
    else:
        outcome = "LOSS"

    return {
        **{k: alert.get(k, "") for k in
           ["ticker", "alert_date", "alert_time", "alert_price", "prev_close",
            "gap_pct", "vol_ratio"]},
        "max_30min_pct":    max_30,
        "max_1hr_pct":      max_1hr,
        "max_2hr_pct":      max_2hr,
        "final_close_pct":  final_close_pct,
        "hit_5pct":         hit_5,
        "hit_10pct":        hit_10,
        "hit_20pct":        hit_20,
        "hit_50pct":        hit_50,
        "outcome":          outcome,
        "evaluated_at":     dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    }


# ── Summary builder ───────────────────────────────────────────────────────

def build_summary(outcomes: list[dict]) -> dict:
    if not outcomes:
        return {}

    def to_f(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    n         = len(outcomes)
    hit_5     = sum(1 for r in outcomes if r["hit_5pct"]  == "1")
    hit_10    = sum(1 for r in outcomes if r["hit_10pct"] == "1")
    hit_20    = sum(1 for r in outcomes if r["hit_20pct"] == "1")
    hit_50    = sum(1 for r in outcomes if r["hit_50pct"] == "1")
    avg_2hr   = statistics.fmean([to_f(r["max_2hr_pct"])  for r in outcomes])
    avg_close = statistics.fmean([to_f(r["final_close_pct"]) for r in outcomes])
    wins      = sum(1 for r in outcomes if to_f(r["final_close_pct"]) > 0)
    losses    = sum(1 for r in outcomes if to_f(r["final_close_pct"]) < 0)

    # Last 30 days
    cutoff = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    recent = [r for r in outcomes if r.get("alert_date", "") >= cutoff]
    recent_n    = len(recent)
    recent_hit10 = sum(1 for r in recent if r["hit_10pct"] == "1")

    # Best performer
    best = max(outcomes, key=lambda r: to_f(r["max_2hr_pct"]), default=None)

    return {
        "generated_at":       dt.datetime.utcnow().isoformat(),
        "total_alerts":       n,
        "hit_rate_5pct":      round(hit_5  / n * 100, 1),
        "hit_rate_10pct":     round(hit_10 / n * 100, 1),
        "hit_rate_20pct":     round(hit_20 / n * 100, 1),
        "hit_rate_50pct":     round(hit_50 / n * 100, 1),
        "avg_max_2hr_pct":    round(avg_2hr, 2),
        "avg_final_close_pct": round(avg_close, 2),
        "wins":               wins,
        "losses":             losses,
        "recent_30d_alerts":  recent_n,
        "recent_30d_hit10":   recent_hit10,
        "recent_30d_hit_rate_10pct": round(
            recent_hit10 / recent_n * 100, 1
        ) if recent_n else 0,
        "best_ticker":        best["ticker"]    if best else "",
        "best_max_2hr_pct":   to_f(best["max_2hr_pct"]) if best else 0,
        "best_date":          best["alert_date"] if best else "",
        "recent_outcomes":    [          # last 10 for premium table
            {
                "ticker":       r["ticker"],
                "date":         r["alert_date"],
                "alert_price":  r["alert_price"],
                "max_2hr_pct":  r["max_2hr_pct"],
                "outcome":      r["outcome"],
                "hit_10pct":    r["hit_10pct"],
            }
            for r in sorted(
                outcomes,
                key=lambda x: x.get("alert_date", ""),
                reverse=True,
            )[:10]
        ],
    }


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    if not ALERT_LOG.exists():
        print("evaluate_gap_outcomes: no gap_alert_log.csv yet — skipping")
        return 0

    alerts = list(csv.DictReader(ALERT_LOG.open(newline="", encoding="utf-8")))
    if not alerts:
        print("evaluate_gap_outcomes: alert log empty")
        return 0

    # Load already-evaluated outcomes to avoid re-fetching
    evaluated: set[tuple[str, str, str]] = set()
    existing_outcomes: list[dict] = []
    if OUTCOME_LOG.exists():
        for row in csv.DictReader(OUTCOME_LOG.open(newline="", encoding="utf-8")):
            key = (row["ticker"], row["alert_date"], row["alert_time"])
            evaluated.add(key)
            existing_outcomes.append(row)

    pending = [
        a for a in alerts
        if (a["ticker"], a["alert_date"], a["alert_time"]) not in evaluated
    ]

    print(f"evaluate_gap_outcomes: {len(alerts)} alerts total, {len(pending)} pending evaluation")

    if not pending:
        print("  all alerts already evaluated")
    else:
        cache     = load_cache()
        new_outcomes: list[dict] = []

        for alert in pending:
            bars = fetch_intraday(alert["ticker"], cache)
            if not bars:
                continue
            result = calc_outcome(alert, bars)
            if result:
                new_outcomes.append(result)
                print(f"  {alert['ticker']} {alert['alert_date']} "
                      f"+{result['max_2hr_pct']}% max 2hr → {result['outcome']}")
            time.sleep(0.2)

        save_cache(cache)

        if new_outcomes:
            append_mode = OUTCOME_LOG.exists()
            with OUTCOME_LOG.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
                if not append_mode:
                    w.writeheader()
                w.writerows(new_outcomes)
            print(f"  appended {len(new_outcomes)} new outcomes → {OUTCOME_LOG.name}")

        existing_outcomes.extend(new_outcomes)

    # Rebuild summary JSON from all outcomes
    summary = build_summary(existing_outcomes)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  summary: {summary.get('total_alerts',0)} alerts | "
          f"10% hit rate: {summary.get('hit_rate_10pct',0)}% | "
          f"avg 2hr gain: +{summary.get('avg_max_2hr_pct',0)}%")
    print(f"  saved → {SUMMARY_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
