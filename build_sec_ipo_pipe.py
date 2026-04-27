#!/usr/bin/env python3
"""build_sec_ipo_pipe.py — EDGAR IPO/registration pipeline tape.

Covers four primary-registration forms that feed the IPO /
new-supply pipeline:
- S-1: initial public offering registration (US domestic).
- S-1/A: S-1 amendments (pricing cycle, deal tuning).
- F-1: foreign private issuer IPO registration.
- F-1/A: foreign IPO amendment.
- 1-A: Reg A+ offering (small-cap, $75M cap).

Economic readthrough:
- Spike in S-1 filings -> IPO window open, new supply incoming
  over 4-8 weeks (roadshow → pricing).
- F-1 filings -> Chinese / European / LatAm IPO pipeline
  (index rebalance exposure for emerging-market funds).
- 1-A Reg A+ -> micro-cap dilution risk, speculative tape.
- S-1/A pricing tightening = deal on-target; wider = soft demand.

Source: SEC EDGAR full-text search
https://efts.sec.gov/LATEST/search-index

Output: sec_ipo_pipe.csv
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
OUT_CSV = ROOT / "sec_ipo_pipe.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["S-1", "S-1/A", "F-1", "F-1/A", "1-A", "1-A/A"]


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
        print(f"sec_ipo_pipe: fetch {form} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=21)).isoformat()
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
            biz = src.get("biz_locations") or []
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
                "location": (biz[0] if biz else "")[:40],
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_ipo_pipe: no rows, keeping {OUT_CSV.name}")
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
    fieldnames = ["filed", "form", "ticker", "issuer", "location",
                  "ciks", "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_form = {}
    for r in rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    fb = " ".join(f"{k}={v}" for k, v
                   in sorted(by_form.items(), key=lambda kv: -kv[1]))
    with_t = sum(1 for r in rows if r["ticker"])
    top = [r for r in rows if r["ticker"]][:5]
    tb = " | ".join(f"{r['ticker']}:{r['form']}" for r in top)
    print(f"sec_ipo_pipe: {len(rows)} 21d ({with_t} tagged) | {fb} | "
          f"pipeline: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
