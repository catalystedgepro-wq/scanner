#!/usr/bin/env python3
"""build_eia_natgas.py — Weekly EIA nat-gas storage (Thu 10:30am ET).

Storage surprise drives 2–8% moves on UNG, nat-gas producers (EQT, AR,
CHK, RRC, SWN, CTRA, CNX) and gas-heavy utilities (NI, CNP, UGI, SR).
Beat expectations → bullish UNG, miss → bullish nat-gas.

Source: EIA API v2 (api.eia.gov). Requires EIA_API_KEY — degrades to
DEMO_KEY with rate limits.

Output: eia_natgas.csv
Columns: date, total_bcf, delta_wk_bcf, delta_yr_bcf, delta_5y_avg_bcf, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eia_natgas.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KEY = os.environ.get("EIA_API_KEY", "DEMO_KEY")

# NG.NW2_EPG0_SWO_R48_BCF.W = Working gas in underground storage, Lower 48, weekly
SERIES = [
    ("total", "NG.NW2_EPG0_SWO_R48_BCF.W"),
    ("east",  "NG.NW2_EPG0_SWO_R31_BCF.W"),
    ("midw",  "NG.NW2_EPG0_SWO_R32_BCF.W"),
    ("mtn",   "NG.NW2_EPG0_SWO_R33_BCF.W"),
    ("pac",   "NG.NW2_EPG0_SWO_R34_BCF.W"),
    ("scen",  "NG.NW2_EPG0_SWO_R35_BCF.W"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = (f"https://api.eia.gov/v2/seriesid/{sid}"
           f"?api_key={KEY}&length=260")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"eia_natgas {sid[-20:]}: {e}")
        return []
    out: list[tuple[str, float]] = []
    for rec in (data.get("response") or {}).get("data") or []:
        pr = str(rec.get("period") or "")
        v = rec.get("value")
        if pr and v is not None:
            try:
                out.append((pr, float(v)))
            except Exception:
                continue
    out.sort(key=lambda t: t[0])
    return out


def main() -> None:
    total = fetch(SERIES[0][1])
    if not total:
        print("eia_natgas: no data")
        OUT_CSV.write_text("date,total_bcf,delta_wk_bcf,delta_yr_bcf,delta_5y_avg_bcf,captured_at\n")
        return
    # Build 5-yr avg per week-of-year
    by_week: dict[int, list[float]] = {}
    for d, v in total:
        try:
            y, m, day = d.split("-")
            woy = dt.date(int(y), int(m), int(day)).isocalendar()[1]
        except Exception:
            continue
        by_week.setdefault(woy, []).append(v)
    five_y_avg = {w: sum(vs[-5:]) / len(vs[-5:]) for w, vs in by_week.items() if vs}

    rows: list[dict] = []
    for i in range(len(total) - 1, -1, -1):
        d, v = total[i]
        prev = total[i - 1][1] if i - 1 >= 0 else v
        # 52w ago
        yr = total[i - 52][1] if i - 52 >= 0 else v
        try:
            y, m, day = d.split("-")
            woy = dt.date(int(y), int(m), int(day)).isocalendar()[1]
        except Exception:
            woy = 0
        avg5 = five_y_avg.get(woy, v)
        rows.append({
            "date": d,
            "total_bcf": f"{v:.0f}",
            "delta_wk_bcf": f"{v - prev:+.0f}",
            "delta_yr_bcf": f"{v - yr:+.0f}",
            "delta_5y_avg_bcf": f"{v - avg5:+.0f}",
        })
        if len(rows) >= 52:
            break
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "total_bcf", "delta_wk_bcf", "delta_yr_bcf",
                "delta_5y_avg_bcf", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"eia_natgas: {len(rows)} weeks | latest {latest.get('date','?')} "
          f"total={latest.get('total_bcf','?')}bcf Δ{latest.get('delta_wk_bcf','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
