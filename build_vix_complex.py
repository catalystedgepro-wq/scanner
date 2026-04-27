#!/usr/bin/env python3
"""build_vix_complex.py — CBOE VIX family + SKEW.

Volatility regime detection. VIX > 30 = panic (long vol ETFs VXX UVXY
SVXY). VIX9D/VIX ratio inversion > 1.0 flags near-term stress that
Bloomberg's VIX card doesn't show. SKEW > 150 = tail-risk hedging
active (institutions buying OTM puts = stress signal).

Symbols affected:
- VIX spike: SPY SQQQ DIA UVXY long-vol; short SPY calls
- VXN spike: QQQ tech selloff risk
- SKEW > 150: hedge fund + pension fund protection bid

Source: FRED fredgraph.csv (CBOE partnership data, daily, free).
Output: vix_complex.csv
Columns: date, vix, vxn, vxd, vix9d, vix3mo, skew, term_inversion
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "vix_complex.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = {
    "vix": "VIXCLS",
    "vxn": "VXNCLS",
    "vxd": "VXDCLS",
    "vix9d": "VIX9DCLS",
    "vix3mo": "VXVCLS",
    "skew": "SKEW",
}


def fetch(sid: str) -> dict[str, float]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    out: dict[str, float] = {}
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"vix {sid}: {e}")
        return out
    for line in body.splitlines()[1:]:
        if "," not in line:
            continue
        date, val = line.split(",", 1)
        val = val.strip()
        if val in (".", "", "NaN"):
            continue
        try:
            out[date] = float(val)
        except ValueError:
            continue
    return out


def main() -> None:
    data = {name: fetch(sid) for name, sid in SERIES.items()}
    all_dates = set()
    for series in data.values():
        all_dates.update(series.keys())
    sorted_dates = sorted(all_dates, reverse=True)[:200]

    rows: list[dict] = []
    for date in sorted_dates:
        vix = data["vix"].get(date)
        v9 = data["vix9d"].get(date)
        term_inv = ""
        if vix and v9 and vix > 0:
            ratio = v9 / vix
            if ratio > 1.0:
                term_inv = f"INVERTED+{((ratio - 1) * 100):.1f}pct"
            elif ratio > 0.95:
                term_inv = "NEAR_INVERSION"
            else:
                term_inv = "NORMAL"
        rows.append({
            "date": date,
            "vix": data["vix"].get(date, ""),
            "vxn": data["vxn"].get(date, ""),
            "vxd": data["vxd"].get(date, ""),
            "vix9d": data["vix9d"].get(date, ""),
            "vix3mo": data["vix3mo"].get(date, ""),
            "skew": data["skew"].get(date, ""),
            "term_inversion": term_inv,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "vix", "vxn", "vxd", "vix9d",
                        "vix3mo", "skew", "term_inversion"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"vix_complex: {len(rows)} days | latest "
          f"{latest.get('date','?')} VIX={latest.get('vix','?')} "
          f"SKEW={latest.get('skew','?')} term={latest.get('term_inversion','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
