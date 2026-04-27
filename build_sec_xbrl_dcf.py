#!/usr/bin/env python3
"""build_sec_xbrl_dcf.py — two-stage Damodaran DCF from SEC XBRL companyfacts.

Output: sec_xbrl_dcf.csv (one row per ticker scored)
Columns:
    ticker, company, cik,
    fcf_ttm, fcf_3y_avg, fcf_5y_avg,
    revenue_ttm, revenue_5y_cagr,
    shares_out, cash, total_debt,
    wacc, growth_stage1, growth_terminal, horizon_years,
    pv_stage1, pv_terminal, enterprise_value, equity_value,
    intrinsic_value_per_share, current_price,
    upside_pct, dcf_grade, method_notes, captured_at

Methodology (two-stage Damodaran model):
    FCF_t = FCF_0 * (1+g1)^t   for t = 1..5
    TV = FCF_5 * (1+g2) / (WACC - g2)
    PV_stage1 = Σ FCF_t / (1+WACC)^t
    PV_terminal = TV / (1+WACC)^5
    Enterprise value = PV_stage1 + PV_terminal
    Equity value = EV + Cash - Total Debt
    Intrinsic per share = Equity / Shares outstanding
    Upside = intrinsic / current_price - 1

Defaults (can be overridden per sector later):
    WACC = 9% (S&P median ~8-10%)
    g1 (stage-1 growth) = min(revenue_5y_cagr capped at 12%, else 4%)
    g2 (terminal growth) = 2.5% (GDP proxy)
    horizon = 5 years

Guards:
    - Skip tickers without 5+ years of OCF data (can't compute FCF)
    - Skip WACC ≤ terminal growth (blows up terminal value)
    - Cap upside at ±500% (protects against data outliers)
    - Grade:
        A: upside >= +50%
        B: +20% to +50%
        C: 0 to +20%
        D: -20% to 0
        F: < -20%

Runs against tickers already in our catalyst universe (sec_top_gappers +
convergence_alerts) to keep the dataset actionable, not academic.

Source: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
Stdlib only.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_xbrl_dcf.csv"
TICKER_MAP = ROOT / "ticker_cik_map.json"
CACHE_DIR = ROOT / ".dcf_companyfacts_cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_DAYS = 7  # XBRL data changes quarterly; 7-day cache keeps SEC happy

UA = "CatalystEdge/1.0 (opensource@example.com)"
API_BASE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

WACC_DEFAULT      = 0.09   # 9%
G_TERMINAL        = 0.025  # 2.5% GDP proxy
G_STAGE1_CAP      = 0.12   # 12% max stage-1 growth
G_STAGE1_FLOOR    = 0.02   # 2% fallback when we can't compute revenue CAGR
HORIZON_YEARS     = 5
MAX_UPSIDE_PCT    = 500.0  # clip extreme DCF outputs
MIN_YEARS_OF_DATA = 3      # need at least 3 annual FCF points

RATE_LIMIT_SEC = 0.11  # SEC asks for <=10 req/s


def fetch_companyfacts(cik: str) -> dict | None:
    """Fetch + cache company XBRL facts. cik is zero-padded 10-digit string."""
    cache_file = CACHE_DIR / f"{cik}.json"
    if cache_file.exists():
        age_days = (dt.datetime.now().timestamp() - cache_file.stat().st_mtime) / 86400
        if age_days < CACHE_TTL_DAYS:
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
    url = API_BASE.format(cik=cik)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        time.sleep(RATE_LIMIT_SEC)
        data = json.loads(raw)
        cache_file.write_text(json.dumps(data), encoding="utf-8")
        return data
    except Exception as e:
        # Note + continue
        print(f"  [WARN] {cik}: {e}")
        return None


def _annual_series(facts: dict, tag: str, unit: str = "USD") -> list[tuple[str, float]]:
    """Extract annual (FY) values for a GAAP tag. Returns list of (fy, value)."""
    try:
        entries = (facts.get("facts", {})
                        .get("us-gaap", {})
                        .get(tag, {})
                        .get("units", {})
                        .get(unit, []))
    except Exception:
        return []
    annual: dict[int, float] = {}
    for e in entries:
        fp = e.get("fp")  # FY or Q1-Q4
        if fp != "FY":
            continue
        fy = e.get("fy")
        val = e.get("val")
        if fy is None or val is None:
            continue
        # Prefer the latest filing for each FY (10-K/A over 10-K)
        if fy not in annual or e.get("filed", "") > str(annual.get(fy, "")):
            annual[fy] = float(val)
    return sorted(annual.items())


def _latest_scalar(facts: dict, tag: str, namespace: str = "us-gaap",
                   unit: str = "USD") -> float | None:
    try:
        entries = (facts.get("facts", {})
                        .get(namespace, {})
                        .get(tag, {})
                        .get("units", {})
                        .get(unit, []))
    except Exception:
        return None
    if not entries:
        return None
    entries = sorted(entries, key=lambda x: x.get("end", ""), reverse=True)
    return float(entries[0].get("val"))


def _shares_out(facts: dict) -> float | None:
    """Entity shares out comes from dei namespace, unit 'shares'."""
    return _latest_scalar(facts, "EntityCommonStockSharesOutstanding",
                          namespace="dei", unit="shares")


def compute_dcf(facts: dict, current_price: float) -> dict | None:
    """Run the two-stage DCF. Returns None if inputs insufficient."""
    ocf = _annual_series(facts, "NetCashProvidedByUsedInOperatingActivities")
    if not ocf or len(ocf) < MIN_YEARS_OF_DATA:
        return None
    capex = _annual_series(facts, "PaymentsToAcquirePropertyPlantAndEquipment")
    capex_map = {fy: v for fy, v in capex}
    # Build annual FCF = OCF - CapEx (CapEx missing → treat as 0)
    fcf: list[tuple[int, float]] = []
    for fy, ocf_v in ocf:
        fcf.append((fy, ocf_v - capex_map.get(fy, 0.0)))
    if len(fcf) < MIN_YEARS_OF_DATA:
        return None
    fcf = sorted(fcf)
    fcf_ttm = fcf[-1][1]
    fcf_3y_avg = sum(v for _, v in fcf[-3:]) / max(1, len(fcf[-3:]))
    fcf_5y_avg = sum(v for _, v in fcf[-5:]) / max(1, len(fcf[-5:]))

    # Revenue CAGR for stage-1 growth estimate
    rev = _annual_series(facts, "Revenues") or _annual_series(facts, "RevenueFromContractWithCustomerExcludingAssessedTax")
    g1 = G_STAGE1_FLOOR
    rev_cagr = 0.0
    revenue_ttm = 0.0
    if rev and len(rev) >= 2:
        first_fy, first_rev = rev[-min(5, len(rev))]
        last_fy, last_rev = rev[-1]
        years = max(1, last_fy - first_fy)
        revenue_ttm = last_rev
        if first_rev > 0 and last_rev > 0:
            rev_cagr = (last_rev / first_rev) ** (1/years) - 1
            g1 = max(G_STAGE1_FLOOR, min(G_STAGE1_CAP, rev_cagr))

    shares = _shares_out(facts) or 0
    cash = _latest_scalar(facts, "CashAndCashEquivalentsAtCarryingValue") or 0
    debt_lt = _latest_scalar(facts, "LongTermDebtNoncurrent") or 0
    debt_st = _latest_scalar(facts, "LongTermDebtCurrent") or 0
    total_debt = debt_lt + debt_st

    # Base FCF for projection: require BOTH TTM >= 0 AND 3y avg >= 0.
    # Refusing negative 3y historical prevents "lucky quarter" inflation
    # where TTM is positive but the business is structurally unprofitable.
    if fcf_3y_avg <= 0 or fcf_ttm <= 0:
        return {
            "fcf_ttm": fcf_ttm, "fcf_3y_avg": fcf_3y_avg, "fcf_5y_avg": fcf_5y_avg,
            "revenue_ttm": revenue_ttm, "revenue_5y_cagr": round(rev_cagr, 4),
            "shares_out": shares, "cash": cash, "total_debt": total_debt,
            "wacc": WACC_DEFAULT, "growth_stage1": g1, "growth_terminal": G_TERMINAL,
            "horizon_years": HORIZON_YEARS,
            "pv_stage1": 0, "pv_terminal": 0, "enterprise_value": 0,
            "equity_value": cash - total_debt,
            "intrinsic_value_per_share": 0,
            "current_price": current_price,
            "upside_pct": -100.0,
            "dcf_grade": "F",
            "method_notes": "negative_fcf_base",
        }
    # Minimum shares-out sanity check. dei tag sometimes reports a class
    # subset (e.g. ADR units only), producing 1000x-inflated intrinsic/share.
    if shares < 1_000_000:
        return {
            "fcf_ttm": fcf_ttm, "fcf_3y_avg": fcf_3y_avg, "fcf_5y_avg": fcf_5y_avg,
            "revenue_ttm": revenue_ttm, "revenue_5y_cagr": round(rev_cagr, 4),
            "shares_out": shares, "cash": cash, "total_debt": total_debt,
            "wacc": WACC_DEFAULT, "growth_stage1": g1, "growth_terminal": G_TERMINAL,
            "horizon_years": HORIZON_YEARS,
            "pv_stage1": 0, "pv_terminal": 0, "enterprise_value": 0,
            "equity_value": 0,
            "intrinsic_value_per_share": 0,
            "current_price": current_price,
            "upside_pct": 0,
            "dcf_grade": "",
            "method_notes": "shares_out_too_low_skip",
        }

    fcf_base = fcf_3y_avg   # use 3y avg (both positive confirmed above)
    wacc = WACC_DEFAULT
    if wacc <= G_TERMINAL:
        return None

    # Project FCF for 5 years, discount each
    pv_stage1 = 0.0
    fcf_last = fcf_base
    for t in range(1, HORIZON_YEARS + 1):
        fcf_last = fcf_base * (1 + g1) ** t
        pv_stage1 += fcf_last / (1 + wacc) ** t
    tv = fcf_last * (1 + G_TERMINAL) / (wacc - G_TERMINAL)
    pv_terminal = tv / (1 + wacc) ** HORIZON_YEARS

    ev = pv_stage1 + pv_terminal
    equity_value = ev + cash - total_debt
    ivps = equity_value / shares if shares > 0 else 0

    # Sanity check: intrinsic > 20x current price almost always means the
    # shares_out or FCF is wrong. Flag as F + note rather than claim alpha.
    if current_price > 0 and ivps > 20 * current_price:
        return {
            "fcf_ttm": fcf_ttm, "fcf_3y_avg": fcf_3y_avg, "fcf_5y_avg": fcf_5y_avg,
            "revenue_ttm": revenue_ttm, "revenue_5y_cagr": round(rev_cagr, 4),
            "shares_out": shares, "cash": cash, "total_debt": total_debt,
            "wacc": wacc, "growth_stage1": round(g1, 4),
            "growth_terminal": G_TERMINAL, "horizon_years": HORIZON_YEARS,
            "pv_stage1": pv_stage1, "pv_terminal": pv_terminal,
            "enterprise_value": ev, "equity_value": equity_value,
            "intrinsic_value_per_share": ivps,
            "current_price": current_price,
            "upside_pct": 0,
            "dcf_grade": "",
            "method_notes": "suspect_intrinsic_gt_20x_price_skip",
        }

    upside = 0.0
    if current_price > 0 and ivps > 0:
        upside = (ivps / current_price - 1) * 100
        upside = max(-MAX_UPSIDE_PCT, min(MAX_UPSIDE_PCT, upside))

    # Grade — tightened to require higher upside for A/B (was 50/20)
    if upside >= 100:   grade = "A"    # 2x+ upside
    elif upside >= 40:  grade = "B"    # 1.4x+ upside
    elif upside >= 10:  grade = "C"    # mild undervalued
    elif upside >= -15: grade = "D"    # fair value zone
    else:               grade = "F"    # overvalued

    return {
        "fcf_ttm": fcf_ttm, "fcf_3y_avg": fcf_3y_avg, "fcf_5y_avg": fcf_5y_avg,
        "revenue_ttm": revenue_ttm, "revenue_5y_cagr": round(rev_cagr, 4),
        "shares_out": shares, "cash": cash, "total_debt": total_debt,
        "wacc": wacc, "growth_stage1": round(g1, 4),
        "growth_terminal": G_TERMINAL, "horizon_years": HORIZON_YEARS,
        "pv_stage1": pv_stage1, "pv_terminal": pv_terminal,
        "enterprise_value": ev, "equity_value": equity_value,
        "intrinsic_value_per_share": ivps,
        "current_price": current_price,
        "upside_pct": round(upside, 1),
        "dcf_grade": grade,
        "method_notes": "two_stage_damodaran_v1",
    }


def load_ticker_cik_map() -> dict[str, tuple[str, str]]:
    """Returns ticker -> (zero-padded CIK, company name)."""
    if not TICKER_MAP.exists():
        return {}
    raw = json.loads(TICKER_MAP.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, str]] = {}
    for cik_str, val in raw.items():
        if not isinstance(val, list) or len(val) < 2:
            continue
        ticker, name = val[0], val[1]
        if ticker and ticker not in out:
            out[ticker.upper()] = (cik_str, name)
    return out


def load_universe() -> set[str]:
    """Combined catalyst universe from top gappers + convergence alerts."""
    tickers: set[str] = set()
    for src in ("sec_top_gappers.csv", "convergence_alerts.csv", "combined_priority.csv"):
        p = ROOT / src
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = (row.get("ticker") or "").strip().upper()
                    if t and t.isalpha() and 1 <= len(t) <= 5:
                        tickers.add(t)
        except Exception:
            pass
    return tickers


def load_quote_cache() -> dict[str, float]:
    p = ROOT / ".sec_quote_cache.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {k.upper(): float((v.get("data") or {}).get("price") or 0)
                for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        return {}


def main() -> int:
    tk_map = load_ticker_cik_map()
    if not tk_map:
        print("sec_xbrl_dcf: no ticker_cik_map.json — abort")
        return 1
    universe = load_universe()
    if not universe:
        print("sec_xbrl_dcf: empty universe — abort")
        return 1
    quotes = load_quote_cache()
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    # Limit per-run to keep SEC happy (10 req/sec budget).
    # Prioritize: tickers WITH a price we can compare upside to.
    prioritized = sorted(universe, key=lambda t: 0 if quotes.get(t, 0) > 0 else 1)
    # Further prioritize cache hits so re-runs complete fast and always produce output.
    def _cache_ready(t: str) -> bool:
        cik_name = tk_map.get(t)
        if not cik_name:
            return False
        return (CACHE_DIR / f"{cik_name[0]}.json").exists()
    prioritized = sorted(prioritized, key=lambda t: 0 if _cache_ready(t) else 1)
    LIMIT = 200

    fields = [
        "ticker", "company", "cik",
        "fcf_ttm", "fcf_3y_avg", "fcf_5y_avg",
        "revenue_ttm", "revenue_5y_cagr",
        "shares_out", "cash", "total_debt",
        "wacc", "growth_stage1", "growth_terminal", "horizon_years",
        "pv_stage1", "pv_terminal", "enterprise_value", "equity_value",
        "intrinsic_value_per_share", "current_price",
        "upside_pct", "dcf_grade", "method_notes", "captured_at",
    ]

    rows: list[dict] = []
    processed = 0
    scored = 0
    grades: dict[str, int] = {}

    for t in prioritized[:LIMIT]:
        cik_name = tk_map.get(t)
        if not cik_name:
            continue
        cik, name = cik_name
        facts = fetch_companyfacts(cik)
        if not facts:
            continue
        processed += 1
        price = quotes.get(t, 0.0)
        result = compute_dcf(facts, price)
        if not result:
            continue
        row = {
            "ticker": t,
            "company": (name or "")[:120],
            "cik": cik,
            **result,
            "captured_at": captured_at,
        }
        rows.append(row)
        scored += 1
        grades[row["dcf_grade"]] = grades.get(row["dcf_grade"], 0) + 1

    # Sort by upside descending (A+ grades first)
    rows.sort(key=lambda r: -r.get("upside_pct", -999))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            # Round floats for compact output
            for k in ("fcf_ttm","fcf_3y_avg","fcf_5y_avg","revenue_ttm","shares_out",
                      "cash","total_debt","pv_stage1","pv_terminal","enterprise_value",
                      "equity_value","intrinsic_value_per_share","current_price"):
                if isinstance(r.get(k), float):
                    r[k] = round(r[k], 2)
            w.writerow(r)

    dist = " ".join(f"{g}={grades[g]}" for g in sorted(grades))
    top_a = [r for r in rows if r["dcf_grade"] == "A"][:5]
    sample = " ".join(f"{r['ticker']}:+{r['upside_pct']:.0f}%" for r in top_a)
    print(f"sec_xbrl_dcf: processed={processed} scored={scored} | grades: {dist}")
    if sample:
        print(f"  top A-grades: {sample}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
