#!/usr/bin/env python3
"""build_cfpb_complaints.py — CFPB consumer complaint intensity.

Consumer Financial Protection Bureau maintains a public database of
14M+ complaints against banks, credit bureaus, fintechs, and debt
collectors. Uses the ElasticSearch company-aggregation so we get
TRUE 30-day population counts (not the 500-hit sample that the
default search returns).

Signal:
- Credit bureau spikes → prelude to CFPB enforcement / FTC action
  (TRU, EFX historical -5% to -12% on enforcement).
- Bank complaint acceleration → regulatory fine risk (WFC 2018
  fake-accounts: complaints 2× baseline → $2.1B fines).
- BNPL / fintech spikes (Block, Affirm, SoFi) → regulatory
  scrutiny risk; sector has broken multiple times historically.

Rolling 30-day vs prior 30-day (60-31 days ago) delta surfaces
inflection points earlier than raw count. Credit bureaus
dominate total volume (~93%); ticker signal lives in the tail
(banks, fintechs, debt collectors).

Source: consumerfinance.gov/data-research/consumer-complaints/
  search/api/v1/?size=0&field=company (no key, no auth).

Output: cfpb_complaints.csv
Columns: company, ticker, cnt_30d, cnt_prev_30d, delta_pct,
         rank_30d, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cfpb_complaints.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = ("https://www.consumerfinance.gov/data-research/"
       "consumer-complaints/search/api/v1/")

# Company substring (lowercase) -> ticker. CFPB submitter names
# are messy; substring match handles legal-entity variations.
TICKER_MAP: dict[str, str] = {
    "transunion": "TRU",
    "experian": "EXPGY",
    "equifax": "EFX",
    "capital one": "COF",
    "wells fargo": "WFC",
    "bank of america": "BAC",
    "jpmorgan": "JPM",
    "citibank": "C",
    "citigroup": "C",
    "synchrony": "SYF",
    "block, inc": "XYZ",
    "pnc bank": "PNC",
    "u.s. bancorp": "USB",
    "u.s. bank": "USB",
    "truist": "TFC",
    "discover": "DFS",
    "american express": "AXP",
    "goldman sachs": "GS",
    "morgan stanley": "MS",
    "charles schwab": "SCHW",
    "ally financial": "ALLY",
    "ally bank": "ALLY",
    "navient": "NAVI",
    "sallie mae": "SLM",
    "nelnet": "NNI",
    "rocket companies": "RKT",
    "rocket mortgage": "RKT",
    "quicken loans": "RKT",
    "mr. cooper": "COOP",
    "pennymac": "PFSI",
    "lendingclub": "LC",
    "sofi": "SOFI",
    "paypal": "PYPL",
    "robinhood": "HOOD",
    "coinbase": "COIN",
    "affirm": "AFRM",
    "upstart": "UPST",
    "onemain": "OMF",
    "credit acceptance": "CACC",
    "fifth third": "FITB",
    "regions bank": "RF",
    "keybank": "KEY",
    "huntington": "HBAN",
    "comerica": "CMA",
    "zions": "ZION",
    "m&t bank": "MTB",
    "citizens bank": "CFG",
    "first citizens": "FCNCA",
    "santander consumer": "SC",
    "santander": "SAN",
    "hsbc": "HSBC",
    "td bank": "TD",
    "bmo": "BMO",
    "scotiabank": "BNS",
    "barclays": "BCS",
    "deutsche bank": "DB",
    "mastercard": "MA",
    "visa inc": "V",
    "fiserv": "FI",
    "fidelity national": "FIS",
    "global payments": "GPN",
    "western union": "WU",
    "carvana": "CVNA",
    "prospect capital": "PSEC",
    "world acceptance": "WRLD",
}


def _map_ticker(name: str) -> str:
    n = name.lower()
    for key, t in TICKER_MAP.items():
        if key in n:
            return t
    return ""


def fetch_company_counts(start: str, end: str) -> list[dict]:
    qs = urllib.parse.urlencode({
        "size": "0",
        "field": "company",
        "date_received_min": start,
        "date_received_max": end,
        "no_aggs": "false",
    })
    url = f"{API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"cfpb_complaints: {start}..{end}: {e}")
        return []
    agg = body.get("aggregations", {}).get("company", {})
    inner = agg.get("company", {})
    return inner.get("buckets", []) or []


def main() -> None:
    today = dt.date.today()
    d30 = (today - dt.timedelta(days=30)).isoformat()
    d60 = (today - dt.timedelta(days=60)).isoformat()
    d31 = (today - dt.timedelta(days=31)).isoformat()
    end = today.isoformat()

    cur = fetch_company_counts(d30, end)
    prev = fetch_company_counts(d60, d31)

    if not cur and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"cfpb_complaints: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    prev_by_co = {b["key"]: b["doc_count"] for b in prev}

    rows: list[dict] = []
    for i, b in enumerate(cur, start=1):
        co = b["key"]
        c30 = b["doc_count"]
        c_prev = prev_by_co.get(co, 0)
        if c_prev > 0:
            delta_s = f"{((c30 - c_prev) / c_prev * 100):.2f}"
        elif c30 > 0:
            delta_s = "new"
        else:
            delta_s = ""
        rows.append({
            "company": co[:80],
            "ticker": _map_ticker(co),
            "cnt_30d": c30,
            "cnt_prev_30d": c_prev,
            "delta_pct": delta_s,
            "rank_30d": i,
        })

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["company", "ticker", "cnt_30d", "cnt_prev_30d",
                  "delta_pct", "rank_30d", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    tickered = [r for r in rows if r["ticker"]]
    movers = [r for r in tickered
              if r["delta_pct"] not in ("", "new")
              and r["cnt_30d"] >= 50]
    movers.sort(key=lambda r: -abs(float(r["delta_pct"])))
    top_t = ", ".join(
        f"{r['ticker']}({r['cnt_30d']}/{r['delta_pct']}%)"
        for r in movers[:6])
    print(f"cfpb_complaints: {len(rows)} cos 30d | "
          f"{len(tickered)} tickered | top movers: {top_t} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
