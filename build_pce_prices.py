#!/usr/bin/env python3
"""build_pce_prices.py — Fed's preferred PCE deflator (monthly).

PCE (Personal Consumption Expenditures) deflator is the Fed's official
2% target. Core PCE YoY = single most important print. Moves rates
futures, SPX entire, XLRE, XLF. Gold miners (GDX, NEM) rally on PCE >
expected.

Source: FRED PCEPI (headline), PCEPILFE (core).
Output: pce_prices.csv
Columns: month, pce_index, core_pce_index, pce_yoy_pct, core_pce_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "pce_prices.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"pce {sid}: {e}")
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
    return out[-48:]


def main() -> None:
    pce = dict(fetch("PCEPI"))
    core = dict(fetch("PCEPILFE"))
    pce_sorted = sorted(pce.keys())
    idx = {d: i for i, d in enumerate(pce_sorted)}
    dates = sorted(pce.keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        p = pce.get(d, 0)
        c = core.get(d, 0)
        i = idx.get(d, -1)
        p_yoy = pce.get(pce_sorted[i - 12], 0) if i >= 12 else 0
        c_yoy = core.get(pce_sorted[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "pce_index": f"{p:.3f}",
            "core_pce_index": f"{c:.3f}",
            "pce_yoy_pct": f"{((p / p_yoy - 1) * 100):.2f}" if p_yoy else "",
            "core_pce_yoy_pct": f"{((c / c_yoy - 1) * 100):.2f}" if c_yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "pce_index", "core_pce_index",
                "pce_yoy_pct", "core_pce_yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"pce_prices: {len(rows)} months | latest {latest.get('month','?')} "
          f"core_yoy={latest.get('core_pce_yoy_pct','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
