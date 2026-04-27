#!/usr/bin/env python3
"""build_aar_railroad.py — AAR weekly railroad carloads + intermodal.

Weekly AAR Rail Time Indicators = physical economy pulse. Falling
carloads → recession signal. Intermodal weakness → consumer import
slowdown. Specific lanes flag sectors: coal carloads → XLU/utilities,
motor vehicles → GM/F/STLA, grain → agriculture complex (DE, AGCO,
MOS, CF). UNP, CSX, NSC, CP, CNI all react to AAR prints.

Source: FRED RAILTC (total carloads), RAILFRTCARLOADSD11 (intermodal).
Output: aar_railroad.csv
Columns: date, total_carloads, intermodal_units, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "aar_railroad.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("total_carloads", "RAILFRTCARLOADSD11"),
    ("intermodal_units", "RAILFRTINTERMODAL"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"aar {sid}: {e}")
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
    data = {k: dict(fetch(s)) for k, s in SERIES}
    dates = sorted(data["total_carloads"].keys(), reverse=True)[:104]
    rows = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    sorted_dates = sorted(data["total_carloads"].keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    for d in dates:
        tot = data["total_carloads"].get(d, 0)
        inter = data["intermodal_units"].get(d, 0)
        i = idx.get(d, -1)
        yoy = ""
        if i >= 52:
            prev = data["total_carloads"].get(sorted_dates[i - 52], 0)
            if prev:
                yoy = f"{(tot - prev) / prev * 100:+.2f}"
        rows.append({
            "date": d,
            "total_carloads": f"{tot:.0f}",
            "intermodal_units": f"{inter:.0f}" if inter else "",
            "yoy_pct": yoy,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "total_carloads", "intermodal_units",
                        "yoy_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"aar: {len(rows)} weeks | latest "
          f"{latest.get('date','?')} loads={latest.get('total_carloads','?')} "
          f"yoy={latest.get('yoy_pct','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
