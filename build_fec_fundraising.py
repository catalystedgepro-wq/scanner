#!/usr/bin/env python3
"""build_fec_fundraising.py — Federal election fundraising leaderboard.

Tracks top candidates by receipts in the current election cycle via
OpenFEC /v1/candidates/totals/.  Campaign-finance flow is a leading
indicator of:
- Policy risk (sector targeting: pharma price controls, oil
  drilling, big tech antitrust)
- Who wins in 2-year cycles → maps to sectoral themes
- PAC + dark-money pressure on specific industries

We pull the top 60 candidates by receipts for cycle=2026, tag party,
office (P=President, S=Senate, H=House), state, and compute party
totals for quick comparison.

Source: https://api.open.fec.gov/v1/candidates/totals/
API key: DEMO_KEY (rate-limited but functional for daily pulls)
Output: fec_fundraising.csv

Lookback: Current cycle (2026).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fec_fundraising.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.open.fec.gov/v1/candidates/totals/"
API_KEY = "DEMO_KEY"
CYCLE = 2026
PER_PAGE = 60


def _fetch() -> list[dict]:
    params = {
        "cycle": CYCLE,
        "per_page": PER_PAGE,
        "sort": "-receipts",
        "api_key": API_KEY,
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fec_fundraising: fetch failed: {e}")
        return []
    res = d.get("results", [])
    return res if isinstance(res, list) else []


def main() -> None:
    results = _fetch()
    if not results:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fec_fundraising: no fetch, keeping {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for c in results:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "") or ""
        receipts = float(c.get("receipts") or 0)
        disbursements = float(c.get("disbursements") or 0)
        cash_on_hand = float(c.get("last_cash_on_hand_end_period")
                             or c.get("cash_on_hand_end_period") or 0)
        rows.append({
            "name": name[:40],
            "party": c.get("party_full", "") or c.get("party", ""),
            "office": c.get("office_full", "") or c.get("office", ""),
            "state": c.get("state", ""),
            "district": c.get("district", ""),
            "cycle": c.get("cycle", CYCLE),
            "receipts_usd_m": round(receipts / 1e6, 3),
            "disbursements_usd_m": round(disbursements / 1e6, 3),
            "cash_on_hand_usd_m": round(cash_on_hand / 1e6, 3),
            "candidate_id": c.get("candidate_id", ""),
            "captured_at": now_iso,
        })

    if not rows:
        return

    rows.sort(key=lambda r: r["receipts_usd_m"], reverse=True)

    fieldnames = ["name", "party", "office", "state", "district",
                  "cycle", "receipts_usd_m", "disbursements_usd_m",
                  "cash_on_hand_usd_m", "candidate_id", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Party breakdown.
    by_party: dict[str, float] = {}
    by_office: dict[str, float] = {}
    for r in rows:
        key = r["party"][:3].upper() or "IND"
        by_party[key] = by_party.get(key, 0) + r["receipts_usd_m"]
        okey = (r["office"] or "?")[:1].upper()
        by_office[okey] = by_office.get(okey, 0) + r["receipts_usd_m"]

    top3 = rows[:3]
    top_blurb = " ".join(
        f"{r['name'].split(',')[0][:8]}"
        f"({r['party'][:3].upper()}) ${r['receipts_usd_m']:.1f}M"
        for r in top3)
    party_blurb = " ".join(
        f"{k}=${v:.1f}M" for k, v in sorted(
            by_party.items(), key=lambda x: -x[1])[:3])
    office_blurb = " ".join(
        f"{k}=${v:.1f}M" for k, v in sorted(
            by_office.items(), key=lambda x: -x[1])[:4])
    print(f"fec_fundraising: {len(rows)} candidates cycle={CYCLE} | "
          f"top: {top_blurb} | parties: {party_blurb} | "
          f"offices: {office_blurb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
