#!/usr/bin/env python3
"""build_sec_splits.py — Stock-split catalysts via SEC EDGAR full-text.

Tape:
- "reverse stock split" in 8-K usually = compliance / Nasdaq-delist
  avoidance / dilution → bearish retail dump risk
- "forward stock split" or "stock split" (not reverse) = confidence /
  retail-attention attractor → TSLA 3:1, NVDA 10:1, AVGO 10:1, CMG 50:1

Both forms are high-momentum catalysts; tagging them cleanly lets the
scanner score forward splits as bullish, reverse splits as squeeze /
penny universe churn.

Source: efts.sec.gov/LATEST/search-index
Output: sec_splits.csv

Lookback: 45 days.
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
OUT_CSV = ROOT / "sec_splits.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://efts.sec.gov/LATEST/search-index"
LOOKBACK_DAYS = 45

QUERIES = {
    "forward": '"stock split" -"reverse stock split"',
    "reverse": '"reverse stock split"',
}

NAME_RE = re.compile(
    r"^(?P<name>.+?)\s+\((?P<tickers>[A-Z0-9,\s\.\-]+?)\)\s+"
    r"\(CIK\s+(?P<cik>\d+)\)"
)


def _fetch(query: str, startdt: str, enddt: str) -> list[dict]:
    params = {
        "q": query,
        "forms": "8-K",
        "dateRange": "custom",
        "startdt": startdt,
        "enddt": enddt,
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"sec_splits: {query[:20]}: {e}")
        return []
    hits = d.get("hits", {}).get("hits", [])
    return hits if isinstance(hits, list) else []


def _parse_name(raw: str) -> tuple[str, str, str]:
    m = NAME_RE.match(raw.strip())
    if not m:
        return raw.strip(), "", ""
    name = m.group("name").strip()
    tickers_str = m.group("tickers")
    cik = m.group("cik")
    tick_list = [t.strip() for t in tickers_str.split(",") if t.strip()]
    primary = tick_list[0] if tick_list else ""
    return name, primary, cik


def main() -> None:
    today = dt.date.today()
    startdt = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    enddt = today.isoformat()

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for kind, query in QUERIES.items():
        hits = _fetch(query, startdt, enddt)
        for h in hits:
            src = h.get("_source", {}) if isinstance(h, dict) else {}
            if not isinstance(src, dict):
                continue
            display = src.get("display_names") or []
            if not display:
                continue
            display_str = display[0] if isinstance(display, list) else ""
            name, ticker, cik = _parse_name(display_str)
            file_date = src.get("file_date", "")
            period = src.get("period_ending", "")
            key = (ticker or cik, file_date, kind)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "kind": kind,
                "ticker": ticker,
                "cik": cik,
                "company": name[:50],
                "file_date": file_date,
                "period_ending": period,
                "accession_id": (h.get("_id", "") or "").split(":")[0],
                "captured_at": now_iso,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_splits: no fetch, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["file_date"], r["kind"], r["ticker"]),
              reverse=True)

    fieldnames = ["kind", "ticker", "cik", "company", "file_date",
                  "period_ending", "accession_id", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    fwd = sum(1 for r in rows if r["kind"] == "forward")
    rev = sum(1 for r in rows if r["kind"] == "reverse")
    recent = [r for r in rows if r["file_date"]
              >= (today - dt.timedelta(days=7)).isoformat()]
    rtick = " ".join(r["ticker"] for r in recent if r["ticker"])[:120]
    print(f"sec_splits: {len(rows)} splits | fwd={fwd} rev={rev} | "
          f"last7d={len(recent)} [{rtick}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
