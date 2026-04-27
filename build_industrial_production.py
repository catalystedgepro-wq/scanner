#!/usr/bin/env python3
"""build_industrial_production.py — Fed Industrial Production + Capacity Utilization.

Industrial Production = manufacturing/mining/utilities output. Capacity
utilization > 82% → CAPEX cycle up (ETN, EMR, ROK, PH, CMI capital spend);
< 78% → contraction. Moves XLI (industrials), freight (UNP, FDX), semis
(AMAT, LRCX fab utilization proxy).

Source: FRED. INDPRO (IP), TCU (cap util).
Output: industrial_production.csv
Columns: month, ip_index, cap_util_pct, mom_pct, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "industrial_production.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [("ip", "INDPRO"), ("cap_util", "TCU")]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"ip {sid}: {e}")
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
    ip_sorted = sorted(data["ip"].keys())
    idx = {d: i for i, d in enumerate(ip_sorted)}
    dates = sorted(data["ip"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["ip"].get(d, 0)
        i = idx.get(d, -1)
        mom = data["ip"].get(ip_sorted[i - 1], 0) if i >= 1 else 0
        yoy = data["ip"].get(ip_sorted[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "ip_index": f"{cur:.2f}",
            "cap_util_pct": f"{data['cap_util'].get(d, 0):.2f}",
            "mom_pct": f"{((cur / mom - 1) * 100):.2f}" if mom else "",
            "yoy_pct": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "ip_index", "cap_util_pct", "mom_pct", "yoy_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"industrial_production: {len(rows)} months | latest {latest.get('month','?')} "
          f"ip={latest.get('ip_index','?')} cap_util={latest.get('cap_util_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
