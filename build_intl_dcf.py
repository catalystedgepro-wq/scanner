#!/usr/bin/env python3
"""build_intl_dcf.py — two-stage Damodaran DCF for international equities.

Uses the yfinance library (handles Yahoo's crumb/cookie auth automatically)
to pull cashflow, balance sheet, income statement, and quote info for any
global ticker. Same math as build_sec_xbrl_dcf.py:

  FCF      = OCF − |CapEx|, 3-year average
  Stage 1  = 5 years growth at clamped revenue CAGR (0-25%)
  Stage 2  = Gordon terminal value, 2.5% growth / 9% WACC
  Bridge   = enterprise value + cash − debt → intrinsic per share
  Grade    = A≥100% / B≥40% / C≥10% / D≥-15% / F<-15% upside

Sanity gates: fcf_3y_avg > 0, fcf_ttm > 0, shares ≥ 1M, intrinsic < 20×price.

Output:
  docs/intl_dcf.csv (full table)
  docs/data/intl_dcf.json (summary payload for /dcf/international/)

Universe: tickers from intl_equity_gappers.csv. Concurrent fetches via
ThreadPoolExecutor (8 workers) keep total runtime under ~120s.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# yfinance is noisy with deprecation warnings on some tickers — silence.
warnings.filterwarnings("ignore")

import yfinance as yf  # noqa: E402


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_intl_dcf.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
GAPPERS = ROOT / "docs/intl_equity_gappers.csv"
OUT_CSV = ROOT / "docs/intl_dcf.csv"
OUT_JSON = ROOT / "docs/data/intl_dcf.json"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

WORKERS = 8
WACC = 0.09
TERMINAL_GROWTH = 0.025
HORIZON_YEARS = 5
GROWTH_CAP = 0.25
SHARES_MIN = 1_000_000
INTRINSIC_MULT_CAP = 20.0


def grade_for(upside_pct: float) -> str:
    if upside_pct >= 100: return "A"
    if upside_pct >= 40:  return "B"
    if upside_pct >= 10:  return "C"
    if upside_pct >= -15: return "D"
    return "F"


def _row_get(df, names: tuple) -> list:
    """Return a row from yfinance DataFrame matching any of the given names."""
    if df is None or df.empty:
        return []
    for n in names:
        if n in df.index:
            row = df.loc[n]
            return [v for v in row.tolist() if v is not None and not _isnan(v)]
    return []


def _isnan(v) -> bool:
    try:
        return v != v  # NaN check
    except Exception:
        return False


def compute_dcf(ticker: str, name: str, country: str, currency: str) -> dict | None:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        t = yf.Ticker(ticker)
        cf = t.cashflow
        bs = t.balance_sheet
        inc = t.income_stmt
        info = t.info or {}
    except Exception:
        return None

    # FCF history: prefer "Free Cash Flow" if reported; else compute OCF − |CapEx|.
    fcf_history = _row_get(cf, ("Free Cash Flow",))
    if not fcf_history:
        ocf = _row_get(cf, (
            "Operating Cash Flow",
            "Total Cash From Operating Activities",
            "Cash Flow From Continuing Operating Activities",
        ))
        capex = _row_get(cf, ("Capital Expenditure", "Capital Expenditures"))
        if not (ocf and capex):
            return None
        n = min(len(ocf), len(capex))
        fcf_history = [ocf[i] - abs(capex[i]) for i in range(n)]

    if len(fcf_history) < 2:
        return None
    fcf_ttm = fcf_history[0]
    fcf_3y_avg = sum(fcf_history[:3]) / min(3, len(fcf_history))

    # Revenue history → CAGR
    revenues = _row_get(inc, ("Total Revenue",))
    revenue_ttm = revenues[0] if revenues else 0
    revenue_cagr = 0.0
    if len(revenues) >= 2 and revenues[-1] > 0:
        years = max(1, len(revenues) - 1)
        revenue_cagr = (revenues[0] / revenues[-1]) ** (1 / years) - 1
    revenue_cagr = max(0.0, min(GROWTH_CAP, revenue_cagr))

    # Balance sheet
    cash_list = _row_get(bs, (
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash Financial",
    ))
    debt_list = _row_get(bs, (
        "Total Debt", "Total Liabilities Net Minority Interest",
    ))
    cash = cash_list[0] if cash_list else 0
    debt = debt_list[0] if debt_list else 0

    # Quote info
    price = info.get("currentPrice") or info.get("regularMarketPrice") \
        or info.get("previousClose")
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 0
    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    if not price or price <= 0 or shares < SHARES_MIN:
        return None
    if currency in (None, "", "USD"):
        currency = info.get("financialCurrency") or info.get("currency") or "USD"

    # Sanity guard: negative FCF
    if fcf_3y_avg <= 0 or fcf_ttm <= 0:
        return {
            "ticker": ticker, "name": name, "country": country,
            "currency": currency, "current_price": round(price, 2),
            "fcf_ttm": round(fcf_ttm, 0), "fcf_3y_avg": round(fcf_3y_avg, 0),
            "intrinsic_per_share": None, "upside_pct": None,
            "grade": "N/A", "method_notes": "negative_fcf",
            "captured_at": captured,
        }

    # Stage 1
    pv_stage1 = 0.0
    for tt in range(1, HORIZON_YEARS + 1):
        fcf_t = fcf_3y_avg * ((1 + revenue_cagr) ** tt)
        pv_stage1 += fcf_t / ((1 + WACC) ** tt)

    # Stage 2 terminal
    fcf_year5 = fcf_3y_avg * ((1 + revenue_cagr) ** HORIZON_YEARS)
    terminal_value = (fcf_year5 * (1 + TERMINAL_GROWTH)) / (WACC - TERMINAL_GROWTH)
    pv_terminal = terminal_value / ((1 + WACC) ** HORIZON_YEARS)

    enterprise_value = pv_stage1 + pv_terminal
    equity_value = enterprise_value + cash - debt
    intrinsic_per_share = equity_value / shares

    # Sector-aware sanity. FCF-based DCF systematically overstates value for
    # banks/insurance because reported "operating cash flow" includes deposit
    # float and reserves that aren't truly distributable. We cap intrinsic at
    # 3× price for financials — anything higher is a model failure, not signal.
    is_financial = "Financ" in (sector or "") or "Insurance" in (industry or "")
    cap = 3.0 if is_financial else INTRINSIC_MULT_CAP
    if intrinsic_per_share <= 0 or intrinsic_per_share / price > cap:
        return {
            "ticker": ticker, "name": name, "country": country,
            "currency": currency, "current_price": round(price, 2),
            "fcf_ttm": round(fcf_ttm, 0), "fcf_3y_avg": round(fcf_3y_avg, 0),
            "intrinsic_per_share": None, "upside_pct": None,
            "grade": "N/A",
            "method_notes": "sanity_reject_financial" if is_financial else "sanity_reject",
            "captured_at": captured,
        }

    upside_pct = (intrinsic_per_share - price) / price * 100
    grade = grade_for(upside_pct)
    return {
        "ticker": ticker, "name": name, "country": country, "currency": currency,
        "sector": sector, "industry": industry,
        "current_price": round(price, 2),
        "fcf_ttm": round(fcf_ttm, 0), "fcf_3y_avg": round(fcf_3y_avg, 0),
        "revenue_ttm": round(revenue_ttm, 0),
        "revenue_cagr": round(revenue_cagr, 4),
        "shares_out": int(shares),
        "cash": round(cash, 0), "total_debt": round(debt, 0),
        "wacc": WACC, "terminal_growth": TERMINAL_GROWTH,
        "horizon_years": HORIZON_YEARS,
        "pv_stage1": round(pv_stage1, 0),
        "pv_terminal": round(pv_terminal, 0),
        "enterprise_value": round(enterprise_value, 0),
        "equity_value": round(equity_value, 0),
        "intrinsic_per_share": round(intrinsic_per_share, 2),
        "upside_pct": round(upside_pct, 2),
        "grade": grade,
        "method_notes": "two_stage_damodaran_v1_yfinance",
        "captured_at": captured,
    }


def main() -> int:
    if not GAPPERS.exists():
        print(f"missing {GAPPERS}")
        return 1

    universe: list[tuple[str, str, str, str]] = []
    with GAPPERS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip()
            if not t:
                continue
            universe.append((
                t, r.get("name", "") or "",
                r.get("country_full", "") or "",
                r.get("currency", "USD") or "USD",
            ))

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(lambda u: compute_dcf(*u), universe):
            if r is not None:
                rows.append(r)

    graded = [r for r in rows if r.get("upside_pct") is not None]
    graded.sort(key=lambda r: r["upside_pct"], reverse=True)
    ungraded = [r for r in rows if r.get("upside_pct") is None]
    final = graded + ungraded

    if final:
        keys: list[str] = []
        seen = set()
        for r in final:
            for k in r.keys():
                if k not in seen:
                    keys.append(k); seen.add(k)
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in final:
                w.writerow(r)

    counts = {g: sum(1 for r in graded if r["grade"] == g)
              for g in ("A", "B", "C", "D", "F")}

    by_country: dict = {}
    for r in graded:
        by_country.setdefault(r.get("country", ""), []).append(r)
    by_country_payload = {
        c: {
            "count": len(rs),
            "avg_upside": round(sum(r["upside_pct"] for r in rs) / len(rs), 1),
            "a_grade": sum(1 for r in rs if r["grade"] == "A"),
            "top": rs[0]["ticker"] if rs else "",
        } for c, rs in by_country.items()
    }
    by_sector: dict = {}
    for r in graded:
        by_sector.setdefault(r.get("sector", "") or "Other", []).append(r)
    by_sector_payload = {
        s: {
            "count": len(rs),
            "avg_upside": round(sum(r["upside_pct"] for r in rs) / len(rs), 1),
            "a_grade": sum(1 for r in rs if r["grade"] == "A"),
        } for s, rs in by_sector.items()
    }

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "total_attempted": len(universe),
        "scored": len(graded),
        "rejected_negative_fcf": sum(1 for r in ungraded if r.get("method_notes") == "negative_fcf"),
        "rejected_sanity": sum(1 for r in ungraded if r.get("method_notes") == "sanity_reject"),
        "grade_counts": counts,
        "top_undervalued": graded[:30],
        "top_overvalued": graded[-15:][::-1] if len(graded) > 15 else [],
        "by_country": by_country_payload,
        "by_sector": by_sector_payload,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    a, b, c, d, f = (counts.get(k, 0) for k in ("A", "B", "C", "D", "F"))
    print(f"intl_dcf: {len(final)} processed | scored={len(graded)} | "
          f"A={a} B={b} C={c} D={d} F={f} | "
          f"countries={len(by_country)} | sectors={len(by_sector)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
