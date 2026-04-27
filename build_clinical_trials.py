#!/usr/bin/env python3
"""build_clinical_trials.py — ClinicalTrials.gov recent-update feed.

NIH ClinicalTrials.gov v2 API is free, no key. Pulls trials with status
changes in the last 7 days, maps sponsors to tickers.

Output: clinical_trials.csv
Columns: nct_id, sponsor, ticker_guess, condition, phase, status, last_update, title, url
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "clinical_trials.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

API = "https://clinicaltrials.gov/api/v2/studies"

SPONSOR_HINTS = {
    "PFIZER": "PFE", "MODERNA": "MRNA", "BIONTECH": "BNTX",
    "JOHNSON & JOHNSON": "JNJ", "JANSSEN": "JNJ",
    "MERCK": "MRK", "ABBVIE": "ABBV", "ELI LILLY": "LLY",
    "NOVARTIS": "NVS", "ROCHE": "RHHBY", "GENENTECH": "RHHBY",
    "BRISTOL": "BMY", "BMS ": "BMY", "AMGEN": "AMGN",
    "GILEAD": "GILD", "REGENERON": "REGN", "VERTEX": "VRTX",
    "BIOGEN": "BIIB", "SANOFI": "SNY", "ASTRAZENECA": "AZN",
    "TAKEDA": "TAK", "TEVA": "TEVA", "ALNYLAM": "ALNY",
    "INCYTE": "INCY", "BEIGENE": "BGNE", "NEUROCRINE": "NBIX",
    "EXELIXIS": "EXEL", "JAZZ": "JAZZ", "IONIS": "IONS",
    "ALKERMES": "ALKS", "BLUEBIRD": "BLUE", "SAREPTA": "SRPT",
    "ACADIA": "ACAD", "INTERCEPT": "ICPT", "UNITED THERAPEUTICS": "UTHR",
    "NOVAVAX": "NVAX", "CATALENT": "CTLT", "IQVIA": "IQV",
    "ICON ": "ICLR", "SYNEOS": "SYNH", "CRISPR": "CRSP",
    "EDITAS": "EDIT", "BEAM": "BEAM", "INTELLIA": "NTLA",
    "GINKGO": "DNA", "SAGE": "SAGE", "ENOVIS": "ENOV",
    "BIOMARIN": "BMRN", "UNITED NEUROSCIENCE": "", "IVERIC": "ISEE",
}


def fetch(url: str, timeout: int = 25) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"clinical_trials: {url[:80]}... -> {e}")
        return None


def guess_ticker(sponsor: str) -> str:
    up = (sponsor or "").upper()
    for k, v in SPONSOR_HINTS.items():
        if k in up:
            return v
    return ""


def main():
    today = dt.date.today()
    since = (today - dt.timedelta(days=10)).strftime("%Y-%m-%d")
    params = {
        "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{since},{today.strftime('%Y-%m-%d')}]",
        "fields": "NCTId,BriefTitle,Condition,Phase,OverallStatus,LeadSponsorName,LastUpdatePostDate",
        "pageSize": "200",
        "countTotal": "true",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    rows = []
    pages = 0
    while url and pages < 5:
        data = fetch(url)
        if not data:
            break
        for study in data.get("studies", []):
            ps = study.get("protocolSection", {})
            ident = ps.get("identificationModule", {})
            status = ps.get("statusModule", {})
            sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
            cond = "; ".join(ps.get("conditionsModule", {}).get("conditions", []) or [])[:140]
            phases = "; ".join(ps.get("designModule", {}).get("phases", []) or [])
            nct = ident.get("nctId", "")
            rows.append({
                "nct_id": nct,
                "sponsor": sponsor[:120],
                "ticker_guess": guess_ticker(sponsor),
                "condition": cond,
                "phase": phases,
                "status": status.get("overallStatus", ""),
                "last_update": status.get("lastUpdatePostDateStruct", {}).get("date", ""),
                "title": ident.get("briefTitle", "")[:200],
                "url": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
            })
        tok = data.get("nextPageToken")
        if not tok:
            break
        url = f"{API}?{urllib.parse.urlencode(params)}&pageToken={tok}"
        pages += 1
    rows.sort(key=lambda r: r["last_update"], reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["nct_id", "sponsor", "ticker_guess", "condition", "phase", "status", "last_update", "title", "url"])
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"clinical_trials: {len(rows)} trials, {with_tic} ticker-mapped -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
