#!/usr/bin/env python3
"""build_sec_s4.py — EDGAR Form S-4 M&A registration tape.

Form S-4 is the registration statement filed when a public company
issues shares as consideration for an M&A transaction (stock-for-
stock, stock+cash, or exchange offer). Unlike an 8-K deal-
announcement, an S-4 includes the definitive share-issuance terms,
pro-forma financials, fairness opinion, and target board vote
context. Filing cadence of an S-4 = committed deal, regulatory
review-ready.

Economic readthrough:
- S-4 filed -> deal is progressing past MOU/LOI stage, target
  shareholder vote approaching (arb window narrows).
- Amended S-4 (S-4/A) -> negotiating around antitrust, financing,
  or material adverse change clauses; spread widens.
- Large registration amount -> major strategic consolidation;
  acquirer EPS accretion math becomes tradable.

Source: SEC EDGAR full-text search
https://efts.sec.gov/LATEST/search-index?forms=S-4

Output: sec_s4.csv
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
OUT_CSV = ROOT / "sec_s4.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"


def _fetch(d_from: str, d_to: str, form: str = "S-4") -> dict:
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
        print(f"sec_s4: fetch {form} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=30)).isoformat()
    d_to = today.isoformat()

    rows: list[dict] = []
    for form in ("S-4", "S-4/A"):
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
            acquirer = ""
            for n in names:
                m = re.search(r"\(([A-Z\.\-]{1,6})\)", n)
                if m and not ticker:
                    ticker = m.group(1)
                if not acquirer:
                    acquirer = n.split("  (")[0][:60]
            rows.append({
                "filed": filed,
                "form": actual_form,
                "ticker": ticker,
                "acquirer": acquirer,
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_s4: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "form", "ticker", "acquirer", "ciks",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_form = {}
    for r in rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    fb = " ".join(f"{k}={v}" for k, v in sorted(by_form.items()))
    with_t = sum(1 for r in rows if r["ticker"])
    top = [r for r in rows if r["ticker"]][:5]
    tb = " | ".join(f"{r['ticker']}:{r['form']}" for r in top)
    print(f"sec_s4: {len(rows)} 30d ({with_t} tagged) | {fb} | "
          f"active deals: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
