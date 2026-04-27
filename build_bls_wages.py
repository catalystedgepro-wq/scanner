#!/usr/bin/env python3
"""build_bls_wages.py — BLS average hourly earnings + weekly hours.

Wage growth persistence = Fed's biggest inflation worry. AHE YoY >4% =
sticky inflation. Moves XLRE (rents), XLY (consumer budget), XLV
(healthcare labor), XLF (bank NIM).

Source: FRED CES0500000003 (AHE, all private), AWHAETP (weekly hours).
Output: bls_wages.csv
Columns: month, ahe_usd, weekly_hours, ahe_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bls_wages.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("ahe", "CES0500000003"),
    ("weekly_hours", "AWHAETP"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"bls {sid}: {e}")
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
    ahe_sorted = sorted(data["ahe"].keys())
    idx = {d: i for i, d in enumerate(ahe_sorted)}
    dates = sorted(data["ahe"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["ahe"].get(d, 0)
        i = idx.get(d, -1)
        yoy = data["ahe"].get(ahe_sorted[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "ahe_usd": f"{cur:.2f}",
            "weekly_hours": f"{data['weekly_hours'].get(d, 0):.1f}",
            "ahe_yoy_pct": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "ahe_usd", "weekly_hours", "ahe_yoy_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"bls_wages: {len(rows)} months | latest {latest.get('month','?')} "
          f"ahe=${latest.get('ahe_usd','?')} yoy={latest.get('ahe_yoy_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
