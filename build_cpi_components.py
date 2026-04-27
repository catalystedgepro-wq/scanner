#!/usr/bin/env python3
"""build_cpi_components.py — CPI monthly components (shelter, used cars, food).

Fed watches shelter CPI (40% of core). Used-car CPI drives CVNA, KMX, AN
margins. Food at home drives WMT, KR, SFM grocery margins. Energy CPI →
XOM/CVX sentiment pathway. Medical care CPI → UNH, CVS, HUM, ELV premium
pricing.

Source: FRED. Output: cpi_components.csv
Columns: month, cpi_all, cpi_core, cpi_shelter, cpi_used_cars, cpi_food,
         cpi_energy, cpi_medical, cpi_all_yoy, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cpi_components.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("cpi_all", "CPIAUCSL"),
    ("cpi_core", "CPILFESL"),
    ("cpi_shelter", "CUSR0000SAH1"),
    ("cpi_used_cars", "CUSR0000SETA02"),
    ("cpi_food", "CPIUFDSL"),
    ("cpi_energy", "CPIENGSL"),
    ("cpi_medical", "CPIMEDSL"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"cpi {sid}: {e}")
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
    cpi_sorted = sorted(data["cpi_all"].keys())
    idx = {d: i for i, d in enumerate(cpi_sorted)}
    dates = sorted(data["cpi_all"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        all_cpi = data["cpi_all"].get(d, 0)
        i = idx.get(d, -1)
        yoy_base = data["cpi_all"].get(cpi_sorted[i - 12], 0) if i >= 12 else 0
        yoy = f"{((all_cpi / yoy_base - 1) * 100):.2f}" if yoy_base else ""
        rows.append({
            "month": d,
            "cpi_all": f"{all_cpi:.2f}",
            "cpi_core": f"{data['cpi_core'].get(d, 0):.2f}",
            "cpi_shelter": f"{data['cpi_shelter'].get(d, 0):.2f}",
            "cpi_used_cars": f"{data['cpi_used_cars'].get(d, 0):.2f}",
            "cpi_food": f"{data['cpi_food'].get(d, 0):.2f}",
            "cpi_energy": f"{data['cpi_energy'].get(d, 0):.2f}",
            "cpi_medical": f"{data['cpi_medical'].get(d, 0):.2f}",
            "cpi_all_yoy": yoy,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "cpi_all", "cpi_core", "cpi_shelter",
                "cpi_used_cars", "cpi_food", "cpi_energy",
                "cpi_medical", "cpi_all_yoy", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"cpi_components: {len(rows)} months | latest {latest.get('month','?')} "
          f"all={latest.get('cpi_all','?')} yoy={latest.get('cpi_all_yoy','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
