#!/usr/bin/env python3
"""build_macro_bundle.py — Consolidated FRED macro series (scheduled releases).

Single file captures the major monthly/weekly macro prints the
scanner wasn't covering yet. Each print is a scheduled calendar
catalyst that moves sector rotation:

- Retail sales (RSAFS) → XLY, XRT, AMZN, WMT, TGT, LOW, HD
- Industrial production (INDPRO) → XLI, CAT, DE, GE
- Capacity utilization (TCU) → cyclicals, materials
- Consumer confidence (UMCSENT) → consumer discretionary
- Conference Board LEI (USSLIND already in leading_index)
- Housing starts (HOUST) → XHB, LEN, DHI, PHM, TOL
- Existing home sales (EXHOSLUSM495S) → ZG, RDFN, COMP
- Business inventories (BUSINV) → macro slowdown signal
- NFCI financial conditions (NFCI) → risk-on/risk-off gauge
- Retail inventories (RETAILIRSA) → inventory de-stocking
- Total vehicle sales (TOTALSA) → GM, F, STLA

Source: FRED fredgraph.csv (no auth).
Output: macro_bundle.csv
Columns: series_alias, series_id, date, value, yoy_pct, mom_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "macro_bundle.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("retail_sales", "RSAFS"),
    ("retail_sales_ex_auto", "RSFSXMV"),
    ("industrial_production", "INDPRO"),
    ("capacity_utilization", "TCU"),
    ("consumer_sentiment_um", "UMCSENT"),
    ("housing_starts", "HOUST"),
    ("building_permits", "PERMIT"),
    ("existing_home_sales", "EXHOSLUSM495S"),
    ("new_home_sales", "HSN1F"),
    ("business_inventories", "BUSINV"),
    ("retail_inventories", "RETAILIRSA"),
    ("nfci", "NFCI"),
    ("ansfci", "ANFCI"),
    ("total_vehicle_sales", "TOTALSA"),
    ("truck_sales", "LTRUCKSA"),
    ("freight_trans_index", "TSIFRGHTM"),
    ("chicago_pmi", "NAPM"),
    ("markit_pmi_mfg", "USAMANPMI"),
    ("ten_year_yield", "DGS10"),
    ("two_year_yield", "DGS2"),
    ("tenyr_breakeven", "T10YIE"),
    ("ig_spread", "BAMLC0A0CM"),
    ("hy_spread", "BAMLH0A0HYM2"),
    ("financial_stress_kc", "KCFSI"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"macro {sid}: {e}")
        return []
    out = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if v in {".", ""}:
            continue
        try:
            out.append((d, float(v)))
        except Exception:
            pass
    return out[-60:]


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for alias, sid in SERIES:
        data = fetch(sid)
        if not data:
            continue
        data.sort(key=lambda x: x[0])
        recent = data[-24:]
        for i, (d, v) in enumerate(recent):
            mom = ""
            yoy = ""
            if i > 0:
                prev = recent[i - 1][1]
                if prev:
                    mom = f"{(v - prev) / prev * 100:+.2f}"
            # YoY from the full series if available
            full_idx = {x[0]: x[1] for x in data}
            try:
                d_dt = dt.date.fromisoformat(d)
                y_dt = d_dt.replace(year=d_dt.year - 1)
                # Nearest prior-year value
                cands = [(k, x) for k, x in full_idx.items()
                         if k[:7] == y_dt.isoformat()[:7]]
                if cands:
                    py = cands[0][1]
                    if py:
                        yoy = f"{(v - py) / py * 100:+.2f}"
            except Exception:
                pass
            rows.append({
                "series_alias": alias,
                "series_id": sid,
                "date": d,
                "value": f"{v:.4f}",
                "yoy_pct": yoy,
                "mom_pct": mom,
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["series_alias", "series_id", "date", "value",
                        "yoy_pct", "mom_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    # Latest value for each series (summary)
    by_alias: dict[str, dict] = {}
    for r in rows:
        if r["series_alias"] not in by_alias or r["date"] > by_alias[r["series_alias"]]["date"]:
            by_alias[r["series_alias"]] = r
    print(f"macro_bundle: {len(SERIES)} series, {len(rows)} rows | "
          f"10y={by_alias.get('ten_year_yield',{}).get('value','?')} "
          f"NFCI={by_alias.get('nfci',{}).get('value','?')} "
          f"HY={by_alias.get('hy_spread',{}).get('value','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
