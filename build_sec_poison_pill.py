#!/usr/bin/env python3
"""build_sec_poison_pill.py - EDGAR 8-K poison pill / shareholder rights plan tape.

A poison pill (formal name: shareholder rights plan) is a defensive
takeover-resistance device. When triggered (a hostile acquirer crosses
a threshold, typically 10-20% ownership), non-acquirer shareholders get
the right to buy shares at a steep discount, diluting the acquirer.

Covered keyword variants:
- poison pill
- rights plan (broader catch, includes term-limited rights plans)
- shareholder rights plan (canonical form)
- limited duration rights (modern form, 1-year expiry)

Economic readthrough:
- Poison pill adoption = board sees credible takeover threat
- Often precedes or follows 13D filing by activist
- Adoption compresses bid premium (defensive value accretion)
- Termination / expiry often signals deal negotiations entering
  friendly territory (poison-pill wave-off)

Source: EDGAR full-text search (efts.sec.gov), 8-K forms, 90d lookback.
Output: sec_poison_pill.csv
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
OUT_CSV = ROOT / "sec_poison_pill.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES = [
    ("\"poison pill\"", "poison_pill"),
    ("\"rights plan\"", "rights_plan"),
    ("\"shareholder rights plan\"", "shareholder_rights_plan"),
    ("\"limited duration rights\"", "limited_duration_rights"),
]


def _fetch(d_from: str, d_to: str, q_term: str) -> dict:
    qs = urllib.parse.urlencode({
        "q": q_term,
        "dateRange": "custom",
        "startdt": d_from,
        "enddt": d_to,
        "forms": "8-K",
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sec_poison_pill: fetch {q_term} failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=90)).isoformat()
    d_to = today.isoformat()

    rows: list[dict] = []
    for q_term, kind in QUERIES:
        j = _fetch(d_from, d_to, q_term)
        hits = j.get("hits", {}).get("hits", [])
        for h in hits[:80]:
            src = h.get("_source", {})
            ciks = src.get("ciks") or []
            names = src.get("display_names") or []
            filed = src.get("file_date", "")
            actual_form = src.get("form", "8-K")
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
                "kind": kind,
                "ticker": ticker,
                "issuer": issuer,
                "ciks": "|".join(ciks[:2])[:50],
                "accession": adsh[:25],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_poison_pill: no rows, keeping {OUT_CSV.name}")
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
    fieldnames = ["filed", "form", "kind", "ticker", "issuer",
                  "ciks", "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v
                  in sorted(by_kind.items(), key=lambda kv: -kv[1]))
    with_t = sum(1 for r in rows if r["ticker"])
    top = [r for r in rows if r["ticker"]][:5]
    tb = " | ".join(f"{r['ticker']}:{r['kind']}" for r in top)
    print(f"sec_poison_pill: {len(rows)} 90d ({with_t} tagged) | "
          f"{kb} | defensives: [{tb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
