#!/usr/bin/env python3
"""build_fda_approvals.py — FDA new drug approvals (openFDA API).

PDUFA dates + FDA approvals = single biggest catalyst for small/mid
biotech (sub-$5B). FDA approval lifts sponsor 20-80% in a day. openFDA
/drug/drugsfda/ endpoint returns approval history with sponsor_name.

Source: api.fda.gov/drug/drugsfda.json
Output: fda_approvals.csv
Columns: application_no, sponsor_name, brand_name, action_date,
         submission_status, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_approvals.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Last 180 days of approvals, sorted by submission_status_date desc
URL = (
    "https://api.fda.gov/drug/drugsfda.json"
    "?search=submissions.submission_status:AP"
    "+AND+submissions.submission_status_date:"
    "[{start}+TO+{end}]"
    "&limit=200"
)


def fetch() -> list[dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=180)
    url = URL.format(
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"fda: {e}")
        return []
    return data.get("results", [])


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    seen: set[str] = set()
    for it in items:
        app = it.get("application_number", "")
        sponsor = it.get("sponsor_name", "")
        brand = ""
        prods = it.get("products") or []
        if prods:
            brand = prods[0].get("brand_name", "") or ""
        for sub in it.get("submissions") or []:
            if sub.get("submission_status") != "AP":
                continue
            dtd = sub.get("submission_status_date", "")
            key = f"{app}:{sub.get('submission_number','')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "application_no": app,
                "sponsor_name": sponsor[:80],
                "brand_name": brand[:60],
                "action_date": dtd[:4] + "-" + dtd[4:6] + "-" + dtd[6:8]
                    if len(dtd) == 8 else dtd,
                "submission_status": sub.get("submission_status", ""),
                "captured_at": now,
            })
    rows.sort(key=lambda r: r["action_date"], reverse=True)
    rows = rows[:200]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "application_no", "sponsor_name", "brand_name",
                "action_date", "submission_status", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fda_approvals: {len(rows)} approvals | latest {latest.get('action_date','?')} "
          f"{latest.get('sponsor_name','?')[:40]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
