#!/usr/bin/env python3
"""Evaluate SEC list quality against next-session outcomes.

Reads archived daily list files and computes outcome stats using daily OHLC.

2026-04-27 — comprehensive methodology upgrade. New columns + summary metrics:
  * spy_close_pct, alpha_close_pct  (#2 baseline subtraction)
  * catalyst_sign  (#3 directionality: S-3 = -1, Form 4 buy = +1, etc.)
  * realistic_pnl_pct  (#5 entry-at-open + 1.5% trail / 2% target / close)
  * hit_2pct_net  (#7 round-trip cost adjusted)
  * cohort_decay computed by summarize() — rolling 30/60/90d hit rate
Loser-cluster analysis runs as a sibling script (analyze_loser_clusters.py).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
OUTCOME_CSV = ROOT / "sec_outcome_rows.csv"
SUMMARY_CSV = ROOT / "sec_outcome_summary.csv"
QUOTE_CACHE = ROOT / ".stooq_daily_cache.json"
CONFIG_PATH = ROOT / "scoring_config.json"

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=120d"
CACHE_TTL_SEC = 6 * 3600
SPY_SYMBOL = "SPY"

LIST_FILES = [
    "sec_clean_gappers_{date}.csv",
    "sec_clean_value_{date}.csv",
    "sec_clean_moat_core_{date}.csv",
    "sec_top_gappers_{date}.csv",
    "sec_top_value_{date}.csv",
    "sec_top_moat_core_{date}.csv",
    "sec_top_moat_emerging_{date}.csv",
]

# Catalyst direction map. Sign convention:
#   +1 = bullish (acquire, insider buy, 13D activist, item-2.01 material acq)
#    0 = neutral / ambiguous (default 8-K, 13G passive)
#   -1 = bearish (dilution, restatement, departure, registered offering)
DEFAULT_SIGNS = {
    "S-1": -1, "S-1/A": -1, "S-3": -1, "S-3/A": -1, "S-3ASR": -1,
    "424B1": -1, "424B2": -1, "424B3": -1, "424B4": -1, "424B5": -1, "424B7": -1,
    "FWP": -1,
    "NT 10-K": -1, "NT 10-Q": -1,
    "13D": 1, "SC 13D": 1, "SC 13D/A": 1,
    "13G": 0, "SC 13G": 0, "SC 13G/A": 0,
    "8-K": 0,
}
# Form 4 needs side context (buy vs sell); we fall back via shares/value parsing
# already done upstream — here we infer from `tags` containing 'sell' or 'buy'.

# Execution cost defaults (overridden by scoring_config.json:execution_costs).
DEFAULT_ROUND_TRIP_PCT = 0.20  # bid/ask + fees baseline
DEFAULT_SMALLCAP_SLIPPAGE = 0.30
DEFAULT_SMALLCAP_CEILING = 1_000_000_000


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_cache() -> dict[str, Any]:
    if not QUOTE_CACHE.exists():
        return {}
    try:
        return json.loads(QUOTE_CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(cache: dict[str, Any]) -> None:
    QUOTE_CACHE.write_text(json.dumps(cache), encoding="utf-8")


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def fetch_yahoo_daily(symbol: str) -> list[dict[str, Any]]:
    url = YAHOO_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])
    except (KeyError, IndexError, TypeError):
        return []

    out: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        try:
            d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
            o = float(opens[i]) if opens[i] is not None else None
            h = float(highs[i]) if highs[i] is not None else None
            l = float(lows[i]) if lows[i] is not None else None
            c = float(closes[i]) if closes[i] is not None else None
            v = float(volumes[i]) if volumes[i] is not None else 0.0
            if o is None or h is None or l is None or c is None:
                continue
        except (TypeError, ValueError, IndexError):
            continue
        out.append({"date": d.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": v})
    return out


def get_daily_series(symbol: str, cache: dict[str, Any]) -> list[dict[str, Any]]:
    now_ts = int(dt.datetime.now().timestamp())
    entry = cache.get(symbol.upper())
    if entry and now_ts - int(entry.get("ts", 0)) <= CACHE_TTL_SEC:
        return entry.get("rows", [])
    rows = fetch_yahoo_daily(symbol)
    cache[symbol.upper()] = {"ts": now_ts, "rows": rows}
    return rows


def next_trading_row(
    rows: list[dict[str, Any]], d: dt.date
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    same = None
    nxt = None
    for i, r in enumerate(rows):
        rd = dt.date.fromisoformat(r["date"])
        if rd == d:
            same = r
            if i + 1 < len(rows):
                nxt = rows[i + 1]
            break
    return same, nxt


def catalyst_sign_from(form: str, tags: str, signs_cfg: dict[str, Any]) -> int:
    """Sign-aware catalyst direction.

    Reads scoring_config.json:catalyst_signs first, then DEFAULT_SIGNS.
    Form 4 needs side context — parse `tags` for 'sell'/'buy' tokens.
    """
    if not form:
        return 0
    f = form.strip()
    tags_low = (tags or "").lower()
    if f.startswith("4") or f == "4":
        if "sell" in tags_low:
            return signs_cfg.get("4_sell", -1)
        if "buy" in tags_low or "purchase" in tags_low:
            return signs_cfg.get("4_buy", 1)
        return 0
    # Try scoring_config map first.
    if f in signs_cfg:
        try:
            return int(signs_cfg[f])
        except (TypeError, ValueError):
            pass
    # Fall back to defaults.
    return DEFAULT_SIGNS.get(f, 0)


def realistic_pnl(
    open1: float, high1: float, low1: float, close1: float, close0: float
) -> float:
    """Simulate a realistic execution path.

    Entry at next_open. Take-profit at +2% above entry (most likely exit if hit).
    Stop-loss at -1.5% below entry. Otherwise hold to close.
    Returns pnl as percent of entry price.

    Note: With daily bars only, we can't know whether high or low came first,
    so we apply a conservative tie-break — if BOTH stop and target are hit,
    assume stop fired first (worst-case assumption protects honest reporting).
    """
    if open1 <= 0:
        return 0.0
    target = open1 * 1.02
    stop = open1 * 0.985
    hit_target = high1 >= target
    hit_stop = low1 <= stop
    if hit_stop and hit_target:
        # Conservative: assume stop fired first.
        return -1.5
    if hit_target:
        return 2.0
    if hit_stop:
        return -1.5
    # Hold to close.
    return (close1 - open1) / open1 * 100.0


def evaluate_one_row(
    row: dict[str, str],
    list_name: str,
    list_date: dt.date,
    cache: dict[str, Any],
    spy_lookup: dict[str, dict[str, float]],
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    ticker = (row.get("ticker") or "").strip().upper()
    if not ticker:
        return None
    series = get_daily_series(ticker, cache)
    if not series:
        return {
            "_dropped": True,
            "ticker": ticker,
            "list_name": list_name,
            "list_date": list_date.isoformat(),
            "reason": "no_price_data",
        }

    filing_day, next_day = next_trading_row(series, list_date)
    if not filing_day or not next_day:
        return {
            "_dropped": True,
            "ticker": ticker,
            "list_name": list_name,
            "list_date": list_date.isoformat(),
            "reason": "no_next_trading_day",
        }

    close0 = to_float(filing_day["close"])
    if close0 <= 0:
        return {
            "_dropped": True,
            "ticker": ticker,
            "list_name": list_name,
            "list_date": list_date.isoformat(),
            "reason": "zero_close",
        }
    open1 = to_float(next_day["open"])
    high1 = to_float(next_day["high"])
    low1 = to_float(next_day["low"])
    close1 = to_float(next_day["close"])
    vol1 = to_float(next_day["volume"])

    gap_next_open_pct = (open1 - close0) / close0 * 100.0
    next_day_max_run_pct = (high1 - close0) / close0 * 100.0
    next_day_close_pct = (close1 - close0) / close0 * 100.0

    # SPY baseline same-session move (Fix #2).
    spy_close_pct = 0.0
    spy_row = spy_lookup.get(next_day["date"])
    if spy_row and spy_row.get("close0_prev"):
        spy_close_pct = (
            (spy_row["close"] - spy_row["close0_prev"]) / spy_row["close0_prev"] * 100.0
        )
    alpha_close_pct = next_day_close_pct - spy_close_pct

    # Catalyst sign (Fix #3).
    signs_cfg = (cfg or {}).get("catalyst_signs", {})
    sign = catalyst_sign_from(row.get("form", ""), row.get("tags", ""), signs_cfg)

    # Transaction cost adjustment (Fix #7).
    exec_cfg = (cfg or {}).get("execution_costs", {})
    rt_cost = float(exec_cfg.get("round_trip_pct", DEFAULT_ROUND_TRIP_PCT))
    slip_smallcap = float(exec_cfg.get("slippage_pct_smallcap", DEFAULT_SMALLCAP_SLIPPAGE))
    smallcap_ceiling = float(exec_cfg.get("smallcap_mcap_ceiling", DEFAULT_SMALLCAP_CEILING))
    mcap = to_float(row.get("market_cap", 0))
    total_cost = rt_cost + (slip_smallcap if 0 < mcap < smallcap_ceiling else 0.0)
    hit_2pct_net = "1" if next_day_max_run_pct >= (2.0 + total_cost) else "0"

    # Realistic execution path (Fix #5).
    real_pnl = realistic_pnl(open1, high1, low1, close1, close0)
    realistic_pnl_net = real_pnl - total_cost

    base_score = (
        row.get("gapper_score", "")
        or row.get("value_score", "")
        or row.get("moat_score", "")
    )

    return {
        "list_name": list_name,
        "list_date": list_date.isoformat(),
        "ticker": ticker,
        "form": row.get("form", ""),
        "base_score": base_score,
        "filing_day_close": f"{close0:.4f}",
        "next_open": f"{open1:.4f}",
        "next_high": f"{high1:.4f}",
        "next_close": f"{close1:.4f}",
        "next_volume": str(int(vol1)),
        "gap_next_open_pct": f"{gap_next_open_pct:.4f}",
        "next_day_max_run_pct": f"{next_day_max_run_pct:.4f}",
        "next_day_close_pct": f"{next_day_close_pct:.4f}",
        "next_day_vwap_pct": f"{((high1 + low1 + close1) / 3.0 - close0) / close0 * 100.0:.4f}",
        "spy_close_pct": f"{spy_close_pct:.4f}",
        "alpha_close_pct": f"{alpha_close_pct:.4f}",
        "catalyst_sign": str(sign),
        "exec_cost_pct": f"{total_cost:.4f}",
        "hit_2pct": "1" if next_day_max_run_pct >= 2 else "0",
        "hit_3pct": "1" if next_day_max_run_pct >= 3 else "0",
        "hit_5pct": "1" if next_day_max_run_pct >= 5 else "0",
        "hit_2pct_net": hit_2pct_net,
        "realistic_pnl_pct": f"{real_pnl:.4f}",
        "realistic_pnl_net_pct": f"{realistic_pnl_net:.4f}",
        "market_cap": str(int(mcap)) if mcap > 0 else "",
    }


def build_spy_lookup(cache: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Map next_day date -> {close, close0_prev} for SPY baseline math."""
    series = get_daily_series(SPY_SYMBOL, cache)
    out: dict[str, dict[str, float]] = {}
    for i, r in enumerate(series):
        prev_close = series[i - 1]["close"] if i > 0 else r["close"]
        out[r["date"]] = {"close": r["close"], "close0_prev": prev_close, "open": r["open"]}
    return out


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault(r["list_name"], []).append(r)

    out: list[dict[str, Any]] = []
    today = dt.date.today()
    for list_name, grp in sorted(grouped.items()):
        if not grp:
            continue
        n = len(grp)
        max_runs = [to_float(x["next_day_max_run_pct"]) for x in grp]
        gap_opens = [to_float(x["gap_next_open_pct"]) for x in grp]
        close_moves = [to_float(x["next_day_close_pct"]) for x in grp]
        alphas = [to_float(x.get("alpha_close_pct", 0)) for x in grp]
        real_pnl = [to_float(x.get("realistic_pnl_pct", 0)) for x in grp]
        real_pnl_net = [to_float(x.get("realistic_pnl_net_pct", 0)) for x in grp]
        hits2 = sum(1 for x in grp if x["hit_2pct"] == "1")
        hits3 = sum(1 for x in grp if x["hit_3pct"] == "1")
        hits5 = sum(1 for x in grp if x["hit_5pct"] == "1")
        hits2_net = sum(1 for x in grp if x.get("hit_2pct_net", "0") == "1")
        wins = sum(1 for x in grp if to_float(x["next_day_close_pct"]) > 0)
        losses = sum(1 for x in grp if to_float(x["next_day_close_pct"]) < 0)

        # Score≥15 filter — published track record (Fix #1).
        published = [x for x in grp if to_float(x.get("base_score", 0)) >= 15]
        pub_n = len(published)
        pub_hits2 = sum(1 for x in published if x["hit_2pct"] == "1")
        pub_wins = sum(1 for x in published if to_float(x["next_day_close_pct"]) > 0)
        pub_losses = sum(1 for x in published if to_float(x["next_day_close_pct"]) < 0)

        # Cohort decay — rolling 30/60/90d (Fix #9).
        def hr_within(days: int) -> tuple[int, float]:
            cutoff = today - dt.timedelta(days=days)
            sub = [
                x
                for x in grp
                if dt.date.fromisoformat(x.get("list_date", "1900-01-01")) >= cutoff
            ]
            if not sub:
                return 0, 0.0
            return len(sub), sum(1 for x in sub if x["hit_2pct"] == "1") / len(sub) * 100.0

        c30_n, c30_hr = hr_within(30)
        c60_n, c60_hr = hr_within(60)
        c90_n, c90_hr = hr_within(90)

        out.append(
            {
                "list_name": list_name,
                "rows": str(n),
                "wins": str(wins),
                "losses": str(losses),
                "avg_gap_next_open_pct": f"{statistics.fmean(gap_opens):.4f}",
                "avg_next_day_max_run_pct": f"{statistics.fmean(max_runs):.4f}",
                "avg_next_day_close_pct": f"{statistics.fmean(close_moves):.4f}",
                "hit_rate_2pct": f"{(hits2 / n) * 100:.2f}",
                "hit_rate_3pct": f"{(hits3 / n) * 100:.2f}",
                "hit_rate_5pct": f"{(hits5 / n) * 100:.2f}",
                "hit_rate_2pct_net": f"{(hits2_net / n) * 100:.2f}",
                "avg_alpha_close_pct": f"{statistics.fmean(alphas):.4f}" if alphas else "0",
                "avg_realistic_pnl_pct": f"{statistics.fmean(real_pnl):.4f}" if real_pnl else "0",
                "avg_realistic_pnl_net_pct": (
                    f"{statistics.fmean(real_pnl_net):.4f}" if real_pnl_net else "0"
                ),
                "published_rows": str(pub_n),
                "published_wins": str(pub_wins),
                "published_losses": str(pub_losses),
                "published_hit_rate_2pct": (
                    f"{(pub_hits2 / pub_n) * 100:.2f}" if pub_n else "0"
                ),
                "cohort_30d_rows": str(c30_n),
                "cohort_30d_hit_rate_2pct": f"{c30_hr:.2f}",
                "cohort_60d_rows": str(c60_n),
                "cohort_60d_hit_rate_2pct": f"{c60_hr:.2f}",
                "cohort_90d_rows": str(c90_n),
                "cohort_90d_hit_rate_2pct": f"{c90_hr:.2f}",
            }
        )
    return out


