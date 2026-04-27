#!/usr/bin/env python3
"""build_sec_xbrl_netincome.py — SEC XBRL NetIncomeLoss YoY.

Pulls aggregate NetIncomeLoss (us-gaap) for the most recent closed
calendar quarter vs the same quarter prior year, joins on CIK,
resolves to tickers.

Bottom-line profit deltas are the second leg of the earnings
two-step. Paired with sec_xbrl_revenue this forms the "operating
leverage" read:
- Revenue +25% YoY + NetIncome +60% YoY = leverage trade (best
  class for 60d drift).
- Revenue flat + NetIncome -30% = margin compression, short setup.
- Revenue +10% + NetIncome -10% = cost structure breaking.

CY2025Q4 frame returns ~1,050 filers (vs ~370 for Revenues),
because NetIncomeLoss is tagged by nearly every 10-Q filer while
Revenues has multiple sibling tags (RevenueFromContract...) that
split the population.

Source: data.sec.gov/api/xbrl/frames/us-gaap/NetIncomeLoss/USD/...

Output: sec_xbrl_netincome.csv
Columns: ticker, company, cik, q_current, val_current_usd, q_prior,
         val_prior_usd, yoy_pct, direction, filed_current,
         accn_current, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_xbrl_netincome.csv"
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
        print(f"xbrl_netincome {tag} {period}: {e}")
        return []
    return body.get("data", []) or []


def load_ticker_map() -> dict[str, tuple[str, str]]:
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
    q_ends = [
        (today.year, 1, dt.date(today.year, 3, 31)),
        (today.year, 2, dt.date(today.year, 6, 30)),
        (today.year, 3, dt.date(today.year, 9, 30)),
        (today.year, 4, dt.date(today.year, 12, 31)),
        (today.year - 1, 4, dt.date(today.year - 1, 12, 31)),
        (today.year - 1, 3, dt.date(today.year - 1, 9, 30)),
    ]
    cutoff = today - dt.timedelta(days=60)
    for y, q, end in sorted(q_ends, key=lambda x: x[2], reverse=True):
        if end <= cutoff:
            return y, q
    return today.year - 1, 4


def signed_yoy(cur: float, prior: float) -> float | None:
    """YoY % handling sign flips: loss -> profit reported as +inf."""
    if prior == 0:
        return None
    # Use absolute base so sign flips are interpretable.
    return (cur - prior) / abs(prior) * 100


def main() -> None:
    today = dt.date.today()
    y, q = most_recent_closed_quarter(today)
    cur = f"CY{y}Q{q}"
    prior = f"CY{y-1}Q{q}"

    ticker_map = load_ticker_map()

    cur_data = fetch_frame("NetIncomeLoss", cur)
    if len(cur_data) < 50:
        if q == 1:
            y2, q2 = y - 1, 4
        else:
            y2, q2 = y, q - 1
        cur2 = f"CY{y2}Q{q2}"
        prior2 = f"CY{y2-1}Q{q2}"
        print(f"xbrl_netincome: {cur} thin ({len(cur_data)}), "
              f"falling back to {cur2}")
        cur_data = fetch_frame("NetIncomeLoss", cur2)
        prior_data = fetch_frame("NetIncomeLoss", prior2)
        cur, prior = cur2, prior2
    else:
        prior_data = fetch_frame("NetIncomeLoss", prior)

    if not cur_data and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"xbrl_netincome: no data, keeping existing "
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
        val_prior = prior_by_cik.get(cik, None)
        yoy = (signed_yoy(val_cur, val_prior)
               if val_prior is not None else None)
        # Direction flags: profit→loss / loss→profit are material.
        direction = ""
        if val_prior is not None:
            if val_prior < 0 and val_cur > 0:
                direction = "LOSS_TO_PROFIT"
            elif val_prior > 0 and val_cur < 0:
                direction = "PROFIT_TO_LOSS"
            elif val_cur > 0 and val_prior > 0:
                direction = "PROFIT"
            elif val_cur < 0 and val_prior < 0:
                direction = "LOSS"
        rows.append({
            "ticker": ticker,
            "company": (p.get("entityName") or company)[:60],
            "cik": cik,
            "q_current": cur,
            "val_current_usd": f"{val_cur:.0f}",
            "q_prior": prior,
            "val_prior_usd": (f"{val_prior:.0f}"
                              if val_prior is not None else ""),
            "yoy_pct": (f"{yoy:.2f}" if yoy is not None else ""),
            "direction": direction,
            "filed_current": p.get("filed", ""),
            "accn_current": p.get("accn", ""),
        })

    # Sort: LOSS_TO_PROFIT / big + YoY first; then by yoy desc.
    def sort_key(r: dict) -> tuple[int, float]:
        pri = 0 if r["direction"] == "LOSS_TO_PROFIT" else 1
        try:
            y = -float(r["yoy_pct"]) if r["yoy_pct"] else 1e18
        except ValueError:
            y = 1e18
        return (pri, y)

    rows.sort(key=sort_key)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["ticker", "company", "cik", "q_current",
                  "val_current_usd", "q_prior", "val_prior_usd",
                  "yoy_pct", "direction", "filed_current",
                  "accn_current", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        flips = [r for r in rows
                 if r["direction"] == "LOSS_TO_PROFIT"][:5]
        reversals = [r for r in rows
                     if r["direction"] == "PROFIT_TO_LOSS"][:5]
        flip_s = ", ".join(f"{r['ticker']}" for r in flips) or "-"
        rev_s = ", ".join(f"{r['ticker']}" for r in reversals) or "-"
        print(f"sec_xbrl_netincome: {cur} vs {prior} | {len(rows)} "
              f"tickered | loss->profit: {flip_s} | "
              f"profit->loss: {rev_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
