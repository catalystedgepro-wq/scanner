#!/usr/bin/env python3
"""build_boe_rates.py — Bank of England Bank Rate + SONIA + gilt yield.

The BoE Bank Rate is the UK policy-rate anchor; divergence vs Fed
drives GBPUSD and UK gilt vs UST carry.

Series (CSVF=TN exports, single series each — multi-series URL 403s):
- IUDBEDR: Bank Rate (policy rate)
- IUDSOIA: SONIA (sterling overnight index average)
- IUDMNPY: 10-year gilt redemption yield (spot)

Readthrough: LSE-listed US-listed dual plays, GBPUSD, UK banks
(BCS, LYG, NWG ADRs), UK REITs, gilt-tracking ETFs (BWX).

Source: bankofengland.co.uk iadb CSV export
Output: boe_rates.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "boe_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://www.bankofengland.co.uk/boeapps/iadb/"
        "fromshowcolumns.asp?csv.x=yes&SeriesCodes={code}"
        "&UsingCodes=Y&VPD=Y&CSVF=TN&Datefrom={frm}")

SERIES = {
    "IUDBEDR": "bank_rate",
    "IUDSOIA": "sonia",
    "IUDMNPY": "gilt_10y",
}


def _get(code: str, frm: str) -> list[tuple[str, float]]:
    url = BASE.format(code=code, frm=frm)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"boe_rates: {code}: {e}")
        return []
    if not text.startswith("DATE,"):
        return []
    out: list[tuple[str, float]] = []
    for line in text.strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            d = dt.datetime.strptime(parts[0].strip(),
                                     "%d %b %Y").date()
            v = float(parts[1].strip())
        except Exception:
            continue
        out.append((d.isoformat(), v))
    return out


def main() -> None:
    frm = (dt.date.today() -
           dt.timedelta(days=180)).strftime("%d/%b/%Y")
    per_series: dict[str, dict[str, float]] = {}
    for code, key in SERIES.items():
        per_series[key] = dict(_get(code, frm))

    all_dates = sorted({d for s in per_series.values() for d in s},
                       reverse=True)
    if not all_dates:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"boe_rates: no fetch, keeping {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for d in all_dates:
        rows.append({
            "date": d,
            "bank_rate": (f"{per_series['bank_rate'][d]:.4f}"
                          if d in per_series["bank_rate"] else ""),
            "sonia": (f"{per_series['sonia'][d]:.4f}"
                      if d in per_series["sonia"] else ""),
            "gilt_10y": (f"{per_series['gilt_10y'][d]:.4f}"
                         if d in per_series["gilt_10y"] else ""),
            "captured_at": now_iso,
        })

    fieldnames = ["date", "bank_rate", "sonia", "gilt_10y",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = next((r for r in rows if r["bank_rate"]), rows[0])
    print(f"boe_rates: {len(rows)} rows | latest={latest['date']} "
          f"bank={latest['bank_rate']} sonia={latest['sonia']} "
          f"gilt10y={latest['gilt_10y']} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
