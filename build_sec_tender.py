#!/usr/bin/env python3
"""build_sec_tender.py — EDGAR tender-offer tape.

Covers three Schedule TO variants:
- SC TO-T: third-party acquirer tender offer (hostile or
  negotiated, often stock + cash).
- SC TO-I: issuer (company) self-tender (share buyback offer
  to shareholders at a premium).
- SC 14D9: target company's board response to a tender offer
  (recommend accept / reject / neutral).

Economic readthrough:
- SC TO-T -> hard deal event, arb spread live; target pops to
  offer price minus time-value discount.
- SC TO-I at premium -> supports EPS through reduced share count;
  bullish absent balance-sheet stress.
- SC 14D9 "reject" -> board fighting the deal, counter-bid odds
  increase, target may trade above offer.

Source: SEC EDGAR full-text search
https://efts.sec.gov/LATEST/search-index

Output: sec_tender.csv
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
OUT_CSV = ROOT / "sec_tender.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FORMS = ["SC TO-T", "SC TO-I", "SC 14D9"]


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
        print(f"sec_tender: fetch {form} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=45)).isoformat()
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
            target_ticker = ""
            target_name = ""
            for n in names:
                m = re.search(r"\(([A-Z\.\-]{1,6})\)", n)
                if m and not target_ticker:
                    target_ticker = m.group(1)
                if not target_name:
                    target_name = n.split("  (")[0][:60]
            rows.append({
                "filed": filed,
                "form": actual_form,
                "target_ticker": target_ticker,
                "target": target_name,
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_tender: no rows, keeping {OUT_CSV.name}")
        return

    # Dedup by accession
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
    fieldnames = ["filed", "form", "target_ticker", "target", "ciks",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_form = {}
    for r in rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    fb = " ".join(f"{k}={v}" for k, v in sorted(by_form.items()))
    with_t = sum(1 for r in rows if r["target_ticker"])
    top = [r for r in rows if r["target_ticker"]][:5]
    tb = " | ".join(f"{r['target_ticker']}:{r['form']}" for r in top)
    print(f"sec_tender: {len(rows)} 45d ({with_t} tagged) | {fb} | "
          f"active targets: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
