#!/usr/bin/env python3
"""build_retail_sales.py — Census monthly retail sales (RSAFS + control groups).

Retail sales = consumer health proxy. Control group (ex auto/gas/food/
building) feeds into GDP personal consumption. Moves XRT, AMZN, WMT, TGT,
COST, HD, LOW, ULTA, TJX, ROST, BBY, BBWI.

Source: FRED series
  - RSAFS: Advance Retail Sales (total, $M)
  - RSXFS: Retail Sales ex Food Services
  - RSCCAS: Control group

Output: retail_sales.csv
Columns: month, total_m, ex_food_m, control_m, mom_pct, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "retail_sales.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("total", "RSAFS"),
    ("ex_food", "RSXFS"),
    ("control", "RSCCAS"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"retail {sid}: {e}")
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
    return out


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    total_sorted = sorted(data["total"].keys())
    idx = {d: i for i, d in enumerate(total_sorted)}
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["total"].get(d, 0)
        i = idx.get(d, -1)
        mom = data["total"].get(total_sorted[i - 1], 0) if i >= 1 else 0
        yoy = data["total"].get(total_sorted[i - 12], 0) if i >= 12 else 0
        mom_p = f"{((cur / mom - 1) * 100):.2f}" if mom else ""
        yoy_p = f"{((cur / yoy - 1) * 100):.2f}" if yoy else ""
        rows.append({
            "month": d,
            "total_m": f"{cur:.0f}",
            "ex_food_m": f"{data['ex_food'].get(d, 0):.0f}",
            "control_m": f"{data['control'].get(d, 0):.0f}",
            "mom_pct": mom_p,
            "yoy_pct": yoy_p,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "total_m", "ex_food_m", "control_m",
                "mom_pct", "yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"retail_sales: {len(rows)} months | latest {latest.get('month','?')} "
          f"total=${latest.get('total_m','?')}M mom={latest.get('mom_pct','?')}% "
          f"yoy={latest.get('yoy_pct','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
