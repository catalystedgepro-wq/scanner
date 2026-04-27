#!/usr/bin/env python3
"""build_case_shiller.py — S&P Case-Shiller US home price indices.

National + 20-city + top-10 composite. Home prices drive homebuilders
(DHI, LEN, PHM, NVR, TOL, KBH, MTH), home centers (HD, LOW), title/
mortgage REITs (FNF, RKT, UWMC, AGNC), insurance (ALL, TRV, PGR).

Source: FRED series (monthly, 2-month lag).
  - CSUSHPINSA: national
  - SPCS20RSA: 20-city seasonally-adjusted
  - SPCS10RNSA: 10-city
Output: case_shiller.csv
Columns: month, national, twenty_city, ten_city, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "case_shiller.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("national", "CSUSHPINSA"),
    ("twenty_city", "SPCS20RSA"),
    ("ten_city", "SPCS10RNSA"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"case_shiller {sid}: {e}")
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


def yoy(cur: float, prev: float) -> str:
    if not prev:
        return ""
    return f"{((cur / prev - 1) * 100):.2f}"


def main() -> None:
    data: dict[str, dict[str, float]] = {a: dict(fetch(s)) for a, s in SERIES}
    # For YoY we need 12-month-prior same-series lookup
    dates = sorted(data["national"].keys(), reverse=True)[:24]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    all_dates_nat = sorted(data["national"].keys())
    idx_by_date = {d: i for i, d in enumerate(all_dates_nat)}
    for d in dates:
        nat = data["national"].get(d, 0)
        i = idx_by_date.get(d, -1)
        prev = data["national"].get(all_dates_nat[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "national": f"{nat:.2f}",
            "twenty_city": f"{data['twenty_city'].get(d, 0):.2f}",
            "ten_city": f"{data['ten_city'].get(d, 0):.2f}",
            "yoy_pct": yoy(nat, prev),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "national", "twenty_city", "ten_city",
                "yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"case_shiller: {len(rows)} months | latest {latest.get('month','?')} "
          f"nat={latest.get('national','?')} yoy={latest.get('yoy_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
