#!/usr/bin/env python3
"""build_sedar_canada.py — SEDAR+ Canadian filings.

SEDAR+ is Canada's counterpart to EDGAR. Canadian-listed but US-traded
stocks (SHOP, CP, CNQ, SU, TECK, weed stocks, miners) file here first.
SEDAR+ has a public search endpoint at https://www.sedarplus.ca.

Output: sedar_canada.csv
Columns: filed_date, company, ticker_guess, filing_type, url
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sedar_canada.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# SEDAR+ public CSV feed — today's filings
URL = "https://www.sedarplus.ca/csa-party/service/todaysPublicFilingsExport.csv"

CAN_HINTS = {
    "SHOPIFY": "SHOP", "CANADIAN PACIFIC": "CP", "CANADIAN NATURAL RESOURCES": "CNQ",
    "SUNCOR ENERGY": "SU", "ENBRIDGE": "ENB", "TC ENERGY": "TRP",
    "BARRICK GOLD": "GOLD", "BARRICK MINING": "GOLD", "KINROSS": "KGC",
    "FRANCO-NEVADA": "FNV", "WHEATON PRECIOUS": "WPM",
    "TECK RESOURCES": "TECK", "FIRST QUANTUM": "FQVLF",
    "BANK OF MONTREAL": "BMO", "TORONTO-DOMINION": "TD",
    "ROYAL BANK OF CANADA": "RY", "BANK OF NOVA SCOTIA": "BNS",
    "CIBC": "CM", "MANULIFE": "MFC", "SUN LIFE": "SLF",
    "CANOPY GROWTH": "CGC", "AURORA CANNABIS": "ACB",
    "CRONOS GROUP": "CRON", "TILRAY": "TLRY", "HEXO": "HEXO",
    "BROOKFIELD": "BN", "MAGNA INTERNATIONAL": "MGA",
    "OPEN TEXT": "OTEX", "CONSTELLATION SOFTWARE": "CSU.TO",
    "LIGHTSPEED": "LSPD", "NUVEI": "NVEI", "THOMSON REUTERS": "TRI",
    "WASTE CONNECTIONS": "WCN", "RESTAURANT BRANDS": "QSR",
    "DOLLARAMA": "DOL.TO", "TFI INTERNATIONAL": "TFII",
    "KINAXIS": "KXS.TO", "BLACKBERRY": "BB",
    "BAUSCH HEALTH": "BHC", "FAIRFAX FINANCIAL": "FFH.TO",
    "NORTHLAND POWER": "NPI.TO", "ALGONQUIN POWER": "AQN",
}


def fetch(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/csv,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.sedarplus.ca/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"sedar: {e}")
        return None


def guess(name: str) -> str:
    up = (name or "").upper()
    for k, v in CAN_HINTS.items():
        if k in up:
            return v
    return ""


def looks_like_html(body: str) -> bool:
    head = body.lstrip()[:400].lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        return True
    # SEDAR+ currently serves "SEDAR+ Maintenance Page" during downtime.
    return "maintenance page" in head or "<title>" in head[:200]


def main():
    today = dt.date.today().strftime("%Y-%m-%d")
    txt = fetch(URL) or ""
    if txt and looks_like_html(txt):
        # SEDAR+ maintenance mode returns an HTML page where the CSV should be.
        # Preserve any existing CSV rather than overwriting with garbage rows.
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 80:
            print(f"sedar_canada: endpoint in maintenance mode, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
            return
        txt = ""  # No prior CSV — write an empty shell below.
    rows: list[dict] = []
    if txt:
        # File is CSV with header row
        reader = csv.reader(txt.splitlines())
        header = next(reader, None) or []
        idx = {h.strip().lower(): i for i, h in enumerate(header)}
        # Common columns: Filing Date, Document Type, Party Name, Filing Number
        for cells in reader:
            if len(cells) < 3:
                continue
            company = cells[idx.get("party name", 2)] if idx.get("party name") is not None else cells[2]
            ftype = cells[idx.get("document type", 1)] if idx.get("document type") is not None else ""
            filed = cells[idx.get("filing date", 0)] if idx.get("filing date") is not None else today
            rows.append({
                "filed_date": filed,
                "company": company[:120],
                "ticker_guess": guess(company),
                "filing_type": ftype[:80],
                "url": "https://www.sedarplus.ca/",
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["filed_date", "company", "ticker_guess", "filing_type", "url"]
        )
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"sedar_canada: {len(rows)} filings ({with_tic} ticker-mapped) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
