#!/usr/bin/env python3
"""build_census_trade_china.py — US-China bilateral goods trade.

Monthly US exports-to-China and imports-from-China by 2-digit HS
(Harmonized System) commodity, with MoM and YoY change vs same
month prior year. China CTY_CODE=5700 in Census intltrade API.

Why China-specific bilateral matters for trading:
- Tariff escalations show up as import-value collapses before
  they show up on earnings calls. Detect month-before-earnings.
- Export-control policy on HS85 (semiconductors) → NVDA, AMD,
  INTC, LRCX, AMAT, AAPL watch. Sudden US→CN HS85 collapse =
  new export restriction active.
- HS87 (vehicles) exports to China → TSLA, GM, F tell. China
  retaliatory tariffs historically hit US autos first.
- HS10, HS12 (grains, oilseeds) → ADM, BG, AGCO. Chinese
  agricultural cancellations are immediate signal.
- HS30 (pharma) imports from China → PFE, LLY, MRK API sourcing.
  Chinese API export bans = US pharma margin crunch.
- HS72, HS73 (iron/steel) → NUE, STLD, X. Chinese steel dumping
  cycles visible in import-price changes.
- Total bilateral deficit widening = Treasury FX intervention risk.

Captures additional countries for triangulation:
  5700 CHINA  4280 GERMANY  5830 JAPAN  5330 SOUTH KOREA
  2010 MEXICO 1220 CANADA  5890 TAIWAN

Source: api.census.gov/data/timeseries/intltrade/{exports,imports}/hs
  (no key; CTY_CODE + COMM_LVL=HS2 dimension).

Output: census_trade_china.csv
Columns: month, direction, country, cty_code, hs2, value_usd,
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
OUT_CSV = ROOT / "census_trade_china.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
EXPORTS = "https://api.census.gov/data/timeseries/intltrade/exports/hs"
IMPORTS = "https://api.census.gov/data/timeseries/intltrade/imports/hs"

COUNTRIES = {
    "5700": "CHINA",
    "4280": "GERMANY",
    "5830": "JAPAN",
    "5800": "KOREA_SOUTH",
    "2010": "MEXICO",
    "1220": "CANADA",
    "5830": "JAPAN",
    "5890": "TAIWAN",
}

# HS2 codes of trading interest — narrow to manageable set.
HS_WATCHLIST = [
    "10",  # cereals (grains)
    "12",  # oilseeds
    "27",  # mineral fuels / oil
    "29",  # organic chemicals (pharma APIs)
    "30",  # pharmaceuticals
    "31",  # fertilizers
    "39",  # plastics
    "52",  # cotton
    "72",  # iron/steel
    "73",  # steel articles
    "74",  # copper
    "76",  # aluminum
    "84",  # machinery
    "85",  # electrical machinery (semis)
    "87",  # vehicles
    "88",  # aircraft
    "90",  # optical/medical
    "94",  # furniture
    "95",  # toys
]


def fetch(api: str, cty: str, hs: str, month: str,
          hs_fld: str, val_fld: str) -> float | None:
    qs = urllib.parse.urlencode({
        "get": f"{hs_fld},{val_fld}",
        "time": month,
        "COMM_LVL": "HS2",
        "CTY_CODE": cty,
        hs_fld: hs,
    })
    url = f"{api}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if not body:
                return None
            raw = body.decode("utf-8", errors="ignore")
    except Exception:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not data or len(data) < 2:
        return None
    try:
        return float(data[1][1])
    except Exception:
        return None


def _month_delta(m: str, months_back: int) -> str:
    y, mo = map(int, m.split("-"))
    d = dt.date(y, mo, 15)
    for _ in range(months_back):
        d = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=15)
    return f"{d.year:04d}-{d.month:02d}"


def main() -> None:
    today = dt.date.today()
    # Walk back to find most recent published month.
    cur = None
    for lag in range(1, 6):
        cand_date = (today.replace(day=1)
                     - dt.timedelta(days=30 * lag)).replace(day=1)
        cand = f"{cand_date.year}-{cand_date.month:02d}"
        # Probe with China HS85.
        probe = fetch(EXPORTS, "5700", "85", cand,
                      "E_COMMODITY", "ALL_VAL_MO")
        if probe is not None:
            cur = cand
            break

    if not cur:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"census_trade_china: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    prior_yr = _month_delta(cur, 12)

    rows: list[dict] = []
    for cty, name in COUNTRIES.items():
        for hs in HS_WATCHLIST:
            # Exports
            cur_v = fetch(EXPORTS, cty, hs, cur,
                          "E_COMMODITY", "ALL_VAL_MO")
            py_v = fetch(EXPORTS, cty, hs, prior_yr,
                         "E_COMMODITY", "ALL_VAL_MO")
            if cur_v is not None:
                yoy = (((cur_v - py_v) / py_v * 100)
                       if py_v and py_v > 0 else None)
                rows.append({
                    "month": cur,
                    "direction": "EXPORT",
                    "country": name,
                    "cty_code": cty,
                    "hs2": hs.zfill(2),
                    "value_usd": f"{cur_v:.0f}",
                    "yoy_pct": (f"{yoy:.2f}"
                                if yoy is not None else ""),
                })
            # Imports
            cur_i = fetch(IMPORTS, cty, hs, cur,
                          "I_COMMODITY", "GEN_VAL_MO")
            py_i = fetch(IMPORTS, cty, hs, prior_yr,
                         "I_COMMODITY", "GEN_VAL_MO")
            if cur_i is not None:
                yoy = (((cur_i - py_i) / py_i * 100)
                       if py_i and py_i > 0 else None)
                rows.append({
                    "month": cur,
                    "direction": "IMPORT",
                    "country": name,
                    "cty_code": cty,
                    "hs2": hs.zfill(2),
                    "value_usd": f"{cur_i:.0f}",
                    "yoy_pct": (f"{yoy:.2f}"
                                if yoy is not None else ""),
                })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"census_trade_china: no rows, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["country"], r["direction"],
                              -float(r["value_usd"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["month", "direction", "country", "cty_code",
                  "hs2", "value_usd", "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: top China YoY movers.
    cn_exp = [r for r in rows
              if r["country"] == "CHINA"
              and r["direction"] == "EXPORT"
              and r["yoy_pct"]]
    cn_exp.sort(key=lambda r: -float(r["yoy_pct"]))
    top = cn_exp[:3]
    bot = cn_exp[-3:][::-1]
    top_s = " ".join(f"HS{r['hs2']}+{r['yoy_pct']}%" for r in top)
    bot_s = " ".join(f"HS{r['hs2']}{r['yoy_pct']}%" for r in bot)
    print(f"census_trade_china: {cur} | {len(rows)} pts | "
          f"CN_exp_top: {top_s} | CN_exp_bot: {bot_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
