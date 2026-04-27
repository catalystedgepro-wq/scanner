#!/usr/bin/env python3
"""build_trade_balance.py — US trade balance goods + services (monthly).

Trade deficit widens/shrinks → USD pressure, port volumes. Movers: CAT,
DE, BA (exporters), HD/LOW (imported lumber/steel), oil (XOM, CVX), tech
(AAPL 55% non-US, MU memory).

Source: FRED BOPGSTB (goods + services, $B).
Output: trade_balance.csv
Columns: month, balance_b, exports_b, imports_b, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "trade_balance.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("balance_b", "BOPGSTB"),
    ("exports_b", "EXPGS"),
    ("imports_b", "IMPGS"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"trade {sid}: {e}")
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
    return out[-36:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    bal_sorted = sorted(data["balance_b"].keys())
    idx = {d: i for i, d in enumerate(bal_sorted)}
    dates = sorted(data["balance_b"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["balance_b"].get(d, 0)
        i = idx.get(d, -1)
        yoy_base = data["balance_b"].get(bal_sorted[i - 12], 0) if i >= 12 else 0
        yoy = f"{((cur / yoy_base - 1) * 100):.2f}" if yoy_base else ""
        rows.append({
            "month": d,
            "balance_b": f"{cur:.2f}",
            "exports_b": f"{data['exports_b'].get(d, 0):.2f}",
            "imports_b": f"{data['imports_b'].get(d, 0):.2f}",
            "yoy_pct": yoy,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "balance_b", "exports_b", "imports_b",
                "yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"trade_balance: {len(rows)} months | latest {latest.get('month','?')} "
          f"balance=${latest.get('balance_b','?')}B -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
