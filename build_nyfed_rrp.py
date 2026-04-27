#!/usr/bin/env python3
"""build_nyfed_rrp.py — NY Fed overnight reverse-repo (RRP) facility.

Daily overnight RRP facility usage — the cash MMFs and GSEs park
at the Fed when bill supply is tight. RRP balance acts as an
inverse bank-reserve indicator. Historically correlates with risk
appetite: big drawdown in RRP = cash flowing back into bills/credit.

Series tracked (last 20 operations):
- Amount Accepted (total $B facility use)
- Number of accepted counterparties
- Award rate (operation floor)

Signal for trading:
- RRP take-up < $50B = cash leaving the facility into bills/credit
  (reflation tailwind). Bid HYG, JNK, IWM on sustained trend.
- RRP take-up > $500B sustained = cash hoarded; fade cyclical risk,
  bid TLT + gold.
- Accepted cpty > 40 at facility floor = broad MMF reliance; watch
  for Fed RRP rate tweak that typically softens BBG US Agg +25bps.
- Award rate gap vs target_mid widens = Fed corridor working as
  designed; no signal. Compression to corridor floor = stress tell.

Source: markets.newyorkfed.org/api/rp/reverserepo (no key).

Output: nyfed_rrp.csv
Columns: operation_date, maturity_date, term_days, offering_rate,
         award_rate, amt_accepted_mm, accepted_cpty, submitted_cpty,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nyfed_rrp.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://markets.newyorkfed.org/api/rp/reverserepo/all/"
       "results/last/30.json")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nyfed_rrp: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nyfed_rrp: keeping existing {OUT_CSV.name}")
        return

    ops = d.get("repo", {}).get("operations", []) or []
    if not ops:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nyfed_rrp: keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for op in ops:
        if op.get("auctionStatus") != "Results":
            continue
        details = op.get("details") or []
        total_accepted = op.get("totalAmtAccepted") or 0
        award_rate = ""
        offering_rate = ""
        if details:
            first = details[0]
            award_rate = first.get("percentAwardRate") or ""
            offering_rate = first.get("percentOfferingRate") or ""
        rows.append({
            "operation_date": op.get("operationDate") or "",
            "maturity_date": op.get("maturityDate") or "",
            "term_days": str(op.get("termCalenderDays") or ""),
            "offering_rate": (f"{float(offering_rate):.4f}"
                              if offering_rate != "" else ""),
            "award_rate": (f"{float(award_rate):.4f}"
                           if award_rate != "" else ""),
            "amt_accepted_mm": str(total_accepted or ""),
            "accepted_cpty": str(op.get("acceptedCpty") or ""),
            "submitted_cpty": str(op.get("participatingCpty") or ""),
        })

    if not rows:
        return

    rows.sort(key=lambda r: r["operation_date"])

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["operation_date", "maturity_date", "term_days",
                  "offering_rate", "award_rate", "amt_accepted_mm",
                  "accepted_cpty", "submitted_cpty", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[-1]
    amt = latest["amt_accepted_mm"]
    # API reports amount in $thousands; divide by 1e6 for $B.
    try:
        amt_bn = float(amt) / 1_000_000.0
    except Exception:
        amt_bn = 0.0
    print(f"nyfed_rrp: {len(rows)} ops | latest {latest['operation_date']}"
          f" ${amt_bn:.1f}B @ {latest['award_rate']}% "
          f"cpty={latest['accepted_cpty']} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
