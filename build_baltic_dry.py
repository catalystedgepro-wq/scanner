#!/usr/bin/env python3
"""build_baltic_dry.py — Baltic Dry Index + shipping proxies (daily).

BDI = global dry-bulk freight cost. Rising BDI = commodity demand up
(copper, iron ore, coal) → FCX, VALE, BHP, RIO. Dry shipping stocks
(SBLK, GOGL, GNK, EGLE, DSX) directly levered. Container rates proxy
for retail inventory restocking (TGT, COST, WMT, AMZN) Q/Q.

Source: stooq.com for ^BDI (free OHLC), FRED for container freight rates.
Output: baltic_dry.csv
Columns: date, bdi, bdi_wow_pct, fsi, containers_ty, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "baltic_dry.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch_stooq(symbol: str) -> list[tuple[str, float]]:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"stooq {symbol}: {e}")
        return []
    out = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        d = parts[0].strip()
        c = parts[4].strip()
        if c in {".", "", "N/D"}:
            continue
        try:
            out.append((d, float(c)))
        except Exception:
            pass
    return out[-180:]


def fetch_fred(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"fred {sid}: {e}")
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


def main() -> None:
    bdi = dict(fetch_stooq("^bdi"))
    fsi = dict(fetch_fred("STLFSI4"))
    # Container freight volume proxy: FRED WPU301 (metal containers PPI)
    # not exact but represents container pricing; use IR14260 if avail
    containers = dict(fetch_fred("WPU30120181"))
    sorted_dates = sorted(bdi.keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(bdi.keys(), reverse=True)[:120]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = bdi.get(d, 0)
        i = idx.get(d, -1)
        wk = bdi.get(sorted_dates[i - 5], 0) if i >= 5 else 0
        rows.append({
            "date": d,
            "bdi": f"{cur:.0f}",
            "bdi_wow_pct": f"{((cur / wk - 1) * 100):.2f}" if wk else "",
            "fsi": f"{fsi.get(d, 0):+.2f}",
            "containers_ty": f"{containers.get(d, 0):.2f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "bdi", "bdi_wow_pct",
                "fsi", "containers_ty", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"bdi: {len(rows)} days | latest {latest.get('date','?')} "
          f"bdi={latest.get('bdi','?')} wow={latest.get('bdi_wow_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
