#!/usr/bin/env python3
"""build_eia_nat_gas.py — Weekly natural gas storage + hub prices.

EIA weekly storage (Thursday 10:30a ET) = highest-volatility gas
print. Draws > consensus → UNG surges, EQT/AR/SWN rally. Builds >
consensus → selloff. Cold snap forecast → LNG/CQP/TELL export hubs
benefit, NYSE utility names (XEL, WEC, ETR, DUK) pressure.

Source: FRED NATURALGAS (Henry Hub), DHHNGSP (daily spot),
WNGSL (weekly storage).
Output: eia_nat_gas.csv
Columns: date, henry_hub_spot, weekly_storage_bcf, storage_change_bcf,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eia_nat_gas.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("spot", "DHHNGSP"),
    ("storage", "NGM_EPG0_SWO_R48_BCF"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"nat_gas {sid}: {e}")
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
    return out[-180:]


def fetch_eia_storage() -> dict[str, float]:
    """EIA weekly working gas in storage (lower 48). Free, no key needed
    for series NW2_EPG0_SWO_R48_BCF via EIA v2 short URL."""
    import os
    key = os.environ.get("EIA_API_KEY", "")
    if not key:
        return {}
    url = (
        "https://api.eia.gov/v2/natural-gas/stor/wkly/data/"
        f"?api_key={key}&frequency=weekly&data[0]=value"
        "&facets[series][]=NW2_EPG0_SWO_R48_BCF&sort[0][column]=period"
        "&sort[0][direction]=desc&length=120"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"eia_storage: {e}")
        return {}
    out: dict[str, float] = {}
    for row in (data.get("response") or {}).get("data", []) or []:
        try:
            out[row.get("period", "")] = float(row.get("value") or 0)
        except Exception:
            pass
    return out


def main() -> None:
    import json as _json  # noqa: F401
    spot = dict(fetch("DHHNGSP"))
    storage = fetch_eia_storage()
    sorted_st = sorted(storage.keys())
    idx = {d: i for i, d in enumerate(sorted_st)}
    dates = sorted(spot.keys(), reverse=True)[:120]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        st = storage.get(d, 0)
        i = idx.get(d, -1)
        prev = storage.get(sorted_st[i - 1], 0) if i >= 1 else 0
        rows.append({
            "date": d,
            "henry_hub_spot": f"{spot.get(d, 0):.3f}",
            "weekly_storage_bcf": f"{st:.0f}" if st else "",
            "storage_change_bcf": f"{(st - prev):+.0f}" if st and prev else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "henry_hub_spot", "weekly_storage_bcf",
                "storage_change_bcf", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"eia_gas: {len(rows)} days | latest {latest.get('date','?')} "
          f"spot=${latest.get('henry_hub_spot','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
