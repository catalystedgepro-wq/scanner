#!/usr/bin/env python3
"""build_epa_echo.py — EPA ECHO Clean Air Act violation facilities.

High Priority Violator (HPV) facilities under CAA across
trading-sensitive SIC sectors. ECHO = Enforcement and Compliance
History Online. An HPV is a facility that EPA has identified as
having violations that warrant formal enforcement — typical path
from HPV flag → Notice of Violation → Consent Decree settlement
is 12-36 months. Settlement quantum for large-cap refiners/chem
producers typically $20M–$500M (injunctive + civil penalty +
supplemental environmental project).

SIC buckets tracked:
- 2911 petroleum refining → XOM, CVX, VLO, MPC, PSX, SUN, DK, PBF, HFC
- 2819 industrial inorganics → LIN, APD, ALB
- 2812 alkalies/chlorine → WLK, OLN, CC, DOW
- 2821 plastics materials → LYB, WLK, DOW, EMN
- 2834 pharma preps → PFE, JNJ, MRK, LLY, BMY, GILD
- 3312 steel mills → NUE, STLD, X, CLF
- 3711 motor vehicles → F, GM, STLA, TSLA
- 3331 primary copper → FCX, SCCO
- 4911 electric utilities → NEE, DUK, SO, AEP, EXC, PCG, EIX, D

Signal for trading:
- Operator with ≥3 HPV flags in 12 months = heightened
  enforcement risk (fade ticker 1-3% on next 8-K disclosure).
- Single major-asset HPV at a refinery with quarter-reported
  downtime = earnings-negative surprise window.
- Utility HPVs typically get passed to ratepayers so equity
  impact muted unless >$100M settlement.

Source: echodata.epa.gov/echo/air_rest_services (no key).
  Step 1: get_facilities (returns QID).
  Step 2: get_qid for actual rows (2-call pattern).

Output: epa_echo.csv
Columns: sic, facility, state, operator_clue, hpv_status,
         months_hpv, quarters_violation, last_viol_date,
         classification, sector_ticker_hint, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "epa_echo.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://echodata.epa.gov/echo/air_rest_services"

SIC_BUCKETS = {
    "2911": "refining:XOM,CVX,VLO,MPC,PSX,SUN,DK,PBF,HFC",
    "2819": "chem_inorg:LIN,APD,ALB",
    "2812": "chlorine:WLK,OLN,CC,DOW",
    "2821": "plastics:LYB,WLK,DOW,EMN",
    "2834": "pharma:PFE,JNJ,MRK,LLY,BMY,GILD",
    "3312": "steel:NUE,STLD,X,CLF",
    "3711": "autos:F,GM,STLA,TSLA",
    "3331": "copper:FCX,SCCO",
    "4911": "utility:NEE,DUK,SO,AEP,EXC,PCG,EIX,D",
}


def _fetch_qid(sic: str) -> str:
    url = (f"{BASE}.get_facilities?output=JSON&p_hpv=Y&p_act=Y"
           f"&p_sic={sic}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"epa_echo sic={sic}: {e}")
        return ""
    try:
        d = json.loads(raw)
    except Exception:
        return ""
    return d.get("Results", {}).get("QueryID", "") or ""


def _fetch_qid_rows(qid: str, qrows: int = 50) -> list[dict]:
    url = (f"{BASE}.get_qid?output=JSON&qid={qid}&qrows={qrows}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"epa_echo qid={qid}: {e}")
        return []
    try:
        d = json.loads(raw)
    except Exception:
        return []
    return d.get("Results", {}).get("Facilities", []) or []


def main() -> None:
    rows: list[dict] = []
    for sic, hint in SIC_BUCKETS.items():
        qid = _fetch_qid(sic)
        if not qid:
            continue
        facs = _fetch_qid_rows(qid, 200)
        for f in facs:
            hpv = f.get("AIRHpvStatus") or ""
            months_hpv_s = f.get("AIRMnthsWithHpv") or "0"
            try:
                months_hpv = int(months_hpv_s)
            except Exception:
                months_hpv = 0
            classif = f.get("AIRClassification") or ""
            # Filter: only active enforcement concern —
            # Unaddressed status OR Major Emissions with ≥12mo HPV.
            is_unaddressed = "Unaddressed" in hpv
            is_major_long = (("Major Emissions" in classif)
                             and months_hpv >= 12)
            if not (is_unaddressed or is_major_long):
                continue
            name = (f.get("AIRName") or "")[:80]
            state = f.get("AIRState") or ""
            qtrs_viol = f.get("AIRQtrsWithViol") or ""
            last_viol = f.get("AIRLastViolDate") or ""
            rows.append({
                "sic": sic,
                "facility": name,
                "state": state,
                "hpv_status": hpv[:60],
                "months_hpv": str(months_hpv),
                "quarters_violation": qtrs_viol,
                "last_viol_date": last_viol,
                "classification": classif[:40],
                "sector_ticker_hint": hint,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"epa_echo: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Sort by HPV duration (longest first), then sic.
    def _sort(r):
        try:
            m = int(r["months_hpv"] or 0)
        except Exception:
            m = 0
        return (-m, r["sic"])

    rows.sort(key=_sort)
    # Cap to 200 most severe to keep output focused.
    rows = rows[:200]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["sic", "facility", "state", "hpv_status",
                  "months_hpv", "quarters_violation", "last_viol_date",
                  "classification", "sector_ticker_hint", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summarize by SIC.
    from collections import Counter
    counts = Counter(r["sic"] for r in rows)
    top = counts.most_common(3)
    top_s = " ".join(f"SIC{s}={n}" for s, n in top)
    print(f"epa_echo: {len(rows)} HPV facilities | {top_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
