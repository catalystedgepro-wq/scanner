#!/usr/bin/env python3
"""build_sec_restatements.py — EDGAR amended-filing / restatement tape.

Amended annual/quarterly/8-K filings signal that the original filing
contained material errors, non-reliance on prior financials, or a
re-categorization of accounting treatment. Restatements are Non-
Reliance Item 4.02 8-Ks and the subsequent 10-K/A or 10-Q/A.

Covers:
- 10-K/A: annual report amendment (full restatement).
- 10-Q/A: quarterly amendment.
- 20-F/A: foreign private issuer annual amendment.
- 40-F/A: Canadian MJDS annual amendment.
- 6-K/A: foreign 6-K amendment (periodic).
- 8-K/A: 8-K amendment (often follow-up to original item).

Economic readthrough:
- 10-K/A with restated financials -> credibility hit, auditor
  scrutiny intensifies, Russell/S&P index eligibility risk.
- 8-K/A re-filed within days -> often benign (exhibit missing);
  8-K/A weeks later -> material correction.
- Clustered amendments across one ticker -> audit committee
  action, often feeds sec_audit cluster (going-concern etc).
- 20-F/A on ADR -> SEC-staff comment response, often precedes
  SEC investigation or PCAOB concerns for Chinese ADRs.

Source: SEC EDGAR full-text search
https://efts.sec.gov/LATEST/search-index

Output: sec_restatements.csv
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
OUT_CSV = ROOT / "sec_restatements.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["10-K/A", "10-Q/A", "20-F/A", "40-F/A", "6-K/A", "8-K/A"]


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
        print(f"sec_restatements: fetch {form} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=30)).isoformat()
    d_to = today.isoformat()

    rows: list[dict] = []
    by_ticker: dict[str, int] = {}
    for form in FORMS:
        j = _fetch(d_from, d_to, form)
        hits = j.get("hits", {}).get("hits", [])
        for h in hits[:100]:
            src = h.get("_source", {})
            ciks = src.get("ciks") or []
            names = src.get("display_names") or []
            filed = src.get("file_date", "")
            period = src.get("period_ending", "")
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
                "period": period,
                "ticker": ticker,
                "issuer": issuer,
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })
            if ticker:
                by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_restatements: no rows, keeping {OUT_CSV.name}")
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
    fieldnames = ["filed", "form", "period", "ticker", "issuer",
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
    clusters = sorted(by_ticker.items(),
                       key=lambda kv: -kv[1])[:5]
    cb = " | ".join(f"{t}:{v}" for t, v in clusters)
    print(f"sec_restatements: {len(rows)} 30d ({with_t} tagged) | "
          f"{fb} | clusters: [{cb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
