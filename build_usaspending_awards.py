#!/usr/bin/env python3
"""build_usaspending_awards.py — Top US federal contract awards.

US government prime contract awards >$10M from last 30 days. Direct
revenue catalyst feed for defense, aerospace, IT services, healthcare
IT, construction, and energy-contractor stocks:
- LMT, RTX, NOC, GD, BA, LHX — prime defense
- BAH, SAIC, LDOS, CACI, CSL, ACN — IT services/consulting
- KBR, FLR — engineering/construction
- HII, CW, MRCY — naval/sensors
- HAL, SLB, BKR — DOE/DOD energy support

Trade context:
- Award >$500M single prime → typically 1-3% pop next session
- Consecutive awards same prime over 5 days → streak momentum
- Cost-plus type C/D contracts → margin expansion on extensions
- BAA (A) type = definitive contract (shipping revenue now) vs IDIQ

Source: api.usaspending.gov v2 (free, no key, POST /search/spending_by_award).

Output: usaspending_awards.csv
Columns: award_id, recipient, amount_usd, awarding_agency, award_type,
         date_range, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usaspending_awards.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


def main() -> None:
    today = dt.date.today()
    start = today - dt.timedelta(days=60)
    body = json.dumps({
        "filters": {
            "time_period": [{
                "start_date": start.isoformat(),
                "end_date": today.isoformat(),
            }],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount",
                   "Awarding Agency", "Award Type", "Description",
                   "Start Date", "End Date"],
        "page": 1,
        "limit": 60,
        "sort": "Award Amount",
        "order": "desc",
    }).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"usaspending_awards: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"usaspending_awards: keeping existing {OUT_CSV.name}")
        return

    results = d.get("results") or []
    rows: list[dict] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        amt = float(r.get("Award Amount") or 0)
        if amt < 10_000_000:  # drop sub-$10M noise
            continue
        rows.append({
            "award_id": (r.get("Award ID") or "")[:48],
            "recipient": (r.get("Recipient Name") or "")[:48],
            "amount_usd": f"{amt:.0f}",
            "awarding_agency": (r.get("Awarding Agency") or "")[:36],
            "award_type": (r.get("Award Type") or "")[:24],
            "date_range": (
                f"{(r.get('Start Date') or '')[:10]}..{(r.get('End Date') or '')[:10]}"
            ),
            "description": (r.get("Description") or "")[:96],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"usaspending_awards: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: -float(r["amount_usd"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["award_id", "recipient", "amount_usd", "awarding_agency",
                  "award_type", "date_range", "description", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total = sum(float(r["amount_usd"]) for r in rows)
    top = rows[0] if rows else {}
    per_agency: dict[str, float] = {}
    for r in rows:
        per_agency[r["awarding_agency"]] = (
            per_agency.get(r["awarding_agency"], 0.0)
            + float(r["amount_usd"])
        )
    top_agency = max(per_agency.items(), key=lambda kv: kv[1],
                     default=("?", 0))
    print(f"usaspending_awards: {len(rows)} awards | "
          f"total=${total/1e9:.1f}B | top: "
          f"{top.get('recipient','?')[:24]}=${float(top.get('amount_usd',0))/1e9:.2f}B"
          f" | top agency: {top_agency[0][:20]}=${top_agency[1]/1e9:.1f}B "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
