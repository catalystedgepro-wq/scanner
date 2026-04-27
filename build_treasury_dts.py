#!/usr/bin/env python3
"""build_treasury_dts.py — Daily Treasury Statement flows.

Daily US federal government deposits and withdrawals by agency
category. Publishes next-business-day — much fresher than any
economic data release. Captures:

- Defense spending (Dept of Defense) → LMT, RTX, NOC, GD, BA
  defense unit. Sharp MTD outlay drops or surges telegraph
  contract-award cycles + CR/shutdown risk.
- USDA Commodity Credit Corp payments → ADM, BG, CORN etf. Farm
  subsidy pulses.
- Medicare + Medicaid outlays → UNH, HUM, ELV, CVS, MOH. Pacing
  of CMS payments.
- Student loan collections → SOFI, DFS, SLM recovery signal.
- Customs duties → tariff revenue run-rate; large day-over-day
  deltas confirm tariff-policy execution in near-real-time.
- IRS refund vs receipt flows → consumer-spending proxy Mar-Apr.
- Treasury General Account balance = federal liquidity reserve.
  TGA drawdowns during debt-ceiling standoffs = QE-like;
  rebuilds after resolution drain Fed RRP → risk-asset impact.

Source: api.fiscaldata.treasury.gov/services/api/fiscal_service/v1
  /accounting/dts/operating_cash_balance (no key, daily).
  + deposits_withdrawals_operating_cash for category breakdown.

Output: treasury_dts.csv
Columns: record_date, category, transaction_type, today_usd_mm,
         mtd_usd_mm, fytd_usd_mm, captured_at

Note: values are in millions of dollars ($MM).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_dts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://api.fiscaldata.treasury.gov/services/api/"
        "fiscal_service/v1/accounting/dts")

DEPOSITS_EP = f"{BASE}/deposits_withdrawals_operating_cash"

# Categories we care about most — narrowed to avoid 1k-row noise.
INTEREST_CATEGORIES = {
    "Dept of Defense",
    "Dept of Veterans Affairs",
    "HHS - Medicare",
    "HHS - Medicaid",
    "Social Security Benefits",
    "USDA - Commodity Credit",
    "Customs and Certain Exc",
    "IRS Tax Refunds",
    "Federal Salaries",
    "Treasury Interest",
    "Individual Income Taxes",
    "Corporation Income Taxes",
    "Withheld Income + FICA",
    "IRS Non-Tax Revenue",
    "Unemployment Insurance",
    "Dept of Energy",
    "Dept of Transportation",
    "Dept of Homeland Security",
    "Dept of Agriculture",
    "Dept of State",
    "Education Department",
    "HUD program",
}


def fetch_recent_days(days: int = 7) -> list[dict]:
    """Pull DTS deposits/withdrawals for past N days, all cats."""
    today = dt.date.today()
    start = today - dt.timedelta(days=days + 3)
    qs = urllib.parse.urlencode({
        "sort": "-record_date",
        "filter": f"record_date:gte:{start.isoformat()}",
        "page[size]": "10000",
        "format": "json",
    })
    url = f"{DEPOSITS_EP}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"treasury_dts fetch: {e}")
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data.get("data", []) or []


def _to_float(s) -> float | None:
    if s is None or s == "null" or s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None


def main() -> None:
    records = fetch_recent_days(days=7)

    if not records:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_dts: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Filter to most recent record_date.
    dates = sorted({r.get("record_date", "") for r in records},
                   reverse=True)
    latest = dates[0] if dates else ""
    if not latest:
        return

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rec in records:
        if rec.get("record_date") != latest:
            continue
        catg = str(rec.get("transaction_catg", "")).strip()
        if not catg or catg == "null":
            continue
        # Match on substring for interest categories.
        match = None
        for keep in INTEREST_CATEGORIES:
            if keep.lower() in catg.lower():
                match = keep
                break
        if not match:
            continue
        ttype = str(rec.get("transaction_type", ""))
        key = (ttype, catg)
        if key in seen:
            continue
        seen.add(key)
        today_v = _to_float(rec.get("transaction_today_amt"))
        mtd_v = _to_float(rec.get("transaction_mtd_amt"))
        fytd_v = _to_float(rec.get("transaction_fytd_amt"))
        if today_v is None and mtd_v is None and fytd_v is None:
            continue
        rows.append({
            "record_date": latest,
            "category": catg[:60],
            "transaction_type": ttype,
            "today_usd_mm": (f"{today_v:.0f}"
                             if today_v is not None else ""),
            "mtd_usd_mm": (f"{mtd_v:.0f}"
                           if mtd_v is not None else ""),
            "fytd_usd_mm": (f"{fytd_v:.0f}"
                            if fytd_v is not None else ""),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_dts: no matched cats, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort deposits descending by MTD, withdrawals separately.
    def _sort_key(r):
        mtd = 0.0
        try:
            mtd = float(r["mtd_usd_mm"] or 0)
        except Exception:
            pass
        return (r["transaction_type"], -mtd)

    rows.sort(key=_sort_key)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["record_date", "category", "transaction_type",
                  "today_usd_mm", "mtd_usd_mm", "fytd_usd_mm",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    dep = [r for r in rows if r["transaction_type"] == "Deposits"]
    wdr = [r for r in rows if r["transaction_type"] == "Withdrawals"]
    print(f"treasury_dts: {latest} | {len(rows)} cats "
          f"({len(dep)} dep / {len(wdr)} wdr) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
