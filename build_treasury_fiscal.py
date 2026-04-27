#!/usr/bin/env python3
"""build_treasury_fiscal.py — US Treasury daily debt + cash balance.

Treasury daily data is a real-time federal finance gauge, invaluable
when debt ceiling / continuing resolution news hits. Operating cash
balance < $150B = debt ceiling brinksmanship risk (X-date proximity).
Debt change acceleration = bond supply pressure (TLT down, yields up).

Trade uses:
- Operating cash < $300B + congress gridlock: T-bill yields spike at
  specific maturity buckets, duration ETFs (TLT) weak, gold (GLD) bid.
- Debt-to-penny > $50B daily jump: auction overhang — short TLT,
  lift regional banks (higher NIM) until auction absorbs.
- Tax receipts (withholding) YoY decline for 2+ weeks: labor market
  softening, rate cut odds rise (XLRE, XLU rally).
- Corporate estimated taxes (quarterly) vs prior year: earnings-season
  sentiment proxy, lifts or fades SPY ahead of reports.

Sources:
- api.fiscaldata.treasury.gov/.../debt_to_penny (daily total debt)
- api.fiscaldata.treasury.gov/.../operating_cash_balance (daily TGA)
Both public, no key, no rate limit observed.

Output: treasury_fiscal.csv
Columns: record_date, total_debt, debt_held_public, intragov_held,
         debt_dod_change, tga_balance, tga_dod_change, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_fiscal.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
DEBT_EP = f"{BASE}/v2/accounting/od/debt_to_penny"
TGA_EP  = f"{BASE}/v1/accounting/dts/operating_cash_balance"


def fetch(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"treasury_fiscal: {e}")
        return []
    return payload.get("data", []) or []


def main() -> None:
    qs = "sort=-record_date&page%5Bsize%5D=90"
    debt_rows = fetch(f"{DEBT_EP}?{qs}")
    tga_filter = urllib.parse.quote(
        "account_type:eq:Treasury General Account (TGA) Opening Balance",
        safe=":",
    )
    tga_rows = fetch(f"{TGA_EP}?{qs}&filter={tga_filter}")
    # Map by date.
    debt_by_date: dict[str, dict] = {}
    for r in debt_rows:
        d = r.get("record_date", "")
        if d:
            debt_by_date[d] = r
    tga_by_date: dict[str, float] = {}
    for r in tga_rows:
        d = r.get("record_date", "")
        raw = r.get("open_today_bal", "")
        if not d or raw in ("", "null", None):
            continue
        try:
            tga_by_date[d] = float(raw)
        except (ValueError, TypeError):
            continue

    dates = sorted(debt_by_date.keys(), reverse=True)[:90]
    dates.reverse()  # chronological

    rows: list[dict] = []
    prev_debt: float | None = None
    prev_tga: float | None = None
    for d in dates:
        rec = debt_by_date[d]
        try:
            total = float(rec.get("tot_pub_debt_out_amt", "") or 0)
            pub   = float(rec.get("debt_held_public_amt", "") or 0)
            intra = float(rec.get("intragov_hold_amt", "") or 0)
        except (ValueError, TypeError):
            continue
        tga = tga_by_date.get(d)
        # TGA endpoint uses $M; debt is raw dollars. Normalize TGA to raw.
        if tga is not None:
            tga = tga * 1_000_000
        row = {
            "record_date": d,
            "total_debt": f"{total:.2f}",
            "debt_held_public": f"{pub:.2f}",
            "intragov_held": f"{intra:.2f}",
            "debt_dod_change": f"{total - prev_debt:.2f}" if prev_debt else "",
            "tga_balance": f"{tga:.2f}" if tga is not None else "",
            "tga_dod_change": (
                f"{tga - prev_tga:.2f}"
                if tga is not None and prev_tga is not None else ""
            ),
        }
        rows.append(row)
        prev_debt = total
        if tga is not None:
            prev_tga = tga

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 150:
        print(f"treasury_fiscal: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["record_date", "total_debt", "debt_held_public",
                        "intragov_held", "debt_dod_change",
                        "tga_balance", "tga_dod_change", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    total_t = float(latest.get("total_debt", 0) or 0) / 1e12
    tga_b = (
        float(latest.get("tga_balance", 0) or 0) / 1e9
        if latest.get("tga_balance") else 0.0
    )
    print(f"treasury_fiscal: {len(rows)} days | latest "
          f"{latest.get('record_date','?')} "
          f"debt=${total_t:.2f}T tga=${tga_b:.0f}B -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
