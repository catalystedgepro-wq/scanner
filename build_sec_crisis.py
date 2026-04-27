#!/usr/bin/env python3
"""build_sec_crisis.py — SEC operational crisis / cyber tape.

5 8-K kinds across operational-disruption vectors:
- force_majeure — hurricane/earthquake/strike clause invocation;
  often precedes guidance revision by 2-4 weeks.
- cyberattack — SEC Rule 106 (2023) mandates 4-day disclosure;
  avg -3-5% day-one, tails to -10% if breach expands.
- ransomware — operational shutdown signal; CLNE/MGM/CLX templates
  showed 15-30% revenue-quarter hit.
- supply_chain_disruption — semiconductor/rare-earth/logistics
  bottleneck signal; upstream capex feedthrough.
- product_recall — direct liability + secondary-earnings hit;
  automotive (F/GM), pharma/medtech (ABT/MDT), food (KHC/GIS) beta.

Economic readthrough:
- Cyber cluster → CRWD/PANW/ZS/S bid (incident-response tail wind).
- Force-majeure cluster → commodity-price divergence (disrupted
  supply drives brent/copper/lithium).
- Product recall → tort-liability overhang on insurer (CB/TRV/AIG).

Source: efts.sec.gov/LATEST/search-index
Output: sec_crisis.csv
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
OUT_CSV = ROOT / "sec_crisis.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "force_majeure": '"force majeure"',
    "cyberattack": '"cyberattack"',
    "ransomware": '"ransomware"',
    "supply_chain": '"supply chain disruption"',
    "product_recall": '"product recall"',
}

LIMITS = {
    "force_majeure": 150,
    "cyberattack": 60,
    "ransomware": 80,
    "supply_chain": 40,
    "product_recall": 60,
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
        print(f"sec_crisis: {kind} fetch failed: {e}")
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
            print(f"sec_crisis: no fetch, keeping {OUT_CSV.name}")
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

    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:15]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_crisis: {len(rows)} rows | {cb} | "
          f"last7d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
