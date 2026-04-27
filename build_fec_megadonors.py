#!/usr/bin/env python3
"""build_fec_megadonors.py — FEC large political contributions (2026 cycle).

Mega-donations ≥ $1M in the current two-year transaction cycle. Leading
signal for:
- Regulatory alignment: Major tech/pharma/oil donors signal which
  industries are defending policy flanks. Trump/Musk/Thiel dominance
  in 2026 cycle → long SpaceX-adjacent (IRDM), defense (LMT/NOC),
  crypto (COIN), oil (XOM/CVX).
- Individual wealth visibility: $50M+ single contributions imply
  liquidity events — IPO exits, secondary sales, stock grants. Track
  which billionaires are suddenly cash-rich.
- Committee concentration: When one Super PAC receives 80% of its
  funding from 3 donors, regulatory capture risk surfaces.

Source: api.open.fec.gov/v1 (free, DEMO_KEY 30 req/hr — single call
covers 100 largest donations in cycle, filtered >= $1M).

Output: fec_megadonors.csv
Columns: contributor, employer, occupation, amount_usd, committee,
         contribution_date, memo, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fec_megadonors.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.open.fec.gov/v1/schedules/schedule_a/"

# Optional user-supplied key: export FEC_API_KEY="..."
API_KEY = os.environ.get("FEC_API_KEY", "DEMO_KEY")
MIN_AMOUNT = 1_000_000


def fetch(cycle: int, min_amount: int, per_page: int = 100) -> list[dict]:
    params = {
        "api_key": API_KEY,
        "two_year_transaction_period": cycle,
        "min_amount": min_amount,
        "per_page": per_page,
        "sort": "-contribution_receipt_amount",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fec_megadonors: {e}")
        return []
    return body.get("results", []) or []


def main() -> None:
    cycle = dt.date.today().year
    if cycle % 2 == 1:
        cycle += 1
    results = fetch(cycle, MIN_AMOUNT, per_page=100)
    if not results and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"fec_megadonors: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for r in results:
        name = (r.get("contributor_name")
                or r.get("contributor_organization_name") or "").strip()
        if not name:
            continue
        rows.append({
            "contributor": name[:80],
            "employer": (r.get("contributor_employer") or "")[:60],
            "occupation": (r.get("contributor_occupation") or "")[:40],
            "amount_usd": f"{float(r.get('contribution_receipt_amount', 0)):.0f}",
            "committee": (r.get("committee", {}) or {}).get("name", "")[:60],
            "contribution_date": r.get("contribution_receipt_date", "")[:10],
            "memo": (r.get("memo_text") or "")[:80],
        })

    # Deduplicate on (contributor, date, amount) — FEC has amendment rows.
    seen: set[tuple[str, str, str]] = set()
    dedup: list[dict] = []
    for r in rows:
        key = (r["contributor"].upper(),
               r["contribution_date"],
               r["amount_usd"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    rows = dedup

    rows.sort(key=lambda r: float(r["amount_usd"]), reverse=True)
    rows = rows[:200]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["contributor", "employer", "occupation", "amount_usd",
                  "committee", "contribution_date", "memo", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top = rows[:3]
    top_s = " | ".join(
        f"{r['contributor'][:30]}=${float(r['amount_usd'])/1e6:.1f}M"
        for r in top)
    print(f"fec_megadonors: cycle={cycle} | {len(rows)} contribs >=$1M | "
          f"top: {top_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
