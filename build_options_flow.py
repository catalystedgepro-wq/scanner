#!/usr/bin/env python3
"""build_options_flow.py — Bridge: options_activity.json → options_flow.csv.

Reads the options sweep/flow analysis produced by spoke_options.py and writes
it into options_flow.csv, which generate_seo_site.py reads to populate the
⚡ Options Activity section of the scanner website.

Column mapping:
    ticker          — stock symbol
    current_price   — underlying price at scan time
    call_oi         — total call volume scanned
    put_oi          — total put volume scanned
    pc_ratio        — put/call volume ratio (< 0.7 = bullish, > 1.3 = bearish)
    gamma_score     — sweep count (Vol/OI > 3x hits)
    max_pain        — gamma magnet strike (top strike by combined volume)
    atm_call_iv     — implied volatility of top sweep contract (0 if unavailable)
    unusual_call_vol — number of call sweeps (Vol/OI > 3x)

Only tickers with actual sweep or directional signal are written.
Archives dated copy to options_flow_YYYY-MM-DD.csv.

Run: python3 build_options_flow.py
Called automatically by run_daily_sec_catalyst.sh after spoke_options.py.
Pure stdlib — no requests/pandas.
"""
from __future__ import annotations

import csv
import json
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_YF_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def _fetch_price(ticker: str) -> float:
    """Get current price from Yahoo Finance v8 chart (no auth)."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": _YF_UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
            meta = ((d.get("chart") or {}).get("result") or [{}])[0].get("meta", {})
            p = meta.get("regularMarketPrice")
            if p and p > 0:
                return round(float(p), 2)
    except Exception:
        pass
    return 0.0

ROOT = Path(__file__).parent

OPTIONS_ACTIVITY = ROOT / "options_activity.json"
OPTIONS_FLOW_CSV = ROOT / "options_flow.csv"
MAX_ACTIVITY_AGE = timedelta(hours=36)


def _parse_iso_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_fresh_activity(data: dict, *, now: datetime | None = None) -> bool:
    ts = _parse_iso_ts(data.get("ts"))
    if not ts:
        return False
    reference = now or datetime.now(timezone.utc)
    return (reference - ts) <= MAX_ACTIVITY_AGE


def main() -> None:
    if not OPTIONS_ACTIVITY.exists():
        print("build_options_flow: options_activity.json not found — run spoke_options.py first")
        return

    try:
        activity: dict = json.loads(OPTIONS_ACTIVITY.read_text())
    except Exception as exc:
        print(f"build_options_flow: parse error — {exc}")
        return

    today = date.today().isoformat()
    now = datetime.now(timezone.utc)
    rows = []
    stale_rows = 0

    for ticker, data in activity.items():
        if not _is_fresh_activity(data, now=now):
            stale_rows += 1
            continue
        flow    = data.get("flow", {})
        magnet  = data.get("gamma_magnet") or {}
        sweeps  = data.get("top_sweeps", [])

        call_vol    = flow.get("call_volume", 0) or 0
        put_vol     = flow.get("put_volume",  0) or 0
        sentiment   = flow.get("sentiment", "neutral")
        sweep_count = data.get("sweep_count", 0) or 0
        call_sweeps = data.get("call_sweeps", 0) or 0
        price       = data.get("price", 0.0) or 0.0
        if not price:
            price = _fetch_price(ticker)
        top_strike  = magnet.get("strike", "") if magnet else ""

        # Only include tickers with a signal
        if sweep_count == 0 and sentiment == "NEUTRAL":
            continue

        pc_ratio = round(put_vol / call_vol, 3) if call_vol > 0 else 1.0

        # IV from the top sweep contract if available
        atm_iv = 0.0
        if sweeps:
            atm_iv = round(float(sweeps[0].get("iv", 0.0) or 0.0), 4)

        rows.append({
            "ticker":           ticker,
            "current_price":    round(price, 2),
            "call_oi":          call_vol,
            "put_oi":           put_vol,
            "pc_ratio":         pc_ratio,
            "gamma_score":      sweep_count,
            "max_pain":         top_strike,
            "atm_call_iv":      atm_iv,
            "unusual_call_vol": call_sweeps,
            "source":           data.get("source", ""),
            "activity_ts":      data.get("ts", ""),
        })

    # Sort: sweeps first, then by call dominance
    rows.sort(key=lambda r: (-r["gamma_score"], r["pc_ratio"]))

    fieldnames = ["ticker", "current_price", "call_oi", "put_oi",
                  "pc_ratio", "gamma_score", "max_pain",
                  "atm_call_iv", "unusual_call_vol", "source", "activity_ts"]

    with OPTIONS_FLOW_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Archive dated copy
    archive = ROOT / f"options_flow_{today}.csv"
    archive.write_text(OPTIONS_FLOW_CSV.read_text(encoding="utf-8"), encoding="utf-8")

    print(
        f"build_options_flow: {len(rows)} fresh tickers with options signals"
        f" ({stale_rows} stale skipped) → options_flow.csv"
    )
    if rows:
        print(f"  Top signals:")
        for r in rows[:5]:
            sig = "BULLISH" if r["pc_ratio"] < 0.7 else ("BEARISH" if r["pc_ratio"] > 1.3 else "NEUTRAL")
            print(f"    {r['ticker']:8s}  sweeps={r['gamma_score']}  C/P={r['pc_ratio']:.2f}  "
                  f"magnet@{r['max_pain']}  {sig}")


if __name__ == "__main__":
    main()
