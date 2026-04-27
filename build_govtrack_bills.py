#!/usr/bin/env python3
"""build_govtrack_bills.py — Active US congressional bill tracker.

GovTrack aggregates US Congress bills with status timestamps, sponsor
info, and subject classification. Bills that advance (House passage,
Senate introduction, committee vote, presidential action) are
leading indicators for regulatory shocks:

- Defense authorization / appropriations → LMT, RTX, NOC, GD, HII
- Tax policy bills → bank / REIT / pass-through exposure
- Healthcare / drug pricing bills → UNH, CVS, MRK, LLY, NVO
- Crypto bills (stablecoin, market structure) → COIN, HOOD, MSTR
- AI / export-controls bills → NVDA, AMD, SMCI
- Energy subsidies / permitting → FSLR, SEDG, NEE, BE
- Trade / tariff bills → logistics (FDX, UPS), retailers (WMT, TGT,
  COST), semis (MU, INTC)

Output (top 40 most-recently-advanced bills):
  bill_num, title, sponsor_party, introduced_date, status,
  current_status_date, committee, url, captured_at

Source: www.govtrack.us/api/v2/bill (no key, JSON, CC-BY).

Signal for trading:
- Bill with "REPORTED" or "PASS_OVER" status in sensitive committee
  = 1-2 day sector heat on affected tickers.
- "PASSED_BILL" (both chambers) with no White House veto signal =
  heavier positioning on expected outcome.
- Bills mentioning specific company names in title = headline risk
  (screen by keyword match against Russell 3000 tickers downstream).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "govtrack_bills.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.govtrack.us/api/v2/bill"


def main() -> None:
    qs = urllib.parse.urlencode({
        "congress": "119",
        "order_by": "-current_status_date",
        "limit": "60",
    })
    url = f"{URL}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"govtrack_bills: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"govtrack_bills: keeping existing {OUT_CSV.name}")
        return

    bills = d.get("objects", []) or []
    rows: list[dict] = []
    for b in bills:
        sponsor = b.get("sponsor") or {}
        rows.append({
            "bill_num": b.get("display_number") or "",
            "title": (b.get("title_without_number") or b.get("title")
                      or "")[:200],
            "sponsor_party": sponsor.get("party") or "",
            "sponsor_state": sponsor.get("state") or "",
            "introduced_date": b.get("introduced_date") or "",
            "status": b.get("current_status") or "",
            "current_status_date": b.get("current_status_date") or "",
            "url": b.get("link") or "",
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"govtrack_bills: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort by current_status_date descending.
    rows.sort(key=lambda r: r["current_status_date"], reverse=True)
    rows = rows[:40]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["bill_num", "title", "sponsor_party", "sponsor_state",
                  "introduced_date", "status", "current_status_date",
                  "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Status breakdown for summary.
    from collections import Counter
    st = Counter(r["status"] for r in rows)
    top_st = ", ".join(f"{k}={v}" for k, v in st.most_common(3))
    top = rows[0]
    print(f"govtrack_bills: {len(rows)} bills | {top_st} | "
          f"latest: {top['bill_num']} ({top['status']}, "
          f"{top['current_status_date']}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
