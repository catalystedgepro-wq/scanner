#!/usr/bin/env python3
"""build_aaa_gas_prices.py — US retail gasoline + diesel (weekly).

Pump prices = consumer psych gauge + margin proxy for refiners (VLO,
PSX, MPC, DINO). Sustained >$4 gas = XLY drag, COST/TGT/WMT budget
squeeze, rideshare (UBER, LYFT) margin pressure. Rising diesel =
trucker/ag cost input (ODFL, XPO, JBHT, KNX, DE).

Source: FRED GASREGW (regular), GASDESW (diesel).
Output: aaa_gas_prices.csv
Columns: week, gas_reg, gas_diesel, gas_mom, gas_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "aaa_gas_prices.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"gas {sid}: {e}")
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
    return out[-120:]


def main() -> None:
    gas = dict(fetch("GASREGW"))
    diesel = dict(fetch("GASDESW"))
    sorted_dates = sorted(gas.keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(gas.keys(), reverse=True)[:104]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = gas.get(d, 0)
        i = idx.get(d, -1)
        prev = gas.get(sorted_dates[i - 4], 0) if i >= 4 else 0
        yoy = gas.get(sorted_dates[i - 52], 0) if i >= 52 else 0
        rows.append({
            "week": d,
            "gas_reg": f"{cur:.3f}",
            "gas_diesel": f"{diesel.get(d, 0):.3f}",
            "gas_mom": f"{((cur / prev - 1) * 100):.2f}" if prev else "",
            "gas_yoy_pct": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week", "gas_reg", "gas_diesel",
                "gas_mom", "gas_yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"aaa_gas: {len(rows)} weeks | latest {latest.get('week','?')} "
          f"reg=${latest.get('gas_reg','?')} diesel=${latest.get('gas_diesel','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
