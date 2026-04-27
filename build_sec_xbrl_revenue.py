#!/usr/bin/env python3
"""build_sec_xbrl_revenue.py — SEC XBRL Revenues YoY (current vs prior Q).

Pulls aggregate Revenues reported for the most recent completed
calendar quarter from SEC's XBRL Frames API, plus the same quarter
one year prior. Joins on CIK, maps to tickers via SEC company_tickers
cache, computes YoY % delta.

Why this matters for trading:
- XBRL frames surface tagged Revenues BEFORE earnings calls for
  filers who 10-Q/10-K early in the quarter.
- YoY deltas at the reporting-company level are the purest
  growth-rate signal, independent of guidance framing.
- Top-line reacceleration > +20% YoY into a beat = momentum regime
  (historically 3-5% post-earnings drift over 60d).
- Top-line contraction > -10% YoY into a miss = -8% to -15% one-day
  reaction, -20% 60d drift for growth names.
- Sector patterns: tech SaaS hardware ATL2 is 60%+ of new frames
  within 30 days of Q close.

Source: data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY{YYYYQN}.json
  (public, no key; SEC requires User-Agent with contact).

Output: sec_xbrl_revenue.csv
Columns: ticker, company, cik, q_current, val_current_usd, q_prior,
         val_prior_usd, yoy_pct, filed_current, accn_current,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_xbrl_revenue.csv"
TICKER_CACHE = ROOT / ".sec_company_tickers_cache.json"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FRAME = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{period}.json"


def fetch_frame(tag: str, period: str) -> list[dict]:
    url = FRAME.format(tag=tag, period=period)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"xbrl_revenue {tag} {period}: {e}")
        return []
    return body.get("data", []) or []


def load_ticker_map() -> dict[str, tuple[str, str]]:
    """cik10 -> (ticker, company)."""
    if not TICKER_CACHE.exists():
        return {}
    try:
        raw = json.loads(TICKER_CACHE.read_bytes().decode("utf-8"))
    except Exception:
        return {}
    out: dict[str, tuple[str, str]] = {}
    for row in raw.values():
        cik = str(row.get("cik_str", "")).zfill(10)
        t = str(row.get("ticker", "")).upper()
        name = str(row.get("title", ""))
        if cik and t:
            out[cik] = (t, name)
    return out


def most_recent_closed_quarter(today: dt.date) -> tuple[int, int]:
    """Return (year, quarter) whose end is >=60 days before today.

    10-Qs due 40d after close for large accelerated filers, so a 60d
    buffer gives meaningful XBRL fill.
    """
    # Quarter ends: Mar 31, Jun 30, Sep 30, Dec 31.
    q_ends = [
        (today.year, 1, dt.date(today.year, 3, 31)),
        (today.year, 2, dt.date(today.year, 6, 30)),
        (today.year, 3, dt.date(today.year, 9, 30)),
        (today.year, 4, dt.date(today.year, 12, 31)),
        (today.year - 1, 4, dt.date(today.year - 1, 12, 31)),
        (today.year - 1, 3, dt.date(today.year - 1, 9, 30)),
    ]
    cutoff = today - dt.timedelta(days=60)
    # Iterate newest-first, return the first end-date <= cutoff.
    for y, q, end in sorted(q_ends, key=lambda x: x[2], reverse=True):
        if end <= cutoff:
            return y, q
    return today.year - 1, 4


def main() -> None:
    today = dt.date.today()
    y, q = most_recent_closed_quarter(today)
    cur = f"CY{y}Q{q}"
    prior = f"CY{y-1}Q{q}"

    ticker_map = load_ticker_map()

    cur_data = fetch_frame("Revenues", cur)
    if len(cur_data) < 20:
        # Fall back one quarter earlier if current is too thin.
        if q == 1:
            y2, q2 = y - 1, 4
        else:
            y2, q2 = y, q - 1
        cur2 = f"CY{y2}Q{q2}"
        prior2 = f"CY{y2-1}Q{q2}"
        print(f"xbrl_revenue: {cur} thin ({len(cur_data)}), "
              f"falling back to {cur2}")
        cur_data = fetch_frame("Revenues", cur2)
        prior_data = fetch_frame("Revenues", prior2)
        cur, prior = cur2, prior2
    else:
        prior_data = fetch_frame("Revenues", prior)

    if not cur_data and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"xbrl_revenue: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    prior_by_cik: dict[str, float] = {}
    for p in prior_data:
        cik = str(p.get("cik", "")).zfill(10)
        if cik:
            prior_by_cik[cik] = float(p.get("val", 0) or 0)

    rows: list[dict] = []
    for p in cur_data:
        cik = str(p.get("cik", "")).zfill(10)
        if cik not in ticker_map:
            continue
        ticker, company = ticker_map[cik]
        val_cur = float(p.get("val", 0) or 0)
        val_prior = prior_by_cik.get(cik, 0.0)
        if val_cur <= 0:
            continue
        yoy = ((val_cur - val_prior) / val_prior * 100
               if val_prior > 0 else None)
        rows.append({
            "ticker": ticker,
            "company": (p.get("entityName") or company)[:60],
            "cik": cik,
            "q_current": cur,
            "val_current_usd": f"{val_cur:.0f}",
            "q_prior": prior,
            "val_prior_usd": (f"{val_prior:.0f}"
                              if val_prior > 0 else ""),
            "yoy_pct": (f"{yoy:.2f}" if yoy is not None else ""),
            "filed_current": p.get("filed", ""),
            "accn_current": p.get("accn", ""),
        })

    # Sort by YoY growth descending (blanks last).
    def sort_key(r: dict) -> tuple[int, float]:
        y = r["yoy_pct"]
        if not y:
            return (1, 0.0)
        return (0, -float(y))

    rows.sort(key=sort_key)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["ticker", "company", "cik", "q_current",
                  "val_current_usd", "q_prior", "val_prior_usd",
                  "yoy_pct", "filed_current", "accn_current",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        paired = [r for r in rows if r["yoy_pct"]]
        top = paired[:5]
        bot = sorted(paired, key=lambda r: float(r["yoy_pct"]))[:5]
        top_s = ", ".join(f"{r['ticker']}+{r['yoy_pct']}%" for r in top)
        bot_s = ", ".join(f"{r['ticker']}{r['yoy_pct']}%" for r in bot)
        print(f"sec_xbrl_revenue: {cur} vs {prior} | {len(rows)} "
              f"tickered filers | top: {top_s} | bot: {bot_s} "
              f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
