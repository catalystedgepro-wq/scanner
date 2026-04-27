#!/usr/bin/env python3
"""build_sec_crypto.py — SEC digital-asset / crypto-adoption tape.

5 crypto-disclosure 8-K kinds (public-company balance-sheet
exposure to digital assets):

- bitcoin_treasury — corporate BTC-on-balance-sheet declaration.
  Canonical MSTR playbook. ~75 companies global; US public subset
  ~35 (MARA/RIOT/CLSK/COIN/GME/TSLA etc.). Correlates +0.8 with
  BTC/USD spot.
- bitcoin_holdings — generic BTC holdings (often as payment for
  services or mining reward retention).
- digital_asset — broad bucket, includes token inventory, NFT,
  crypto receivables. Accounting treatment shifted 2024 with ASU
  2023-08 (fair-value election).
- stablecoin — USDC/USDT/PYUSD integration. Signals crypto
  payments rail adoption (V/MA competitor thesis).
- crypto_holdings — non-bitcoin crypto on balance sheet.

Economic readthrough:
- Bitcoin treasury + bitcoin holdings concurrent -> MSTR analog
  bullish (MARA/RIOT/CLSK/BITF/HUT8 relative strength).
- Stablecoin adoption -> COIN/HOOD fee-stream bullish + PYPL
  thesis.
- Digital asset disclosures = proxy for on-balance-sheet crypto
  capacity (policy = GENIUS Act / FIT21 tailwind).

Source: efts.sec.gov/LATEST/search-index
Output: sec_crypto.csv

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
OUT_CSV = ROOT / "sec_crypto.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "bitcoin_treasury": '"bitcoin treasury"',
    "bitcoin_holdings": '"bitcoin holdings"',
    "digital_asset": '"digital asset"',
    "stablecoin": '"stablecoin"',
    "crypto_holdings": '"crypto holdings"',
}

LIMITS = {
    "bitcoin_treasury": 20,
    "bitcoin_holdings": 20,
    "digital_asset": 170,
    "stablecoin": 40,
    "crypto_holdings": 15,
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
        print(f"sec_crypto: {kind} fetch failed: {e}")
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
            print(f"sec_crypto: no fetch, keeping {OUT_CSV.name}")
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
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:15]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_crypto: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
