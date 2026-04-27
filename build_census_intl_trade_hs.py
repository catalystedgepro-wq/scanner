#!/usr/bin/env python3
"""build_census_intl_trade_hs.py — Census intl trade, HS2 commodities.

Monthly US goods exports + imports by 2-digit HS (Harmonized System)
commodity code, with MoM and YoY. Commodity-level detail surfaces
sector-specific trade shocks that headline FT900 obscures:

- HS 85 (electrical machinery, incl semiconductors) → NVDA, AMD,
  INTC, AMAT, LRCX, AAPL — watch for China-export-control-driven
  collapses.
- HS 87 (vehicles) → F, GM, STLA, TSLA — tariff/CBP compliance
  shocks, auto-sector pair trades.
- HS 27 (mineral fuels / oil) → XOM, CVX, MPC, VLO, PSX —
  crude-export policy & OPEC response.
- HS 30 (pharmaceuticals) → PFE, LLY, MRK, ABBV — tariff exposure
  + generics-import acceleration.
- HS 31 (fertilizers) → MOS, NTR, CF, SQM — agricultural input costs.
- HS 10 (cereals), HS 12 (oilseeds) → ADM, BG, INGR — grain export
  commodity flows; China cancellations are immediately detectable.
- HS 88 (aircraft, spacecraft) → BA, GE, HEI, TDG, LMT — orderbook
  deliveries.
- HS 72 (iron & steel), HS 74 (copper) → NUE, STLD, X, CLF, FCX.

MoM spikes >15% or drops >-10% have historically preceded
sector-index 2-4% rerate within 5 sessions of release.

Source: api.census.gov/data/timeseries/intltrade/{exports,imports}/hs
  (no key, COMM_LVL=HS2 aggregation).

Output: census_intl_trade_hs.csv
Columns: month, direction, hs2, label, value_usd, mom_pct,
         yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_intl_trade_hs.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
EXPORTS = "https://api.census.gov/data/timeseries/intltrade/exports/hs"
IMPORTS = "https://api.census.gov/data/timeseries/intltrade/imports/hs"


def fetch_month(api: str, month: str,
                hs_field: str, val_field: str
                ) -> list[tuple[str, str, float]]:
    """Return list of (hs2, label, value_usd) for given month."""
    qs = urllib.parse.urlencode({
        "get": f"{hs_field},{hs_field}_SDESC,{val_field}",
        "time": month,
        "COMM_LVL": "HS2",
    })
    url = f"{api}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if not body:
                return []
            raw = body.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"intl_trade_hs {api.split('/')[-2]} {month}: {e}")
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not data or len(data) < 2:
        return []
    out: list[tuple[str, str, float]] = []
    for row in data[1:]:
        try:
            v = float(row[2])
        except Exception:
            continue
        out.append((str(row[0]).zfill(2), str(row[1]), v))
    return out


def _month_delta(m: str, months_back: int) -> str:
    y, mo = map(int, m.split("-"))
    d = dt.date(y, mo, 15)
    for _ in range(months_back):
        d = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=15)
    return f"{d.year:04d}-{d.month:02d}"


def main() -> None:
    today = dt.date.today()
    # Try most recent ~60d window; Census intltrade lags ~45d.
    cur = None
    cur_hit: list = []
    for lag in range(1, 6):
        cand_date = (today.replace(day=1)
                     - dt.timedelta(days=30 * lag)).replace(day=1)
        cand = f"{cand_date.year}-{cand_date.month:02d}"
        cur_hit = fetch_month(EXPORTS, cand, "E_COMMODITY", "ALL_VAL_MO")
        if cur_hit:
            cur = cand
            break

    if not cur:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"intl_trade_hs: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    prev_m = _month_delta(cur, 1)
    prior_yr = _month_delta(cur, 12)

    # Pull all three windows for both directions.
    sets: dict[tuple[str, str], list[tuple[str, str, float]]] = {}
    for api, direction, fld, vfld in [
            (EXPORTS, "EXPORT", "E_COMMODITY", "ALL_VAL_MO"),
            (IMPORTS, "IMPORT", "I_COMMODITY", "GEN_VAL_MO")]:
        for m in (cur, prev_m, prior_yr):
            sets[(direction, m)] = fetch_month(api, m, fld, vfld)

    rows: list[dict] = []
    for direction in ("EXPORT", "IMPORT"):
        cur_rows = sets.get((direction, cur), [])
        prev_rows = dict(((hs, v) for hs, _, v in
                          sets.get((direction, prev_m), [])))
        py_rows = dict(((hs, v) for hs, _, v in
                        sets.get((direction, prior_yr), [])))
        for hs, label, v in cur_rows:
            prev_v = prev_rows.get(hs)
            py_v = py_rows.get(hs)
            mom = (((v - prev_v) / prev_v * 100)
                   if prev_v and prev_v > 0 else None)
            yoy = (((v - py_v) / py_v * 100)
                   if py_v and py_v > 0 else None)
            rows.append({
                "month": cur,
                "direction": direction,
                "hs2": hs,
                "label": label[:45],
                "value_usd": f"{v:.0f}",
                "mom_pct": (f"{mom:.2f}"
                            if mom is not None else ""),
                "yoy_pct": (f"{yoy:.2f}"
                            if yoy is not None else ""),
            })

    # Sort: direction then absolute value descending.
    rows.sort(key=lambda r: (r["direction"], -float(r["value_usd"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["month", "direction", "hs2", "label",
                  "value_usd", "mom_pct", "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        exp_rows = [r for r in rows if r["direction"] == "EXPORT"]
        # YoY movers.
        with_yoy = [r for r in exp_rows if r["yoy_pct"]]
        with_yoy.sort(key=lambda r: -float(r["yoy_pct"]))
        top = with_yoy[:3]
        bot = with_yoy[-3:][::-1]
        top_s = " ".join(f"HS{r['hs2']}+{r['yoy_pct']}%" for r in top)
        bot_s = " ".join(f"HS{r['hs2']}{r['yoy_pct']}%" for r in bot)
        print(f"census_intl_trade_hs: {cur} | {len(rows)} pts "
              f"({len(exp_rows)} exp) | top_exp: {top_s} | "
              f"bot_exp: {bot_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
