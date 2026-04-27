#!/usr/bin/env python3
"""daily_recap.py — EOD win-rate scorecard for today's Top N picks.

Run after 4 PM ET (or schedule via cron at 4:15 PM weekdays).

Usage:
    python3 daily_recap.py                      # today's Top 10 from combined_priority
    python3 daily_recap.py --date 2026-04-02    # evaluate a past session
    python3 daily_recap.py --top 15             # change pick count
    python3 daily_recap.py --source gappers     # use sec_top_gappers instead

Outputs (all in workspace root):
    daily_recap_log.csv        — one row per ticker per session (appended daily)
    daily_recap_summary.json   — today + rolling 30d + all-time stats

All dependencies: stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent
RECAP_LOG    = ROOT / "daily_recap_log.csv"
SUMMARY_JSON = ROOT / "daily_recap_summary.json"
CACHE_FILE   = ROOT / ".daily_recap_cache.json"
CACHE_TTL    = 4 * 3600   # 4 h — refresh after market close settles

# Yahoo Finance daily OHLCV — 60 days is enough to always find prev_close
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1d&range=60d"
)
UA = "Mozilla/5.0 (compatible; CatalystEdge/1.0)"

# ── Outcome thresholds (vs prior close) ───────────────────────────────────────
#   BIG WIN   : close ≥ +5%
#   WIN       : close ≥ +2%
#   FLAT      : close ≥ -1%
#   LOSS      : close  < -1%
THRESH_BIG_WIN  =  5.0
THRESH_WIN      =  2.0
THRESH_FLAT     = -1.0

LOG_FIELDS = [
    "session_date", "ticker", "rank", "total_score", "form",
    "prev_close", "day_open", "day_high", "day_close",
    "open_gap_pct",      # open  vs prev_close
    "max_intraday_pct",  # high  vs prev_close  (best opportunity)
    "close_pct",         # close vs prev_close  (what you got if you held)
    "hit_2pct", "hit_5pct", "hit_10pct",
    "outcome",           # BIG WIN / WIN / FLAT / LOSS / NO DATA
    "source",            # combined_priority | gappers
]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    except Exception:
        return {}


def _save_cache(c: dict) -> None:
    CACHE_FILE.write_text(json.dumps(c))


# ── Yahoo Finance fetch ───────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, cache: dict) -> list[dict]:
    """Return list of {date, open, high, low, close, volume} sorted ascending."""
    key   = symbol.upper()
    now   = int(dt.datetime.now().timestamp())
    entry = cache.get(key)
    if entry and now - int(entry.get("ts", 0)) < CACHE_TTL:
        return entry["rows"]

    url = YAHOO_URL.format(symbol=key)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result     = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        q          = result["indicators"]["quote"][0]
        rows: list[dict] = []
        for i, ts in enumerate(timestamps):
            try:
                o = q["open"][i];  h = q["high"][i]
                l = q["low"][i];   c = q["close"][i]
                if None in (o, h, l, c):
                    continue
                rows.append({
                    "date":   dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d"),
                    "open":   float(o),
                    "high":   float(h),
                    "low":    float(l),
                    "close":  float(c),
                })
            except (TypeError, IndexError):
                continue
        cache[key] = {"ts": now, "rows": rows}
        _save_cache(cache)
        return rows
    except Exception as exc:
        print(f"    [{symbol}] fetch error: {exc}")
        cache[key] = {"ts": now, "rows": []}
        _save_cache(cache)
        return []


def get_day_bars(rows: list[dict], date_str: str) -> dict | None:
    """Return the OHLC bar for date_str, or None if not found."""
    for r in rows:
        if r["date"] == date_str:
            return r
    return None


def get_prev_close(rows: list[dict], date_str: str) -> float | None:
    """Return the close of the trading day immediately before date_str."""
    before = [r for r in rows if r["date"] < date_str]
    return before[-1]["close"] if before else None


# ── Pick loading ──────────────────────────────────────────────────────────────

def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def load_picks(date_str: str, top_n: int, source: str) -> list[dict]:
    """
    Load today's (or a historical) top-N picks.

    Sources:
      combined_priority — combined_priority_{date}.csv, sorted by total_score
      gappers           — sec_top_gappers_{date}.csv, sorted by base_score then recency
    Falls back to the live (undated) file if the dated archive doesn't exist yet.
    """
    if source == "gappers":
        dated = ROOT / f"sec_top_gappers_{date_str}.csv"
        live  = ROOT / "sec_top_gappers.csv"
        rows  = _load_csv(dated) or _load_csv(live)
        score_col = "base_score"
        form_col  = "form"
    else:
        dated = ROOT / f"combined_priority_{date_str}.csv"
        live  = ROOT / "combined_priority.csv"
        rows  = _load_csv(dated) or _load_csv(live)
        score_col = "total_score"
        form_col  = "form" if "form" in (rows[0] if rows else {}) else ""

    if not rows:
        return []

    def score_key(r: dict) -> float:
        try:
            return float(r.get(score_col, 0) or 0)
        except ValueError:
            return 0.0

    rows.sort(key=score_key, reverse=True)
    top = rows[:top_n]

    result = []
    for i, r in enumerate(top, start=1):
        result.append({
            "rank":        i,
            "ticker":      r.get("ticker", "").strip().upper(),
            "total_score": r.get(score_col, ""),
            "form":        r.get(form_col, "") if form_col else "",
        })
    return [p for p in result if p["ticker"]]


# ── Outcome calculation ───────────────────────────────────────────────────────

def pct(new: float, base: float) -> float:
    return round((new - base) / base * 100, 2) if base else 0.0


def classify(close_pct: float) -> str:
    if close_pct >= THRESH_BIG_WIN:
        return "BIG WIN"
    if close_pct >= THRESH_WIN:
        return "WIN"
    if close_pct >= THRESH_FLAT:
        return "FLAT"
    return "LOSS"


def evaluate_pick(pick: dict, date_str: str, cache: dict) -> dict:
    sym  = pick["ticker"]
    rows = fetch_ohlcv(sym, cache)
    time.sleep(0.15)   # polite throttle

    bar       = get_day_bars(rows, date_str)
    prev_close = get_prev_close(rows, date_str)

    if not bar or not prev_close or prev_close <= 0:
        return {
            **pick,
            "session_date": date_str,
            "prev_close": "", "day_open": "", "day_high": "", "day_close": "",
            "open_gap_pct": "", "max_intraday_pct": "", "close_pct": "",
            "hit_2pct": "0", "hit_5pct": "0", "hit_10pct": "0",
            "outcome": "NO DATA",
        }

    o = bar["open"];  h = bar["high"];  c = bar["close"]
    gap_pct = pct(o, prev_close)
    max_pct = pct(h, prev_close)
    cls_pct = pct(c, prev_close)

    return {
        **pick,
        "session_date":     date_str,
        "prev_close":       round(prev_close, 4),
        "day_open":         round(o, 4),
        "day_high":         round(h, 4),
        "day_close":        round(c, 4),
        "open_gap_pct":     gap_pct,
        "max_intraday_pct": max_pct,
        "close_pct":        cls_pct,
        "hit_2pct":  "1" if max_pct >= 2  else "0",
        "hit_5pct":  "1" if max_pct >= 5  else "0",
        "hit_10pct": "1" if max_pct >= 10 else "0",
        "outcome":   classify(cls_pct),
    }


# ── Aggregation helpers ───────────────────────────────────────────────────────

def to_f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def session_stats(rows: list[dict]) -> dict:
    """Aggregate stats for a set of outcome rows (one session or many)."""
    valid = [r for r in rows if r.get("outcome") not in ("NO DATA", "")]
    n = len(valid)
    if not n:
        return {"picks": 0}

    def fvals(col: str) -> list[float]:
        return [v for r in valid if (v := to_f(r.get(col))) is not None]

    wins     = sum(1 for r in valid if r["outcome"] in ("WIN", "BIG WIN"))
    big_wins = sum(1 for r in valid if r["outcome"] == "BIG WIN")
    losses   = sum(1 for r in valid if r["outcome"] == "LOSS")
    flat     = sum(1 for r in valid if r["outcome"] == "FLAT")

    close_vals   = fvals("close_pct")
    max_vals     = fvals("max_intraday_pct")
    gap_vals     = fvals("open_gap_pct")

    hit2  = sum(1 for r in valid if r.get("hit_2pct")  == "1")
    hit5  = sum(1 for r in valid if r.get("hit_5pct")  == "1")
    hit10 = sum(1 for r in valid if r.get("hit_10pct") == "1")

    best  = max(valid, key=lambda r: to_f(r.get("close_pct")) or -999)
    worst = min(valid, key=lambda r: to_f(r.get("close_pct")) or 999)

    return {
        "picks":            n,
        "wins":             wins,
        "big_wins":         big_wins,
        "flat":             flat,
        "losses":           losses,
        "win_rate_pct":     round(wins / n * 100, 1),
        "avg_close_pct":    round(statistics.fmean(close_vals), 2) if close_vals else 0,
        "avg_max_pct":      round(statistics.fmean(max_vals),   2) if max_vals   else 0,
        "avg_gap_pct":      round(statistics.fmean(gap_vals),   2) if gap_vals   else 0,
        "hit_rate_2pct":    round(hit2  / n * 100, 1),
        "hit_rate_5pct":    round(hit5  / n * 100, 1),
        "hit_rate_10pct":   round(hit10 / n * 100, 1),
        "best_ticker":      best.get("ticker", ""),
        "best_close_pct":   to_f(best.get("close_pct")),
        "worst_ticker":     worst.get("ticker", ""),
        "worst_close_pct":  to_f(worst.get("close_pct")),
    }


def rolling_stats(all_rows: list[dict], days: int) -> dict:
    """Stats across the most recent N calendar days."""
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    subset = [r for r in all_rows if r.get("session_date", "") >= cutoff]

    stats = session_stats(subset)

    # Per-session win rates for best/worst session
    by_session: dict[str, list[dict]] = {}
    for r in subset:
        by_session.setdefault(r.get("session_date", ""), []).append(r)

    sessions = len(by_session)
    best_sess = worst_sess = {}
    if by_session:
        sess_rates = [
            {"date": d, "win_rate_pct": session_stats(rs).get("win_rate_pct", 0)}
            for d, rs in by_session.items()
            if session_stats(rs).get("picks", 0)
        ]
        if sess_rates:
            best_sess  = max(sess_rates, key=lambda x: x["win_rate_pct"])
            worst_sess = min(sess_rates, key=lambda x: x["win_rate_pct"])

    return {
        **stats,
        "sessions":      sessions,
        "best_session":  best_sess,
        "worst_session": worst_sess,
    }


# ── ASCII report printer ──────────────────────────────────────────────────────

WIN_EMOJI  = {"BIG WIN": "🚀", "WIN": "✅", "FLAT": "➖", "LOSS": "❌", "NO DATA": "⏳"}
COL_TICKER = 7
COL_SCORE  = 7
COL_FORM   = 6
COL_CLOSE  = 8
COL_MAX    = 8
COL_GAP    = 7
COL_HIT    = 5
COL_OUTC   = 11


def _bar(val: float, width: int = 12) -> str:
    """Simple inline bar for sparkline feel."""
    if val is None:
        return " " * width
    filled = max(0, min(width, round(abs(val) / 20 * width)))
    char = "█" if val >= 0 else "░"
    return (char * filled).ljust(width)


def print_report(date_str: str, results: list[dict], source: str) -> None:
    stats = session_stats(results)

    print()
    print("=" * 70)
    print(f"  📊  CATALYST EDGE — DAILY RECAP  [{date_str}]")
    print(f"  Source: {source.upper()} · Top {len(results)} picks")
    print("=" * 70)

    header = (
        f"  {'#':>2}  {'TICKER':<{COL_TICKER}}  {'SCORE':>{COL_SCORE}}"
        f"  {'FORM':<{COL_FORM}}  {'CLOSE%':>{COL_CLOSE}}  {'MAX%':>{COL_MAX}}"
        f"  {'GAP%':>{COL_GAP}}  {'H5%':>{COL_HIT}}  {'OUTCOME':<{COL_OUTC}}"
    )
    print(header)
    print("  " + "-" * 66)

    for r in results:
        emoji    = WIN_EMOJI.get(r.get("outcome", ""), "")
        close_p  = to_f(r.get("close_pct"))
        max_p    = to_f(r.get("max_intraday_pct"))
        gap_p    = to_f(r.get("open_gap_pct"))
        hit5     = "Y" if r.get("hit_5pct") == "1" else "·"
        c_str    = f"{close_p:+.2f}%" if close_p is not None else "  ---  "
        m_str    = f"{max_p:+.2f}%"   if max_p   is not None else "  ---  "
        g_str    = f"{gap_p:+.2f}%"   if gap_p   is not None else "  --- "
        score    = str(r.get("total_score", ""))[:6]
        outc     = f"{emoji} {r.get('outcome','NO DATA')}"

        print(
            f"  {r['rank']:>2}  {r['ticker']:<{COL_TICKER}}  {score:>{COL_SCORE}}"
            f"  {r.get('form',''):<{COL_FORM}}  {c_str:>{COL_CLOSE}}  {m_str:>{COL_MAX}}"
            f"  {g_str:>{COL_GAP}}  {hit5:>{COL_HIT}}  {outc:<{COL_OUTC}}"
        )

    print("  " + "─" * 66)
    n = stats.get("picks", 0)
    if n:
        w   = stats["wins"]
        wr  = stats["win_rate_pct"]
        avg = stats["avg_close_pct"]
        print(
            f"\n  Session Win Rate : {w}/{n} picks = {wr}% ({'🟢' if wr >= 60 else '🟡' if wr >= 40 else '🔴'})"
        )
        print(f"  Avg Close Gain   : {avg:+.2f}%")
        print(f"  Avg Max Run      : {stats['avg_max_pct']:+.2f}%")
        print(f"  Avg Open Gap     : {stats['avg_gap_pct']:+.2f}%")
        print(f"  Hit ≥2% intraday : {stats['hit_rate_2pct']}%")
        print(f"  Hit ≥5% intraday : {stats['hit_rate_5pct']}%")
        print(f"  Hit ≥10% intraday: {stats['hit_rate_10pct']}%")
        print(f"  Best  : {stats['best_ticker']} {stats['best_close_pct']:+.2f}%")
        print(f"  Worst : {stats['worst_ticker']} {stats['worst_close_pct']:+.2f}%")
    else:
        print("\n  No valid outcome data for this session.")
    print("=" * 70)


# ── Log persistence ───────────────────────────────────────────────────────────

def load_log() -> list[dict]:
    if not RECAP_LOG.exists():
        return []
    return list(csv.DictReader(RECAP_LOG.open(newline="", encoding="utf-8")))


def save_to_log(results: list[dict], source: str) -> None:
    append = RECAP_LOG.exists()
    with RECAP_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if not append:
            w.writeheader()
        for r in results:
            w.writerow({**r, "source": source})


def already_logged(date_str: str, source: str) -> bool:
    if not RECAP_LOG.exists():
        return False
    for row in csv.DictReader(RECAP_LOG.open(newline="", encoding="utf-8")):
        if row.get("session_date") == date_str and row.get("source") == source:
            return True
    return False


# ── Summary JSON ──────────────────────────────────────────────────────────────

def build_summary(today_date: str, today_results: list[dict],
                  all_rows: list[dict], source: str) -> dict:
    today_stats = session_stats(today_results)
    r30         = rolling_stats(all_rows, 30)
    r90         = rolling_stats(all_rows, 90)
    all_stats   = rolling_stats(all_rows, 9999)

    def ticker_rows(results: list[dict]) -> list[dict]:
        return [
            {
                "rank":       r["rank"],
                "ticker":     r["ticker"],
                "form":       r.get("form", ""),
                "close_pct":  to_f(r.get("close_pct")),
                "max_pct":    to_f(r.get("max_intraday_pct")),
                "gap_pct":    to_f(r.get("open_gap_pct")),
                "outcome":    r.get("outcome", "NO DATA"),
                "hit_5pct":   r.get("hit_5pct", "0"),
            }
            for r in results
        ]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat() + "Z",
        "source":       source,
        "today": {
            "session_date": today_date,
            **today_stats,
            "picks_detail": ticker_rows(today_results),
        },
        "rolling_30d":  r30,
        "rolling_90d":  r90,
        "all_time":     all_stats,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Daily recap: win-rate for today's Top N picks")
    ap.add_argument("--date",   default="",               help="Session date YYYY-MM-DD (default: today)")
    ap.add_argument("--top",    default=10, type=int,     help="Number of picks to evaluate (default: 10)")
    ap.add_argument("--source", default="combined",       help="combined | gappers")
    ap.add_argument("--force",  action="store_true",      help="Re-evaluate even if already logged today")
    args = ap.parse_args()

    date_str = args.date or dt.date.today().isoformat()
    source   = "gappers" if args.source == "gappers" else "combined"
    top_n    = max(1, args.top)

    print(f"daily_recap: {date_str} · source={source} · top={top_n}")

    # Guard: don't double-log unless forced
    if not args.force and already_logged(date_str, source):
        print(f"  Already logged for {date_str}/{source}. Use --force to re-evaluate.")
        # Still load and print the summary for reference
        all_rows = load_log()
        today_rows = [r for r in all_rows
                      if r.get("session_date") == date_str and r.get("source") == source]
        if today_rows:
            print_report(date_str, today_rows, source)
        summary = build_summary(date_str, today_rows, all_rows, source)
        SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 0

    picks = load_picks(date_str, top_n, source)
    if not picks:
        print(f"  No picks found for {date_str}/{source}. "
              f"Check that combined_priority_{date_str}.csv exists.")
        return 1

    print(f"  Loaded {len(picks)} picks. Fetching EOD data...")

    cache   = _load_cache()
    results = []
    for pick in picks:
        sym = pick["ticker"]
        r   = evaluate_pick(pick, date_str, cache)
        cp  = to_f(r.get("close_pct"))
        mp  = to_f(r.get("max_intraday_pct"))
        c_str = f"{cp:+.2f}%" if cp is not None else "NO DATA"
        m_str = f"{mp:+.2f}%" if mp is not None else ""
        print(f"    #{pick['rank']:>2} {sym:<6}  close {c_str}  max {m_str}  → {r['outcome']}")
        results.append(r)

    save_to_log(results, source)
    print(f"  Appended {len(results)} rows → {RECAP_LOG.name}")

    all_rows = load_log()
    summary  = build_summary(date_str, results, all_rows, source)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  Summary saved → {SUMMARY_JSON.name}")

    print_report(date_str, results, source)

    # Quick 30-day headline
    r30 = summary["rolling_30d"]
    if r30.get("sessions"):
        print(
            f"\n  📈 30-Day Rolling: {r30['sessions']} sessions · "
            f"{r30.get('win_rate_pct',0)}% win rate · "
            f"avg close {r30.get('avg_close_pct',0):+.2f}%"
        )
        bs = r30.get("best_session", {})
        ws = r30.get("worst_session", {})
        if bs:
            print(f"     Best session  {bs.get('date','?')} → {bs.get('win_rate_pct',0)}% win rate")
        if ws:
            print(f"     Worst session {ws.get('date','?')} → {ws.get('win_rate_pct',0)}% win rate")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