def daterange(start: dt.date, end: dt.date) -> list[dt.date]:
    cur = start
    out = []
    while cur <= end:
        out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SEC list outcomes.")
    parser.add_argument("--days", type=int, default=14, help="Lookback days from today.")
    args = parser.parse_args()

    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=max(args.days - 1, 0))

    cache = load_cache()
    cfg = load_config()
    spy_lookup = build_spy_lookup(cache)
    outcome_rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []

    for d in daterange(start, end):
        dstr = d.isoformat()
        for pattern in LIST_FILES:
            fname = pattern.format(date=dstr)
            path = ROOT / fname
            if not path.exists():
                continue
            list_name = fname.replace(f"_{dstr}.csv", "")
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    r = evaluate_one_row(row, list_name, d, cache, spy_lookup, cfg)
                    if r and not r.get("_dropped"):
                        outcome_rows.append(r)
                    elif r and r.get("_dropped"):
                        dropped_rows.append(r)

    save_cache(cache)

    with OUTCOME_CSV.open("w", newline="", encoding="utf-8") as f:
        if outcome_rows:
            writer = csv.DictWriter(f, fieldnames=list(outcome_rows[0].keys()))
            writer.writeheader()
            writer.writerows(outcome_rows)
        else:
            f.write("list_name,list_date,ticker\n")

    summary_rows = summarize(outcome_rows)
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        if summary_rows:
            writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)
        else:
            f.write("list_name,rows\n")

    print(f"wrote {OUTCOME_CSV.name} rows={len(outcome_rows)}")
    print(f"wrote {SUMMARY_CSV.name} rows={len(summary_rows)}")
    if dropped_rows:
        print(f"  survivorship: {len(dropped_rows)} tickers dropped (no price data)")
        drop_path = ROOT / "sec_outcome_dropped.csv"
        with drop_path.open("w", newline="", encoding="utf-8") as df:
            dw = csv.DictWriter(
                df, fieldnames=["ticker", "list_name", "list_date", "reason"]
            )
            dw.writeheader()
            dw.writerows(
                [
                    {k: r.get(k, "") for k in ["ticker", "list_name", "list_date", "reason"]}
                    for r in dropped_rows
                ]
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
