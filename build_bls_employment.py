#!/usr/bin/env python3
"""build_bls_employment.py — BLS nonfarm payrolls + unemployment.

First-Friday-of-the-month NFP = biggest scheduled macro catalyst.
Hot print → yields up, growth stocks (QQQ, ARKK) pressure, banks
(XLF, JPM, BAC) rally. Cold print → Fed-cut odds jump, small caps
(IWM) rally. Unemployment rate change + labor force participation
give the full picture. Also captures wage growth (AHETPI, CES).

Source: FRED PAYEMS, UNRATE, CES3000000008, LNS11300000, ICSA.
Output: bls_employment.csv
Columns: date, nonfarm_payrolls, unrate, part_rate, avg_hourly_earn,
         jobless_claims, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bls_employment.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("nonfarm_payrolls", "PAYEMS"),
    ("unrate", "UNRATE"),
    ("part_rate", "CIVPART"),
    ("avg_hourly_earn", "CES0500000003"),
    ("jobless_claims", "ICSA"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"bls_emp {sid}: {e}")
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
    return out[-60:]


def main() -> None:
    data = {alias: dict(fetch(sid)) for alias, sid in SERIES}
    # Union of monthly dates (use payrolls as driver series)
    driver = sorted(data["nonfarm_payrolls"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in driver:
        row = {"date": d, "captured_at": now}
        for alias, _ in SERIES:
            v = data[alias].get(d)
            if v is None:
                # nearest available (for weekly claims / earnings)
                near = [(k, v2) for k, v2 in data[alias].items() if k <= d]
                v = near[-1][1] if near else 0
            row[alias] = f"{v:.2f}" if v else ""
        rows.append(row)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "nonfarm_payrolls", "unrate",
                        "part_rate", "avg_hourly_earn",
                        "jobless_claims", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"bls_emp: {len(rows)} months | latest "
          f"{latest.get('date','?')} nfp={latest.get('nonfarm_payrolls','?')} "
          f"unrate={latest.get('unrate','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
