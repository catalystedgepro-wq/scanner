#!/usr/bin/env python3
"""build_bea_trade.py — US goods & services trade balance.

Monthly BEA release. Widening deficit → USD pressure (DXY down),
exporters (KO, PG, MMM, CAT) benefit. Narrowing → USD strength,
S&P500 margin headwinds for multinationals. Breakdown by country
flags tariff-sensitive names (AAPL China, NKE Vietnam, WMT imports).

Source: FRED BOPGSTB (goods+svcs), EXPGS, IMPGS.
Output: bea_trade.csv
Columns: date, trade_balance_usd_bn, exports_usd_bn,
         imports_usd_bn, balance_change, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bea_trade.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("trade_balance", "BOPGSTB"),
    ("exports", "EXPGS"),
    ("imports", "IMPGS"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"bea {sid}: {e}")
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
    data = {k: dict(fetch(s)) for k, s in SERIES}
    dates = sorted(data["trade_balance"].keys(), reverse=True)[:36]
    rows = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    prev_tb = None
    for d in dates:
        tb = data["trade_balance"].get(d, 0) / 1000  # to $bn
        ex = data["exports"].get(d, 0) / 1000
        im = data["imports"].get(d, 0) / 1000
        change = f"{(tb - prev_tb):+.1f}" if prev_tb is not None else ""
        prev_tb = tb
        rows.append({
            "date": d,
            "trade_balance_usd_bn": f"{tb:+.1f}",
            "exports_usd_bn": f"{ex:.1f}",
            "imports_usd_bn": f"{im:.1f}",
            "balance_change": change,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "trade_balance_usd_bn", "exports_usd_bn",
                        "imports_usd_bn", "balance_change", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"bea_trade: {len(rows)} months | latest "
          f"{latest.get('date','?')} balance={latest.get('trade_balance_usd_bn','?')}bn "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
