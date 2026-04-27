#!/usr/bin/env python3
"""build_opec_crude.py — OPEC basket + WTI/Brent spread (daily).

OPEC basket vs WTI spread → refiner crack margin proxy (VLO, MPC,
PSX, DINO). Widening Brent-WTI = US crude export arb window open
(EPD, ET, WMB midstream). Contango/backwardation flips move
commodity-linked MLPs.

Source: FRED DCOILWTICO, DCOILBRENTEU. OPEC basket weekly from FRED
POILAPSPUSDM (proxy IMF average petroleum spot index).
Output: opec_crude.csv
Columns: date, wti, brent, brent_wti_spread, opec_basket_avg, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "opec_crude.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("wti", "DCOILWTICO"),
    ("brent", "DCOILBRENTEU"),
    ("opec_basket", "POILAPSPUSDM"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"opec {sid}: {e}")
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
    data = {a: dict(fetch(s)) for a, s in SERIES}
    dates = sorted(data["wti"].keys(), reverse=True)[:120]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        wti = data["wti"].get(d, 0)
        brent = data["brent"].get(d, 0)
        # Match OPEC basket monthly to daily by year-month
        ym = d[:7] + "-01"
        opec = data["opec_basket"].get(ym, 0)
        rows.append({
            "date": d,
            "wti": f"{wti:.2f}",
            "brent": f"{brent:.2f}",
            "brent_wti_spread": f"{(brent - wti):+.2f}" if (wti and brent) else "",
            "opec_basket_avg": f"{opec:.2f}" if opec else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "wti", "brent",
                "brent_wti_spread", "opec_basket_avg", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"opec_crude: {len(rows)} days | latest {latest.get('date','?')} "
          f"spread={latest.get('brent_wti_spread','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
