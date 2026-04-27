#!/usr/bin/env python3
"""build_ppi_components.py — PPI final demand + commodities (monthly).

PPI leads CPI by 1-2 months. Input inflation (steel, resin, corrugated)
drives margin compression for BUD, PEP, KO, PG, CL, CLX, KHC, SJM. Auto
parts inflation → F, GM, STLA capex lines.

Source: FRED. PPIACO (all comm), PPIFIS (final demand services),
PPITM (industrial commodities), PPICRM (crude materials).

Output: ppi_components.csv
Columns: month, ppi_all, ppi_final_svc, ppi_industrial, ppi_crude,
         ppi_all_yoy, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ppi_components.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("ppi_all", "PPIACO"),
    ("ppi_final_svc", "PPIFIS"),
    ("ppi_industrial", "PPIITM"),
    ("ppi_crude", "PPICRM"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"ppi {sid}: {e}")
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
    data = {a: dict(fetch(s)) for a, s in SERIES}
    ppi_sorted = sorted(data["ppi_all"].keys())
    idx = {d: i for i, d in enumerate(ppi_sorted)}
    dates = sorted(data["ppi_all"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["ppi_all"].get(d, 0)
        i = idx.get(d, -1)
        yoy = data["ppi_all"].get(ppi_sorted[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "ppi_all": f"{cur:.2f}",
            "ppi_final_svc": f"{data['ppi_final_svc'].get(d, 0):.2f}",
            "ppi_industrial": f"{data['ppi_industrial'].get(d, 0):.2f}",
            "ppi_crude": f"{data['ppi_crude'].get(d, 0):.2f}",
            "ppi_all_yoy": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "ppi_all", "ppi_final_svc",
                "ppi_industrial", "ppi_crude", "ppi_all_yoy", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"ppi_components: {len(rows)} months | latest {latest.get('month','?')} "
          f"ppi={latest.get('ppi_all','?')} yoy={latest.get('ppi_all_yoy','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
