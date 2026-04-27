#!/usr/bin/env python3
"""build_sec_whistleblower.py — SEC whistleblower / internal-investigation tape.

3 kinds of governance-alert filings:
- whistleblower — Dodd-Frank Sec 922 (2010). SEC whistleblower awards
  > $2B total 2012-2025. Presence in 8-K/10-K language often signals
  live SEC/DOJ probe. Commonly precedes -10-20% drawdown.
- internal_investigation — board/audit-committee probe. Often
  simultaneous with CFO/CEO exit. KPMG 2022 study: -8% CAR, +40%
  restatement probability within 18 months.
- clawback_policy — NYSE/Nasdaq listing rule (effective 2023 Oct) +
  Dodd-Frank Sec 954. Routine now but clustering around specific
  issuers = sign that incentive/restatement risk is high.

Economic readthrough:
- Whistleblower + internal_investigation cluster = short-conviction
  basket (trust collapse, covenant stress, NYSE/Nasdaq delisting risk).
- Clawback amendments spike when an actual restatement is pending —
  feeds sec_risks::material_weakness overlay.

Source: efts.sec.gov/LATEST/search-index
Output: sec_whistleblower.csv

Lookback: 45 days (investigations drag; don't lose signal tail).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_whistleblower.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "whistleblower": '"whistleblower"',
    "internal_investigation": '"internal investigation"',
    "clawback_policy": '"clawback policy"',
}

LIMITS = {
    "whistleblower": 100,
    "internal_investigation": 60,
    "clawback_policy": 100,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=45)).isoformat()
    d_to = today.isoformat()
    qq = urllib.parse.quote(query)
    url = (f"https://efts.sec.gov/LATEST/search-index?q={qq}"
           f"&dateRange=custom&startdt={d_from}&enddt={d_to}"
           f"&from=0&size={min(limit, 100)}")
    out: list[dict] = []
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"sec_whistleblower: {kind} fetch failed: {e}")
        return out
    for h in d.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        names_list = src.get("display_names") or []
        names_str = " ".join(names_list)
        m = TICKER_RE.search(names_str)
        out.append({
            "kind": kind,
            "ticker": m.group(1) if m else "",
            "name": (names_list[0] if names_list else "")[:80],
            "form": src.get("form", ""),
            "filed": src.get("file_date", ""),
            "accession": h.get("_id", ""),
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for kind, q in QUERIES.items():
        batch = _fetch(kind, q, LIMITS.get(kind, 100))
        counts[kind] = len(batch)
        rows.extend(batch)
        time.sleep(0.4)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_whistleblower: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["filed"], r["kind"]), reverse=True)
    fieldnames = ["kind", "ticker", "name", "form", "filed",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:12]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_whistleblower: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
