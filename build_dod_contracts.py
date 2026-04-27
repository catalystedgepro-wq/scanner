#!/usr/bin/env python3
"""build_dod_contracts.py — Federal contract awards via USASpending.gov.

USASpending.gov is the official government spending REST API (no UA filter, no
throttling issues). Covers ALL federal contracts including DoD, VA, DOE, HHS,
plus grants and other award vehicles. Replaces the defense.gov scrape which is
hard-gated behind Cloudflare.

Output: dod_contracts.csv
Columns: announce_date, firm, ticker_guess, amount_usd, description, branch, url
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "dod_contracts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

DEFENSE_HINTS = {
    "LOCKHEED": "LMT", "RAYTHEON": "RTX", "RTX ": "RTX",
    "GENERAL DYNAMICS": "GD", "NORTHROP": "NOC",
    "BOEING": "BA", "HII ": "HII", "HUNTINGTON INGALLS": "HII",
    "L3HARRIS": "LHX", "LEIDOS": "LDOS", "BAE SYSTEMS": "BAESY",
    "BOOZ ALLEN": "BAH", "SAIC": "SAIC", "CACI": "CACI",
    "MANTECH": "MANT", "KRATOS": "KTOS", "CURTISS-WRIGHT": "CW",
    "TEXTRON": "TXT", "HEICO": "HEI", "HONEYWELL": "HON",
    "PARSONS": "PSN", "V2X": "VVX", "ELBIT": "ESLT",
    "AEROJET": "AJRD", "PALANTIR": "PLTR",
    "AECOM": "ACM", "CAE ": "CAE", "MOOG ": "MOG.A",
    "GENERAL ELECTRIC": "GE", "RTX CORP": "RTX",
    "OSHKOSH": "OSK", "AEROVIRONMENT": "AVAV",
    "MERCURY SYSTEMS": "MRCY", "MAXAR": "MAXR",
    "IRIDIUM": "IRDM", "INTUITIVE MACHINES": "LUNR",
    "REDWIRE": "RDW", "PLANET LABS": "PL", "ROCKET LAB": "RKLB",
    "TRANSDIGM": "TDG", "HEXCEL": "HXL", "WOODWARD": "WWD",
    "TRIUMPH": "TGI", "DUCOMMUN": "DCO", "ASTRONICS": "ATRO",
    "SPIRIT AEROSYSTEMS": "SPR", "EMBRAER": "ERJ",
    "DRS ": "LDOS",  # Leonardo DRS merged with RADA
    "PARSONS CORP": "PSN", "BYRNA": "BYRN", "KBR ": "KBR",
    "IBM ": "IBM", "MICROSOFT": "MSFT", "AMAZON WEB": "AMZN",
    "ORACLE": "ORCL", "SAIC ": "SAIC", "DXC ": "DXC",
    "ACCENTURE": "ACN", "CGI ": "GIB", "PERSPECTA": "LDOS",
}


def fetch(url: str, payload: dict, timeout: int = 25) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"dod: fetch failed: {e}")
        return None


def guess_ticker(firm: str) -> str:
    up = (firm or "").upper()
    for k, v in DEFENSE_HINTS.items():
        if k in up:
            return v
    return ""


def main():
    today = dt.date.today()
    since = (today - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    until = today.strftime("%Y-%m-%d")
    # Contract award categories: A=BPA Call, B=Purchase Order, C=Delivery Order, D=Contract
    payload = {
        "filters": {
            "time_period": [{"start_date": since, "end_date": until}],
            "award_type_codes": ["A", "B", "C", "D"],
            "agencies": [
                {"type": "awarding", "tier": "toptier", "name": "Department of Defense"}
            ],
            "award_amounts": [{"lower_bound": 7_500_000}],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Description",
            "Start Date",
            "End Date",
            "generated_internal_id",
        ],
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
    }
    rows: list[dict] = []
    data = fetch(API, payload)
    if data and data.get("results"):
        for r in data["results"]:
            firm = r.get("Recipient Name") or ""
            amt = r.get("Award Amount") or 0
            sub = r.get("Awarding Sub Agency") or ""
            branch = ""
            up = sub.upper()
            if "ARMY" in up:
                branch = "Army"
            elif "NAVY" in up or "MARINE" in up:
                branch = "Navy"
            elif "AIR FORCE" in up or "SPACE FORCE" in up:
                branch = "Air Force"
            elif "DLA" in up or "LOGISTICS AGENCY" in up:
                branch = "DLA"
            elif "DARPA" in up:
                branch = "DARPA"
            gid = r.get("generated_internal_id") or ""
            rows.append({
                "announce_date": (r.get("Start Date") or until)[:10],
                "firm": firm[:120],
                "ticker_guess": guess_ticker(firm),
                "amount_usd": f"{float(amt):.0f}" if amt else "0",
                "description": (r.get("Description") or "")[:280],
                "branch": branch,
                "url": f"https://www.usaspending.gov/award/{gid}" if gid else "https://www.usaspending.gov/",
            })
    rows.sort(key=lambda r: float(r["amount_usd"] or 0), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["announce_date", "firm", "ticker_guess", "amount_usd", "description", "branch", "url"],
        )
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"dod_contracts: {len(rows)} awards, {with_tic} ticker-mapped -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
