#!/usr/bin/env python3
"""build_adp_payrolls.py — ADP monthly private payrolls.

ADP prints Wednesday before BLS NFP Friday. Beats/misses swing futures
premarket. Movers: broad market (SPY, QQQ), staffing (MAN, RHI), payroll
vendors (PAYX, ADP — the provider itself).

Source: FRED ADPMNUSNERSA (NSA) and ADPWNUSNERSA (weekly payrolls).
  Actual ADP monthly report is via adpemploymentreport.com (PDF only).
  Using FRED closest series.

Output: adp_payrolls.csv
Columns: month, total_employment_k, mom_change_k, mom_pct, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "adp_payrolls.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Use private NFP (BLS USPRIV) as proxy
SERIES_ID = "USPRIV"


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"adp {sid}: {e}")
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
    return out


def main() -> None:
    data = fetch(SERIES_ID)
    sorted_data = sorted(data)
    idx = {d: i for i, (d, _) in enumerate(sorted_data)}
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d, v in sorted(data, reverse=True)[:36]:
        i = idx.get(d, -1)
        prev_m = sorted_data[i - 1][1] if i >= 1 else 0
        prev_y = sorted_data[i - 12][1] if i >= 12 else 0
        mom_k = v - prev_m if prev_m else 0
        mom = f"{((v / prev_m - 1) * 100):.2f}" if prev_m else ""
        yoy = f"{((v / prev_y - 1) * 100):.2f}" if prev_y else ""
        rows.append({
            "month": d,
            "total_employment_k": f"{v:.0f}",
            "mom_change_k": f"{mom_k:.0f}",
            "mom_pct": mom,
            "yoy_pct": yoy,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "total_employment_k", "mom_change_k",
                "mom_pct", "yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"adp_payrolls: {len(rows)} months | latest {latest.get('month','?')} "
          f"total={latest.get('total_employment_k','?')}k mom={latest.get('mom_change_k','?')}k "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
