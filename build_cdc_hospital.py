#!/usr/bin/env python3
"""build_cdc_hospital.py — CDC weekly hospital admissions (COVID + flu + RSV).

Hospital admission surges drive hospital-operator trades (HCA UHS THC
CYH) and vaccine/antiviral plays (MRNA PFE GILD BNTX NVAX). State-
level breakdown lets scanner map local outbreaks to regional REIT and
service plays.

Instruments affected:
- Flu surge: MRNA PFE BNTX NVAX vaccine makers; GILD Tamiflu Roche
- COVID wave: MRNA PFE BNTX; remdesivir GILD; PPE KMB WM CVS
- RSV: AZN MRK BNTX NVAX; nasal-spray AZTS

Source: data.cdc.gov Socrata resource aemt-mg7g (weekly by state).
NOTE: Data reporting paused post-PHE in 2024-10. Kept for YoY and
backtest. Will re-source to NHSN replacement when CDC publishes new API.

Output: cdc_hospital.csv
Columns: week_end, state, covid_adult, covid_pedi, flu_admit,
         flu_icu, rsv_admit
"""
from __future__ import annotations
import csv
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cdc_hospital.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = (
    "https://data.cdc.gov/resource/aemt-mg7g.json"
    "?$limit=4000&$order=week_end_date%20DESC"
)


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"cdc_hospital: {e}")
        return []


def to_int(s: str) -> int:
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def main() -> None:
    raw = fetch()
    rows: list[dict] = []
    for it in raw:
        week = (it.get("week_end_date") or "")[:10]
        state = it.get("jurisdiction", "")
        if not week or not state:
            continue
        covid_adult = to_int(it.get("total_adult_patients_covid", "0")) \
            or to_int(it.get("num_hospitals_admissions_all_covid_confirmed", "0"))
        covid_pedi = to_int(it.get("total_pediatric_patients_covid", "0"))
        flu_admit = to_int(it.get("total_patients_hospitalized_confirmed_influenza", "0")) \
            or to_int(it.get("num_hospitals_admissions_all_flu_confirmed", "0"))
        flu_icu = to_int(it.get("icu_patients_confirmed_influenza", "0")) \
            or to_int(it.get("num_hospitals_icu_patients_confirmed_influenza", "0"))
        rsv_admit = to_int(it.get("total_rsv_admissions", "0"))
        rows.append({
            "week_end": week,
            "state": state,
            "covid_adult": covid_adult,
            "covid_pedi": covid_pedi,
            "flu_admit": flu_admit,
            "flu_icu": flu_icu,
            "rsv_admit": rsv_admit,
        })
    # Keep most recent 12 weeks * up to 56 jurisdictions = cap at 700 rows
    rows.sort(key=lambda r: (r["week_end"], r["state"]), reverse=True)
    rows = rows[:700]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["week_end", "state", "covid_adult", "covid_pedi",
                        "flu_admit", "flu_icu", "rsv_admit"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    total_flu = sum(r["flu_admit"] for r in rows
                    if r["week_end"] == latest.get("week_end"))
    print(f"cdc_hospital: {len(rows)} rows | week "
          f"{latest.get('week_end','?')} | US flu admits={total_flu} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
