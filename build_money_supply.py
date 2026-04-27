#!/usr/bin/env python3
"""build_money_supply.py — M1/M2 money supply (weekly + monthly).

Money supply growth = liquidity gauge. M2 contraction in 2022-2023
preceded bank stress (SIVB, SBNY, FRC). Expansion = risk-on fuel,
speculative caps, crypto rally (COIN, MSTR, MARA, RIOT).

Source: FRED M1SL, M2SL, WM2NS (weekly).
Output: money_supply.csv
Columns: period, m1_b, m2_b, m2w_b, m2_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "money_supply.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("m1", "M1SL"),
    ("m2", "M2SL"),
    ("m2w", "WM2NS"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"money {sid}: {e}")
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
    return out[-96:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    m2_sorted = sorted(data["m2"].keys())
    idx = {d: i for i, d in enumerate(m2_sorted)}
    dates = sorted(data["m2"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["m2"].get(d, 0)
        i = idx.get(d, -1)
        yoy = data["m2"].get(m2_sorted[i - 12], 0) if i >= 12 else 0
        rows.append({
            "period": d,
            "m1_b": f"{data['m1'].get(d, 0):.0f}",
            "m2_b": f"{cur:.0f}",
            "m2w_b": f"{data['m2w'].get(d, 0):.0f}",
            "m2_yoy_pct": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "period", "m1_b", "m2_b", "m2w_b", "m2_yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"money: {len(rows)} months | latest {latest.get('period','?')} "
          f"m2=${latest.get('m2_b','?')}B yoy={latest.get('m2_yoy_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
