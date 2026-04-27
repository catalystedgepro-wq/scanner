#!/usr/bin/env python3
"""build_treasury_ofac.py — Treasury auctions + OFAC sanctions updates.

Treasury publishes daily auction results (TreasuryDirect JSON) and the
OFAC SDN list (press releases) — both move FX, rates, and individual
tickers exposed to sanctioned jurisdictions.

Output: treasury_ofac.csv
Columns: date, type, detail, ticker_guess, url
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_ofac.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# TreasuryDirect auction results (JSON)
AUCTION = "https://www.treasurydirect.gov/TA_WS/securities/announced?format=json"
# OFAC recent actions RSS
OFAC_RSS = "https://ofac.treasury.gov/system/files/126/ofac.xml"


def fetch_json(url: str, timeout: int = 25) -> list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"treasury: {e}")
        return None


def fetch_text(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"ofac: {e}")
        return None


def main():
    rows: list[dict] = []
    today = dt.date.today()
    # 1) Treasury auctions in last 21 days
    auctions = fetch_json(AUCTION) or []
    if isinstance(auctions, list):
        for a in auctions[:50]:
            try:
                ann = (a.get("announcementDate") or "")[:10]
                if not ann:
                    continue
            except Exception:
                continue
            rows.append({
                "date": ann,
                "type": "TREASURY_AUCTION",
                "detail": f"{a.get('securityTerm','')} {a.get('securityType','')} CUSIP {a.get('cusip','')}",
                "ticker_guess": "",
                "url": "https://www.treasurydirect.gov/auctions/upcoming/",
            })
    # 2) OFAC SDN updates (rarely structured; parse title/link)
    xml = fetch_text(OFAC_RSS) or ""
    if xml:
        for m in re.finditer(r"<item>(.*?)</item>", xml, re.DOTALL | re.I):
            block = m.group(1)
            tm = re.search(r"<title>(.*?)</title>", block, re.DOTALL | re.I)
            lm = re.search(r"<link>(.*?)</link>", block, re.DOTALL | re.I)
            pm = re.search(r"<pubDate>(.*?)</pubDate>", block, re.DOTALL | re.I)
            title = re.sub(r"<[^>]+>", " ", tm.group(1)).strip() if tm else ""
            link = (lm.group(1).strip() if lm else "")
            pub = (pm.group(1).strip() if pm else "")[:16]
            rows.append({
                "date": pub,
                "type": "OFAC_ACTION",
                "detail": title[:240],
                "ticker_guess": "",
                "url": link,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["date", "type", "detail", "ticker_guess", "url"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"treasury_ofac: {len(rows)} entries -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
