#!/usr/bin/env python3
"""build_sec_uplist.py - EDGAR Form 8-A exchange registration tape.

Form 8-A12B (Section 12(b) registration, listed) and
Form 8-A12G (Section 12(g) registration, OTC) are the
registration statements filed when an issuer registers a
class of securities under the Exchange Act.

The 8-A12B is functionally the paperwork for an uplisting
or initial exchange listing. When a sub-$5 OTC name files
8-A12B, that is an imminent Nasdaq/NYSE uplist - historically
a +10-30% short-term catalyst tape.

Covered form types:
- 8-A12B: Section 12(b) registration (NYSE / Nasdaq)
- 8-A12G: Section 12(g) registration (non-listed equity)
- 8-A12B/A, 8-A12G/A: amendments

Economic readthrough:
- Uplist = institutional-access unlock
  (institutional mandates often forbid OTC holdings)
- Uplist often follows reverse-split (shared cluster with
  sec_splits) and capital raise (sec_financing)
- Initial 8-A12B on an already-NYSE-listed name can signal
  a new share class (Class B issuance) - neutral

Source: SEC EDGAR full-text search, 30d lookback.
Output: sec_uplist.csv
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
OUT_CSV = ROOT / "sec_uplist.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["8-A12B", "8-A12G", "8-A12B/A", "8-A12G/A"]


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
        print(f"sec_uplist: fetch {form} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=30)).isoformat()
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
            print(f"sec_uplist: 0 rows, keeping {OUT_CSV.name}")
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
    print(f"sec_uplist: {len(rows)} 30d ({with_t} tagged) | "
          f"{fb} | uplists: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
