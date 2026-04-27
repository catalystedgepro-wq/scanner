#!/usr/bin/env python3
"""build_ism_pmi.py — ISM Manufacturing + Services PMI (monthly).

ISM PMI > 50 = expansion, < 50 = contraction. Moves industrials (CAT, DE,
HON, MMM, EMR, ETN), transports (UPS, FDX, UNP, CSX), chemicals (DOW, LYB,
PPG, SHW), semis (INTC, AMD, TXN) via capex cycle.

Source: FRED NAPM (Manufacturing) + NAPMNOI (Services/Non-Manufacturing).
Output: ism_pmi.csv
Columns: month, manu_pmi, services_pmi, manu_new_orders, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ism_pmi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("manu_pmi", "NAPM"),
    ("services_pmi", "NAPMSDI"),  # non-manu composite
    ("manu_new_orders", "NAPMNOI"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"ism {sid}: {e}")
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
    return out[-24:]


def main() -> None:
    data: dict[str, dict[str, float]] = {a: dict(fetch(s)) for a, s in SERIES}
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:24]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "month": d,
            "manu_pmi": f"{data['manu_pmi'].get(d, 0):.1f}",
            "services_pmi": f"{data['services_pmi'].get(d, 0):.1f}",
            "manu_new_orders": f"{data['manu_new_orders'].get(d, 0):.1f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "manu_pmi", "services_pmi",
                "manu_new_orders", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"ism_pmi: {len(rows)} months | latest {latest.get('month','?')} "
          f"manu={latest.get('manu_pmi','?')} svc={latest.get('services_pmi','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
