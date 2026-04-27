#!/usr/bin/env python3
"""build_treasury_mts.py — Monthly Treasury Statement fiscal flows.

Monthly Treasury Statement (MTS) Table 1 shows federal budget
receipts, outlays, and deficit/surplus by calendar month. Captures
the macro fiscal impulse — how much cash is flowing out of the
Treasury vs coming in via taxes — a key driver of risk appetite
and term-premium expectations.

Series tracked (last 24 months):
- current_month_gross_rcpt_amt    federal receipts, $
- current_month_gross_outly_amt   federal outlays, $
- current_month_dfct_sur_amt      deficit (+) or surplus (-), $
  (MTS sign convention: positive = deficit)

Signal for trading:
- Monthly deficit > $300B sustained = net Treasury issuance needs
  tick up; 10y yield repricing risk. Fade TLT, bid XLF (banks
  benefit from steeper curve).
- 3-mo trailing receipts rising > 5% YoY = strong nominal growth;
  bid IWM (cyclicals).
- Interest outlays > 20% of receipts = fiscal dominance risk
  signal; bid GLD/SLV.
- April surplus (tax day) timing: watch TGA build into mid-April
  for Treasury drawdown announcement (RRP cash release tell).

Source: api.fiscaldata.treasury.gov/.../mts/mts_table_1
        (JSON, no key). 24-month window, record_type_cd=MTH.

Output: treasury_mts.csv
Columns: report_date, period_month, receipts_bn, outlays_bn,
         deficit_bn, surplus_flag, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_mts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.fiscaldata.treasury.gov/services/api/"
       "fiscal_service/v1/accounting/mts/mts_table_1"
       "?filter=record_type_cd:eq:MTH"
       "&sort=-record_date"
       "&page[size]=48")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"treasury_mts: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_mts: keeping existing {OUT_CSV.name}")
        return

    raw = d.get("data", []) or []
    rows: list[dict] = []
    for r in raw:
        rd = r.get("record_date") or ""
        month_name = r.get("classification_desc") or ""
        try:
            rcpt = float(r.get("current_month_gross_rcpt_amt") or 0) / 1e9
            outly = float(r.get("current_month_gross_outly_amt") or 0) / 1e9
            defc = float(r.get("current_month_dfct_sur_amt") or 0) / 1e9
        except ValueError:
            continue
        if rcpt == 0 and outly == 0:
            continue
        surplus = "deficit" if defc >= 0 else "surplus"
        rows.append({
            "report_date": rd,
            "period_month": month_name,
            "receipts_bn": f"{rcpt:.2f}",
            "outlays_bn": f"{outly:.2f}",
            "deficit_bn": f"{abs(defc):.2f}",
            "surplus_flag": surplus,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_mts: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort most recent report first.
    rows.sort(key=lambda r: (r["report_date"], r["period_month"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["report_date", "period_month", "receipts_bn",
                  "outlays_bn", "deficit_bn", "surplus_flag",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]
    print(f"treasury_mts: {len(rows)} rows | {latest['period_month']} "
          f"(report {latest['report_date']}) "
          f"rcpt=${latest['receipts_bn']}B "
          f"outly=${latest['outlays_bn']}B "
          f"{latest['surplus_flag']}=${latest['deficit_bn']}B "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
