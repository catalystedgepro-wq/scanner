#!/usr/bin/env python3
"""build_yield_curve.py — US Treasury yield curve + 2s10s + 3m10y inversion.

Yield curve is Fed + recession tell. 2s10s inversion → recession in 12-18mo
historically. Moves XLF (banks hate inversion), TLT/IEF (duration ETFs),
JPM/BAC/WFC NIM, mortgage REITs AGNC/NLY.

Source: FRED — CURRENT 0.3y, 2y, 5y, 10y, 30y yields + spreads.
Output: yield_curve.csv
Columns: date, y3m, y2y, y5y, y10y, y30y, spread_2s10s, spread_3m10y, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "yield_curve.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("y3m", "DGS3MO"),
    ("y2y", "DGS2"),
    ("y5y", "DGS5"),
    ("y10y", "DGS10"),
    ("y30y", "DGS30"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"yield {sid}: {e}")
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
    return out[-90:]  # last ~3 months of daily obs


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:90]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        y2y = data["y2y"].get(d, 0)
        y10y = data["y10y"].get(d, 0)
        y3m = data["y3m"].get(d, 0)
        rows.append({
            "date": d,
            "y3m": f"{y3m:.2f}",
            "y2y": f"{y2y:.2f}",
            "y5y": f"{data['y5y'].get(d, 0):.2f}",
            "y10y": f"{y10y:.2f}",
            "y30y": f"{data['y30y'].get(d, 0):.2f}",
            "spread_2s10s": f"{(y10y - y2y):.2f}" if y2y and y10y else "",
            "spread_3m10y": f"{(y10y - y3m):.2f}" if y3m and y10y else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "y3m", "y2y", "y5y", "y10y", "y30y",
                "spread_2s10s", "spread_3m10y", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"yield_curve: {len(rows)} days | latest {latest.get('date','?')} "
          f"10y={latest.get('y10y','?')} 2s10s={latest.get('spread_2s10s','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
