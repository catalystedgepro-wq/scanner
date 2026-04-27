#!/usr/bin/env python3
"""build_fda_510k.py — FDA 510(k) medical device clearances.

510(k) is the fast-track device clearance pathway. ~3,500 clearances
per year vs ~50 PMA (de novo) approvals. Catalyst for medical device
makers when novel/implantable device gets cleared, opening new
revenue line.

Signal:
- Cluster of 510(k)s in a specific advisory_committee_description
  (Cardiovascular, Orthopedic, Neurology) = segment tailwind
- High-profile applicant clearances = near-term revenue unlock
- Advisory committee mix tells you where med-tech innovation is
  concentrating

Drives:
- Large-cap med-tech (MDT, SYK, BDX, BSX, ISRG, EW, ZBH)
- Orthopedic (SYK, ZBH, NUVA, ATEC, SIBN)
- Cardiovascular (MDT, EW, SHOC, PRCT, CDNA)
- Diagnostic (DHR, A, WAT, BIO, RGEN, EXAS, GH)
- Aesthetic (ALGN, ANGL, INMD)
- Spine/robotics (SYK, ATEC, SIBN, GMED, AXGN)
- Small-cap device IPOs (PRCT, ATEC, NUVA)

Source: api.fda.gov/device/510k.json (openFDA, free, no key).
Output: fda_510k.csv
Columns: decision_date, k_number, applicant, device_name,
         advisory_committee, country, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_510k.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.fda.gov/device/510k.json"

WINDOW_DAYS = 60
LIMIT_PER_PAGE = 100


def _fetch(since: str, until: str, skip: int) -> dict | None:
    search = f"decision_date:[{since} TO {until}]"
    params = urllib.parse.urlencode({
        "search": search,
        "limit": str(LIMIT_PER_PAGE),
        "skip": str(skip),
    })
    url = f"{BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fda_510k: skip={skip}: {e}")
        return None


def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    until = today.isoformat()
    since = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()

    rows: list[dict] = []

    import time
    skip = 0
    max_pages = 5  # 500 records cap (safe under openFDA 5k limit)
    for _ in range(max_pages):
        payload = _fetch(since, until, skip)
        if not payload:
            break
        results = payload.get("results") or []
        if not results:
            break
        for rec in results:
            decision = (rec.get("decision_date") or "").strip()
            k = (rec.get("k_number") or "").strip()
            applicant = (rec.get("applicant") or "").strip()[:60]
            device = (rec.get("device_name") or "").strip()[:80]
            comm = (rec.get("advisory_committee_description")
                    or "").strip()[:40]
            country = (rec.get("country_code") or "").strip()
            if not k or not decision:
                continue
            rows.append({
                "decision_date": decision,
                "k_number": k,
                "applicant": applicant,
                "device_name": device,
                "advisory_committee": comm,
                "country": country,
            })
        total = (payload.get("meta") or {}).get("results", {}).get("total", 0)
        skip += LIMIT_PER_PAGE
        if skip >= total:
            break
        time.sleep(0.5)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_510k: empty, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["decision_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["decision_date", "k_number", "applicant", "device_name",
                  "advisory_committee", "country", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Committee histogram.
    committees: dict[str, int] = {}
    for r in rows:
        c = r["advisory_committee"] or "UNK"
        committees[c] = committees.get(c, 0) + 1
    top = sorted(committees.items(), key=lambda kv: kv[1], reverse=True)[:4]
    bits = [f"{k}={v}" for k, v in top]
    print(f"fda_510k: {len(rows)} clearances | {WINDOW_DAYS}d window | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
