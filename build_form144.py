#!/usr/bin/env python3
"""build_form144.py — SEC Form 144 planned insider sales (advance notice).

Form 144 is filed by affiliates / insiders BEFORE executing a planned
sale of restricted stock under Rule 144. Unlike Form 4 (actual trade
reports within 2 business days), Form 144 is advance notice — giving
up to 90 days of forward-looking visibility into insider-distribution
pressure.

Why this matters:
- Form 4 is a lagging indicator (sale already happened); Form 144 is
  leading (sale is *planned*, may or may not execute).
- Large Form 144 clusters near earnings = distribution-risk setup.
- Single large Form 144 after a price pop = "selling into strength"
  by executives who know the forward picture.
- 10b5-1 programmatic Form 144s (scheduled) are noise — cluster analysis
  + price context separates signal from noise.

Signal construction:
- Filings per ticker in rolling 30 days: >5 = active distribution
- Concentration: single filer / multiple days = directional conviction
- Co-occurrence with Form 4 executed sales (build_insider_tracker.py)
  = "matched pair" confirmation

Trade uses:
- Pre-earnings Form 144 cluster: fade any earnings pop (insiders know
  something about forward revenue).
- Post-news Form 144 surge: sellers taking advantage of retail
  enthusiasm — short once momentum rolls over.
- Biotech + Form 144 = frequent (compensation-driven) so ignore
  baseline; look only for clusters > 3x 90-day median.

Source: SEC EDGAR EFTS full-text search (same endpoint family as
`build_going_concern.py` — `efts.sec.gov/LATEST/search-index`). Free,
no key, but must send descriptive User-Agent per EDGAR policy.

Output: form144_filings.csv
Columns: accession, filed_date, ticker, issuer, cik, primary_doc,
captured_at
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
OUT_CSV = ROOT / "form144_filings.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://efts.sec.gov/LATEST/search-index"

DAYS_BACK = 7
PAGE_SIZE = 100  # EFTS supports size=100
MAX_PAGES = 12   # up to 1200 filings per run

TICKER_RE = re.compile(r"\(([A-Z]{1,5}(?:-[A-Z]{1,3})?)\)")


def fetch_page(start_dt: str, end_dt: str, from_: int) -> dict:
    params = {
        "q": "",
        "dateRange": "custom",
        "startdt": start_dt,
        "enddt": end_dt,
        "forms": "144",
        "from": str(from_),
        "size": str(PAGE_SIZE),
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"form144: page from={from_} -> {e}")
        return {}


def main() -> None:
    today = dt.date.today()
    start = (today - dt.timedelta(days=DAYS_BACK)).isoformat()
    end = today.isoformat()

    rows: list[dict] = []
    seen: set[str] = set()

    import time
    for page in range(MAX_PAGES):
        from_ = page * PAGE_SIZE
        data = fetch_page(start, end, from_)
        hits = data.get("hits", {}).get("hits") or []
        if not hits:
            break
        if page > 0:
            time.sleep(0.2)  # SEC fair-use pacing

        for h in hits:
            acc = h.get("_id", "")
            src = h.get("_source", {})
            names = src.get("display_names") or []
            disp = names[0] if names else ""

            # Ticker: "Company Name (TICKER[,TICKER2]) (CIK 000...)"
            tickers = TICKER_RE.findall(disp)
            ticker = tickers[0] if tickers else ""

            # Issuer name (strip ticker/CIK tail)
            issuer = re.sub(
                r"\s*\([A-Z][A-Z0-9,\s\-]*\)\s*\(CIK .*$",
                "",
                disp,
            ).strip()

            # CIK
            cik_m = re.search(r"CIK\s+(\d+)", disp)
            cik = cik_m.group(1) if cik_m else ""

            # Filing URL — EFTS gives acc:primary_doc form
            if ":" in acc:
                acc_no, doc = acc.split(":", 1)
                acc_clean = acc_no.replace("-", "")
                primary_doc = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik}/{acc_clean}/{doc}"
                )
            else:
                primary_doc = ""
                acc_no = acc

            if acc_no in seen:
                continue
            seen.add(acc_no)

            filed = src.get("file_date") or ""

            rows.append({
                "accession": acc_no,
                "filed_date": filed,
                "ticker": ticker,
                "issuer": issuer[:120],
                "cik": cik,
                "primary_doc": primary_doc,
            })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"form144: empty response, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: r["filed_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["accession", "filed_date", "ticker", "issuer",
                        "cik", "primary_doc", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Cluster summary — top 5 tickers by 30-day filing count
    from collections import Counter
    c = Counter(r["ticker"] for r in rows if r["ticker"])
    tickered = sum(1 for r in rows if r["ticker"])
    top = ", ".join(f"{t}×{n}" for t, n in c.most_common(5))

    print(f"form144: {len(rows)} filings over {DAYS_BACK}d | "
          f"{tickered} tickered | top clusters: {top} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
