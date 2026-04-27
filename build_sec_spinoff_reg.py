#!/usr/bin/env python3
"""build_sec_spinoff_reg.py — EDGAR Form 10 spin-off registration tape.

A Form 10 (or 10-12B) is the registration statement for a
spin-off security before distribution. Parent co files Form
10 with SEC, then distributes shares pro-rata to existing
shareholders. The Form 10 filing marks the first public
disclosure of spin-off financials, capital structure, and
board composition.

Covers:
- 10: full registration statement (SB-2 replacement)
- 10-12B: Section 12(b) registration (listing)
- 10-12G: Section 12(g) registration (non-listed)
- 10/A, 10-12B/A, 10-12G/A: amendments

Economic readthrough:
- Form 10 filed -> spin-off distribution within ~90 days
- Parent sheds underperforming or overvalued biz unit
- Spin-offs historically alpha-generating (first 12-24m)
- Watch parent pre-spin for "sell the drop" trade and
  spinco post-distribution for fundamental repricing
- 10/A amendments = pricing cycle, often precedes distro

Source: SEC EDGAR full-text search 90d.
Output: sec_spinoff_reg.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_spinoff_reg.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["10-12B", "10-12G", "10-12B/A", "10-12G/A"]


def _fetch(d_from: str, d_to: str, form: str) -> dict:
    qs = urllib.parse.urlencode({
        "q": "",
        "dateRange": "custom",
        "startdt": d_from,
        "enddt": d_to,
        "forms": form,
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sec_spinoff_reg: fetch {form} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=90)).isoformat()
    d_to = today.isoformat()

    rows: list[dict] = []
    for form in FORMS:
        j = _fetch(d_from, d_to, form)
        hits = j.get("hits", {}).get("hits", [])
        for h in hits[:100]:
            src = h.get("_source", {})
            ciks = src.get("ciks") or []
            names = src.get("display_names") or []
            filed = src.get("file_date", "")
            actual_form = src.get("form", form)
            adsh = src.get("adsh", "")
            ticker = ""
            issuer = ""
            for n in names:
                m = re.search(r"\(([A-Z\.\-]{1,6})\)", n)
                if m and not ticker:
                    ticker = m.group(1)
                if not issuer:
                    issuer = n.split("  (")[0][:60]
            rows.append({
                "filed": filed,
                "form": actual_form,
                "ticker": ticker,
                "issuer": issuer,
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_spinoff_reg: no rows, keeping {OUT_CSV.name}")
        return

    seen = set()
    dedup = []
    for r in rows:
        k = r["accession"]
        if k and k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    rows = dedup

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "form", "ticker", "issuer",
                  "ciks", "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_form: dict[str, int] = {}
    for r in rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    fb = " ".join(f"{k}={v}" for k, v
                   in sorted(by_form.items(), key=lambda kv: -kv[1]))
    with_t = sum(1 for r in rows if r["ticker"])
    top = [r for r in rows if r["ticker"]][:5]
    tb = " | ".join(f"{r['ticker']}:{r['form']}" for r in top)
    print(f"sec_spinoff_reg: {len(rows)} 90d ({with_t} tagged) | "
          f"{fb} | pipeline: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
