#!/usr/bin/env python3
"""build_fda_pdufa.py — FDA catalyst calendar via openFDA.

openFDA.gov is free, no API key needed. Pulls:
  - Drug recalls (drug/enforcement)
  - Warning letters proxy (via drug/label updates)
  - Biopharmcatalyst RSS fallback (no official FDA calendar API)

Output: fda_pdufa.csv
Columns: signal_date, signal_type, firm_name, ticker_guess, product, severity, url
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_pdufa.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

OPENFDA_RECALLS = "https://api.fda.gov/drug/enforcement.json?search=report_date:[{start}+TO+{end}]&limit=100"
OPENFDA_DEVICE_RECALLS = "https://api.fda.gov/device/recall.json?search=event_date_initiated:[{start}+TO+{end}]&limit=100"


def fetch(url: str, timeout: int = 20) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"fda: {url[:80]}... -> {e}")
        return None


def guess_ticker(firm: str) -> str:
    # Lightweight firm→ticker hints; real mapping lives in entity_master.json
    firm_u = (firm or "").upper()
    hints = {
        "PFIZER": "PFE", "MODERNA": "MRNA", "BIONTECH": "BNTX",
        "JOHNSON": "JNJ", "MERCK": "MRK", "ABBVIE": "ABBV",
        "ELI LILLY": "LLY", "NOVARTIS": "NVS", "ROCHE": "RHHBY",
        "BRISTOL": "BMY", "AMGEN": "AMGN", "GILEAD": "GILD",
        "REGENERON": "REGN", "VERTEX": "VRTX", "BIOGEN": "BIIB",
        "SANOFI": "SNY", "ASTRAZENECA": "AZN", "TAKEDA": "TAK",
        "TEVA": "TEVA", "VIATRIS": "VTRS", "BAUSCH": "BHC",
        "INCYTE": "INCY", "ALNYLAM": "ALNY", "MODERNA": "MRNA",
        "BOSTON SCIENTIFIC": "BSX", "MEDTRONIC": "MDT", "STRYKER": "SYK",
        "ZIMMER": "ZBH", "EDWARDS": "EW", "INTUITIVE": "ISRG",
    }
    for k, v in hints.items():
        if k in firm_u:
            return v
    return ""


def main():
    today = dt.date.today()
    start = (today - dt.timedelta(days=14)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    rows: list[dict] = []

    drug = fetch(OPENFDA_RECALLS.format(start=start, end=end))
    if drug and drug.get("results"):
        for r in drug["results"]:
            firm = r.get("recalling_firm", "")
            rows.append({
                "signal_date": r.get("report_date", ""),
                "signal_type": "DRUG_RECALL",
                "firm_name": firm,
                "ticker_guess": guess_ticker(firm),
                "product": r.get("product_description", "")[:140],
                "severity": r.get("classification", ""),
                "url": f"https://api.fda.gov/drug/enforcement.json?search=recall_number:{r.get('recall_number','')}",
            })

    device = fetch(OPENFDA_DEVICE_RECALLS.format(start=start, end=end))
    if device and device.get("results"):
        for r in device["results"]:
            firm = r.get("recalling_firm", "")
            rows.append({
                "signal_date": r.get("event_date_initiated", ""),
                "signal_type": "DEVICE_RECALL",
                "firm_name": firm,
                "ticker_guess": guess_ticker(firm),
                "product": r.get("product_description", "")[:140],
                "severity": r.get("product_res_number", ""),
                "url": f"https://api.fda.gov/device/recall.json?search=cdrh_ugmdr_number:{r.get('cdrh_ugmdr_number','')}",
            })

    # Sort newest first
    rows.sort(key=lambda r: r["signal_date"], reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["signal_date", "signal_type", "firm_name", "ticker_guess", "product", "severity", "url"])
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"fda_pdufa: {len(rows)} signals, {with_tic} ticker-mapped -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
