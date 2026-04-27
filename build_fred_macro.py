#!/usr/bin/env python3
"""build_fred_macro.py — FRED macro regime snapshot (Federal Reserve).

FRED is free but requires a key (FRED_API_KEY). Fallback: St Louis Fed
publishes many of these as CSV directly.

Series tracked (market-regime critical):
  - H.4.1 Fed balance sheet (WALCL)
  - H.8 Bank credit (TOTBKCR, TOTLL)
  - Repo operations (RRPONTSYD)
  - 10Y Treasury (DGS10), 2Y (DGS2), spread
  - VIX (VIXCLS), MOVE proxy
  - DXY dollar index (DTWEXBGS)
  - High-yield OAS (BAMLH0A0HYM2)

Output: fred_macro.csv
Columns: series, tag, date, value, prior, change_pct, regime_note
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fred_macro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KEY = os.environ.get("FRED_API_KEY", "")

SERIES = {
    "WALCL": "FED_BALANCE_SHEET",
    "TOTBKCR": "BANK_CREDIT",
    "TOTLL": "LOANS_LEASES",
    "RRPONTSYD": "REVERSE_REPO",
    "DGS10": "TREASURY_10Y",
    "DGS2": "TREASURY_2Y",
    "VIXCLS": "VIX",
    "DTWEXBGS": "DOLLAR_INDEX",
    "BAMLH0A0HYM2": "HY_OAS",
    "T10Y2Y": "YIELD_CURVE",
    "SP500": "SPX",
    "FEDFUNDS": "FED_FUNDS",
}

FRED = "https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={key}&file_type=json&sort_order=desc&limit=30"
# Fallback CSV (no key needed)
CSV_FB = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def fetch_json(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"fred(json): {e}")
        return None


def fetch_csv(sid: str, timeout: int = 20) -> list | None:
    req = urllib.request.Request(CSV_FB.format(sid=sid), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"fred(csv): {sid}: {e}")
        return None
    obs = []
    for ln in txt.splitlines()[1:]:
        parts = ln.split(",")
        if len(parts) < 2 or parts[1] in (".", ""):
            continue
        try:
            obs.append({"date": parts[0], "value": float(parts[1])})
        except Exception:
            continue
    return obs


def main():
    rows = []
    for sid, tag in SERIES.items():
        latest = prior = None
        latest_date = ""
        if KEY:
            data = fetch_json(FRED.format(sid=sid, key=KEY))
            if data and data.get("observations"):
                obs = data["observations"]
                for o in obs:
                    if o.get("value") in (".", None, ""):
                        continue
                    if latest is None:
                        try:
                            latest = float(o["value"])
                            latest_date = o["date"]
                        except Exception:
                            pass
                    elif prior is None:
                        try:
                            prior = float(o["value"])
                        except Exception:
                            pass
                        break
        if latest is None:
            obs = fetch_csv(sid) or []
            if obs:
                latest = obs[-1]["value"]
                latest_date = obs[-1]["date"]
                prior = obs[-2]["value"] if len(obs) > 1 else latest
        if latest is None:
            continue
        change_pct = ((latest - (prior or latest)) / prior * 100) if prior else 0
        note = ""
        if tag == "YIELD_CURVE" and latest < 0:
            note = "INVERTED"
        if tag == "VIX" and latest > 25:
            note = "ELEVATED"
        if tag == "HY_OAS" and latest > 5:
            note = "STRESS"
        rows.append({
            "series": sid,
            "tag": tag,
            "date": latest_date,
            "value": f"{latest:.4f}",
            "prior": f"{prior:.4f}" if prior is not None else "",
            "change_pct": f"{change_pct:+.2f}",
            "regime_note": note,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["series", "tag", "date", "value", "prior", "change_pct", "regime_note"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"fred_macro: {len(rows)} series -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
