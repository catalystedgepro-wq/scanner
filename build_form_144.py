#!/usr/bin/env python3
"""build_form_144.py — EDGAR Form 144 insider sell-intent feed.

Form 144 = notice of PROPOSED insider sale (fires BEFORE the Form 4 showing actual sale).
This is the earliest signal of an insider unloading.

Output: form_144.csv
Columns: ticker, cik, filer_name, filed_date, shares_to_sell, approx_value,
         market_cap_pct, filing_url
"""
from __future__ import annotations
import csv
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "form_144.csv"
CACHE = ROOT / ".form_144_cache.json"
TICKERS_JSON = ROOT / "ticker_cik_map.json"

UA = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 (opensource@example.com)")
FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=144&company=&dateb=&owner=include&count=100&output=atom"

ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
LINK_RE = re.compile(r'<link[^>]+href="([^"]+)"', re.DOTALL)
UPDATED_RE = re.compile(r"<updated>(.*?)</updated>", re.DOTALL)
SUMMARY_RE = re.compile(r"<summary[^>]*>(.*?)</summary>", re.DOTALL)


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/atom+xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def load_cik_map() -> dict:
    if TICKERS_JSON.exists():
        try:
            return json.loads(TICKERS_JSON.read_text())
        except Exception:
            pass
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = json.loads(r.read().decode("utf-8"))
        m = {}
        for _, v in raw.items():
            cik = str(v["cik_str"]).zfill(10)
            m[cik] = (v["ticker"].upper(), v["title"])
        TICKERS_JSON.write_text(json.dumps(m))
        return m
    except Exception as e:
        print(f"form_144: cik map fetch failed: {e}")
        return {}


def parse_entry(entry: str, cik_map: dict) -> dict | None:
    title_m = TITLE_RE.search(entry)
    link_m = LINK_RE.search(entry)
    upd_m = UPDATED_RE.search(entry)
    summ_m = SUMMARY_RE.search(entry)
    if not (title_m and link_m):
        return None
    title = title_m.group(1).strip()
    link = link_m.group(1).strip()
    # Title format: "144 - Company Name (0001921865) (Subject)"
    # Only keep the Subject-side (issuer) — Reporting side is the insider
    if "(Reporting)" in title:
        return None
    t_match = re.match(r"^144\s*-\s*(.*?)\s*\((\d{10})\)\s*\((Subject|Reporting|Filer)\)", title)
    if t_match:
        filer = t_match.group(1).strip()
        cik = t_match.group(2)
    else:
        filer = re.sub(r"^144\s*-\s*", "", title).split(" (")[0]
        cik_m2 = re.search(r"/data/(\d+)/", link)
        cik = cik_m2.group(1).zfill(10) if cik_m2 else ""
    tic_info = cik_map.get(cik, ("", filer))
    tic = tic_info[0] if isinstance(tic_info, (list, tuple)) else ""
    filed = (upd_m.group(1).strip()[:10] if upd_m else "")
    summary = (summ_m.group(1) if summ_m else "").strip()
    return {
        "ticker": tic,
        "cik": cik,
        "filer_name": filer[:120],
        "filed_date": filed,
        "summary": re.sub(r"<[^>]+>", " ", summary)[:200],
        "filing_url": link,
    }


def main():
    cik_map = load_cik_map()
    try:
        body = fetch(FEED)
    except Exception as e:
        print(f"form_144: feed fetch failed: {e}")
        return
    rows = []
    for entry in ENTRY_RE.findall(body):
        r = parse_entry(entry, cik_map)
        if r:
            rows.append(r)
    # Dedupe by (cik, filing_url)
    seen = set()
    deduped = []
    for r in rows:
        key = (r["cik"], r["filing_url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "cik", "filer_name", "filed_date", "summary", "filing_url"])
        w.writeheader()
        w.writerows(deduped)
    with_tic = sum(1 for r in deduped if r["ticker"])
    print(f"form_144: {len(deduped)} filings, {with_tic} ticker-mapped -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
