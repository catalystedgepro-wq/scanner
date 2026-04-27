#!/usr/bin/env python3
"""build_sec_banking.py — SEC bank regulatory / capital-raise tape.

5 banking-specific 8-K kinds for US depository institutions:

- fdic — FDIC notices (deposit-insurance-linked, receiver-
  appointment, cease-and-desist, enforcement). Cluster flags
  regional-bank stress (SVB/SBNY 2023 analog).
- occ — Office of the Comptroller of the Currency enforcement /
  consent orders. Mid-cycle stress signal.
- capital_raise — 8-K disclosing capital raise. Banks: Series A
  preferred, Tier 1/Tier 2 issuance. Typical after-stress action.
- stress_test — CCAR / DFAST disclosure. Annual, BHC ≥$100B.
  Pass/fail signals relative strength vs JPM/BAC/C/WFC.
- deposit_insurance — FDIC-insurance-linked assurance. Often
  routine Q&A language but clusters flag worried investors.

Economic readthrough:
- FDIC + capital_raise cluster -> KRE regional banks relative
  weakness / SPDR KBWR basket breakdown.
- Stress_test clusters ahead of Fed release (late June) ->
  BAC/WFC call-wing positioning.
- Cross-ref with sec_financing::atm_offering & rights_offering
  for doubling-down shareholder dilution pressure.

Source: efts.sec.gov/LATEST/search-index
Output: sec_banking.csv

Lookback: 45 days.
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
OUT_CSV = ROOT / "sec_banking.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "fdic": '"FDIC"',
    "occ": '"OCC"',
    "capital_raise": '"capital raise"',
    "stress_test": '"stress test"',
    "deposit_insurance": '"deposit insurance"',
}

LIMITS = {
    "fdic": 150,
    "occ": 50,
    "capital_raise": 65,
    "stress_test": 15,
    "deposit_insurance": 200,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=45)).isoformat()
    d_to = today.isoformat()
    qq = urllib.parse.quote(query)
    forms = urllib.parse.quote("8-K")
    url = (f"https://efts.sec.gov/LATEST/search-index?q={qq}"
           f"&dateRange=custom&startdt={d_from}&enddt={d_to}"
           f"&forms={forms}&from=0&size={min(limit, 100)}")
    out: list[dict] = []
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"sec_banking: {kind} fetch failed: {e}")
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
            print(f"sec_banking: no fetch, keeping {OUT_CSV.name}")
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
    print(f"sec_banking: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
