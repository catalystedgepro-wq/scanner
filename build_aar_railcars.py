#!/usr/bin/env python3
"""build_aar_railcars.py — AAR weekly rail carloadings (US/Canada/Mexico).

Association of American Railroads publishes weekly carloads by commodity.
Signal: coal, grain, chemicals, intermodal volume → UNP, CSX, NSC, CP, CNI
(railroads), plus downstream: coal (AMR, BTU, HCC), grain (ADM, BG),
chem (DOW, LYB), intermodal = consumer demand proxy.

Source: FRED weekly rail series (subset of AAR data).
  - RAILFRTINTERMODAL (total intermodal)
  - RAILFRTCARLOADSD11 (total carloads)

Output: aar_railcars.csv
Columns: week_end, metric, value, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "aar_railcars.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("intermodal", "RAILFRTINTERMODAL"),
    ("carloads", "RAILFRTCARLOADSD11"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"aar {sid}: {e}")
        return []
    out: list[tuple[str, float]] = []
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
    return out[-104:]  # last 2 years


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for alias, sid in SERIES:
        for d, v in fetch(sid):
            rows.append({
                "week_end": d,
                "metric": alias,
                "value": f"{v:.0f}",
                "captured_at": now,
            })
    rows.sort(key=lambda r: (r["week_end"], r["metric"]), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["week_end", "metric", "value", "captured_at"])
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"aar_railcars: {len(rows)} obs | latest {latest.get('week_end','?')} "
          f"{latest.get('metric','?')}={latest.get('value','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
