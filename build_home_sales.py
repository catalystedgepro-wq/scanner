#!/usr/bin/env python3
"""build_home_sales.py — New + existing home sales + inventory.

New home sales (Census) + existing home sales (NAR). Leading indicators
for homebuilders (DHI, LEN, PHM, NVR, TOL, KBH, MTH), home improvement
(HD, LOW), mortgage origination (RKT, UWMC), furniture (ETD, WSM, RH).

Source: FRED HSN1F (new, SAAR thousands), EXHOSLUSM495S (existing, SAAR
millions), HOSSUPUSM673N (inventory months-supply).

Output: home_sales.csv
Columns: month, new_home_sales_k, existing_home_sales_m, months_supply,
         median_new_price, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "home_sales.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("new_home_sales_k", "HSN1F"),
    ("existing_home_sales_m", "EXHOSLUSM495S"),
    ("months_supply", "MSACSR"),
    ("median_new_price", "MSPNHSUS"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"home {sid}: {e}")
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
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "month": d,
            "new_home_sales_k": f"{data['new_home_sales_k'].get(d, 0):.0f}",
            "existing_home_sales_m": f"{data['existing_home_sales_m'].get(d, 0):.2f}",
            "months_supply": f"{data['months_supply'].get(d, 0):.1f}",
            "median_new_price": f"{data['median_new_price'].get(d, 0):.0f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "new_home_sales_k", "existing_home_sales_m",
                "months_supply", "median_new_price", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"home_sales: {len(rows)} months | latest {latest.get('month','?')} "
          f"new={latest.get('new_home_sales_k','?')}k exist={latest.get('existing_home_sales_m','?')}M "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
