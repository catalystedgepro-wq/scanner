#!/usr/bin/env python3
"""build_regs_dockets.py — regulations.gov active dockets by agency.

Regulatory dockets at major federal agencies. Active rulemaking
dockets drive sector repricing:
- FTC     -> M&A blocking (MSFT/ATVI precedent, KR/ACI outcome)
- FDA     -> device / food / drug approval tracks (MRNA, BNTX, LLY,
           TLRY, CGC)
- FAA     -> airline route/cert cases (BA, SPR, DAL, UAL, LUV)
- EPA     -> emissions rules (CVX, XOM, DOW, LYB, RL, NUE, X, CLF)
- DOT     -> freight/rail rulemaking (CSX, UNP, NSC, CP, CNI)
- OSHA/DOL-> labor compliance (AMZN, WMT, TSLA, F, GM)
- DEA     -> cannabis rescheduling (TLRY, CGC, CRON, ACB, GTBIF)

Source: api.regulations.gov/v4/dockets (DEMO_KEY rate-limited).

Output: regs_dockets.csv
Columns: agency, docket_id, docket_type, title, last_modified,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "regs_dockets.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.regulations.gov/v4/dockets"

AGENCIES = [
    "FTC", "FDA", "FAA", "EPA", "DOT", "OSHA", "DEA", "FCC",
    "CFPB", "NHTSA", "FERC",
]


def _fetch(agency: str) -> list:
    qs = urllib.parse.urlencode({
        "page[size]": 15,
        "sort": "-lastModifiedDate",
        "filter[agencyId]": agency,
        "api_key": "DEMO_KEY",
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        return d.get("data") or []
    except Exception as e:
        print(f"regs_dockets {agency}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    for agency in AGENCIES:
        items = _fetch(agency)
        for item in items:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes") or {}
            rows.append({
                "agency": agency,
                "docket_id": str(item.get("id") or "")[:32],
                "docket_type": str(attrs.get("docketType") or "")[:24],
                "title": str(attrs.get("title") or "")[:160],
                "last_modified": str(attrs.get("lastModifiedDate") or "")[:19],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"regs_dockets: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["last_modified"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["agency", "docket_id", "docket_type", "title",
                  "last_modified", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    per_agency: dict[str, int] = {}
    for r in rows:
        per_agency[r["agency"]] = per_agency.get(r["agency"], 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in
                         sorted(per_agency.items(), key=lambda kv: -kv[1]))
    print(f"regs_dockets: {len(rows)} dockets across "
          f"{len(per_agency)} agencies | {breakdown} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
