#!/usr/bin/env python3
"""build_nhtsa_recalls.py — NHTSA auto recalls (rolling).

Auto recalls = direct hit on make/model. Ford $1B+ recall history
gapped F down 5-8%. Tesla Autopilot recalls → TSLA. GM ignition →
GM multi-year drag. Supplier recalls hit OEM cascade. Large airbag
recall → Takata-style supplier bankruptcy.

Trading-relevant make → ticker map:
- Ford -> F
- Tesla -> TSLA
- General Motors, Chevrolet, Buick, GMC, Cadillac -> GM
- Stellantis, Jeep, Ram, Chrysler, Dodge -> STLA
- BMW -> BMWYY (ADR)
- Mercedes-Benz -> MBGYY
- Volkswagen, Audi, Porsche -> VWAGY / POAHY
- Hyundai, Kia, Genesis -> HYMTF
- Honda, Acura -> HMC
- Toyota, Lexus -> TM
- Nissan, Infiniti -> NSANY
- Subaru -> FUJHY
- Mazda -> MZDAY
- Volvo -> VLVLY
- Rivian -> RIVN
- Lucid -> LCID
- Polestar -> PSNY

NHTSA API requires make+model+modelYear. Use 2-step fetch:
1. /products/vehicle/models?modelYear=Y&make=X&issueType=r  (models with recalls)
2. /recalls/recallsByVehicle?make=X&model=M&modelYear=Y       (recall detail)

Source: api.nhtsa.gov (public, no key).
Output: nhtsa_recalls.csv
Columns: nhtsa_id, make, model, year, ticker, component, subject,
         report_date, recall_description, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nhtsa_recalls.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

MAKE_TICKER: dict[str, str] = {
    "FORD": "F",
    "LINCOLN": "F",
    "TESLA": "TSLA",
    "GENERAL MOTORS": "GM",
    "CHEVROLET": "GM",
    "BUICK": "GM",
    "GMC": "GM",
    "CADILLAC": "GM",
    "STELLANTIS": "STLA",
    "JEEP": "STLA",
    "RAM": "STLA",
    "CHRYSLER": "STLA",
    "DODGE": "STLA",
    "FIAT": "STLA",
    "ALFA ROMEO": "STLA",
    "TOYOTA": "TM",
    "LEXUS": "TM",
    "HONDA": "HMC",
    "ACURA": "HMC",
    "NISSAN": "NSANY",
    "INFINITI": "NSANY",
    "HYUNDAI": "HYMTF",
    "KIA": "HYMTF",
    "GENESIS": "HYMTF",
    "SUBARU": "FUJHY",
    "MAZDA": "MZDAY",
    "VOLVO": "VLVLY",
    "VOLKSWAGEN": "VWAGY",
    "AUDI": "VWAGY",
    "PORSCHE": "POAHY",
    "BMW": "BMWYY",
    "MINI": "BMWYY",
    "MERCEDES-BENZ": "MBGYY",
    "RIVIAN": "RIVN",
    "LUCID": "LCID",
    "POLESTAR": "PSNY",
}

MAKES = list(MAKE_TICKER.keys())


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return {"_error": str(e)}


def models_with_recalls(make: str, year: int) -> list[str]:
    url = (f"https://api.nhtsa.gov/products/vehicle/models"
           f"?modelYear={year}&make={urllib.parse.quote(make)}"
           f"&issueType=r")
    data = _get(url)
    results = data.get("results") or []
    models: list[str] = []
    seen: set[str] = set()
    for r in results:
        m = (r.get("model") or "").strip()
        if m and m not in seen:
            seen.add(m)
            models.append(m)
    return models


def fetch_recalls(make: str, model: str, year: int) -> list[dict]:
    url = (f"https://api.nhtsa.gov/recalls/recallsByVehicle"
           f"?make={urllib.parse.quote(make)}"
           f"&model={urllib.parse.quote(model)}"
           f"&modelYear={year}")
    data = _get(url)
    return data.get("results") or []


def main() -> None:
    current_year = dt.date.today().year
    years = [current_year, current_year - 1]

    rows: list[dict] = []
    seen: set[str] = set()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    for make in MAKES:
        ticker = MAKE_TICKER[make]
        for yr in years:
            models = models_with_recalls(make, yr)
            time.sleep(0.15)
            # Cap per-make-year to avoid 200+ requests per make.
            for mdl in models[:12]:
                for rec in fetch_recalls(make, mdl, yr):
                    key = rec.get("NHTSACampaignNumber", "") or ""
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "nhtsa_id": key,
                        "make": rec.get("Make", make),
                        "model": rec.get("Model", mdl),
                        "year": rec.get("ModelYear", str(yr)),
                        "ticker": ticker,
                        "component": (rec.get("Component") or "")[:80],
                        "subject": (rec.get("Summary") or "")[:140],
                        "report_date": rec.get("ReportReceivedDate", ""),
                        "recall_description": (
                            rec.get("Consequence") or "")[:200],
                        "captured_at": now,
                    })
                time.sleep(0.12)

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"nhtsa: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    def _parse_date(s: str) -> str:
        # ReportReceivedDate format: dd/mm/yyyy
        try:
            d = dt.datetime.strptime(s, "%d/%m/%Y").date()
            return d.isoformat()
        except (ValueError, TypeError):
            return "0000-00-00"

    rows.sort(key=lambda r: _parse_date(r["report_date"]), reverse=True)
    rows = rows[:600]

    fieldnames = ["nhtsa_id", "make", "model", "year", "ticker",
                  "component", "subject", "report_date",
                  "recall_description", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0] if rows else {}
    by_ticker: dict[str, int] = {}
    for r in rows:
        by_ticker[r["ticker"]] = by_ticker.get(r["ticker"], 0) + 1
    top = sorted(by_ticker.items(), key=lambda x: x[1], reverse=True)[:3]
    top_s = " | ".join(f"{t}={n}" for t, n in top)
    print(f"nhtsa_recalls: {len(rows)} rows | latest "
          f"{latest.get('report_date','?')} {latest.get('make','?')} "
          f"{latest.get('model','?')} | top tickers: {top_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
