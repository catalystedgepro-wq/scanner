#!/usr/bin/env python3
"""build_pubmed_biotech.py — PubMed publication momentum by drug-target class.

Tracks how many PubMed papers per drug class hit in the last 14d vs the
prior 14d. Rising publication velocity on a target class often precedes
institutional analyst upgrades and retail-awareness spikes in the
associated biotechs. Useful for weighting sympathy rotation when a
single catalyst (FDA approval, readout) pops.

Drug-class → trading-relevant ticker coupling:
- **GLP-1 receptor agonist** — LLY, NVO, VKTX, ALT, RVMD, PFE
- **CAR-T therapy** — GILD, LEGN, JNJ, BLUE, ARCT
- **ADC / antibody-drug conjugate** — PFE, GILD, IMGN, IGMS, ADCT
- **mRNA vaccine** — MRNA, BNTX, PFE, SNY, CVAC
- **KRAS inhibitor** — AMGN, MRTX, RVMD, BBIO
- **BTK inhibitor** — JNJ, ABBV, NUVL, BGNE, LOXO
- **PCSK9 inhibitor** — AMGN, REGN, NVS
- **IL-23 inhibitor** — JNJ, ABBV, NVS, MRK
- **FGFR inhibitor** — PFE, IFRX, INCY
- **Bispecific antibody** — REGN, JNJ, RGEN, AMGN
- **Gene therapy** — CRSP, EDIT, BEAM, VERV, NTLA, RGNX, BLUE
- **Amyloid beta** — LLY, BIIB, EISAI (TSE:4523)
- **Alzheimer disease** — LLY, BIIB, AXSM, ATAI
- **Obesity pharmacotherapy** — LLY, NVO, VKTX, AMGN, ALT
- **NASH / MASH** — MDGL, AKRO, VKTX, TERN, IMVT
- **Sickle cell disease** — CRSP, BLUE, PFE, VRTX, AGIO
- **Hemophilia gene therapy** — SRPT, RGNX, BMRN, TAK
- **Alzheimer tau** — LLY, BIIB, RXRX, ANAB
- **Psilocybin** — COMP, ATAI, MNMD, CYBN
- **Ketamine depression** — ATAI, MNMD
- **Long COVID** — PFE, MRK, GILD (remdesivir)

Rules-of-thumb:
- Pub-velocity ratio > 1.5× (14d vs 14d prior) → momentum accelerating;
  consider long biotech ETFs (XBI, IBB) overweight on that class.
- Negative swing > -0.5× → fading interest, rotation watch.

Source: eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi (free, no
key for small volume; 3 req/sec polite ceiling). Date-filtered with
publication-date range. Returns hit count instantly.

Output: pubmed_biotech_momentum.csv
Columns: drug_class, tickers, hits_last14d, hits_prev14d, velocity_x,
delta_pct, latest_pmids, captured_at
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
OUT_CSV = ROOT / "pubmed_biotech_momentum.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

CLASSES: list[tuple[str, str]] = [
    ("GLP-1 receptor agonist",    "LLY,NVO,VKTX,ALT,RVMD"),
    ("CAR-T therapy",             "GILD,LEGN,JNJ,BLUE"),
    ("antibody drug conjugate",   "PFE,GILD,IMGN,IGMS,ADCT"),
    ("mRNA vaccine",              "MRNA,BNTX,PFE,CVAC"),
    ("KRAS inhibitor",            "AMGN,MRTX,RVMD,BBIO"),
    ("BTK inhibitor",             "JNJ,ABBV,NUVL,BGNE"),
    ("PCSK9 inhibitor",           "AMGN,REGN,NVS"),
    ("IL-23 inhibitor",           "JNJ,ABBV,NVS,MRK"),
    ("FGFR inhibitor",            "PFE,INCY"),
    ("bispecific antibody",       "REGN,JNJ,AMGN,IMVT"),
    ("gene therapy",              "CRSP,EDIT,BEAM,VERV,NTLA,RGNX,BLUE,SRPT"),
    ("amyloid beta",              "LLY,BIIB"),
    ("obesity pharmacotherapy",   "LLY,NVO,VKTX,AMGN,ALT,RVMD"),
    ("nonalcoholic steatohepatitis", "MDGL,AKRO,VKTX,TERN"),
    ("sickle cell disease",       "CRSP,BLUE,PFE,VRTX,AGIO"),
    ("hemophilia gene therapy",   "SRPT,RGNX,BMRN"),
    ("Alzheimer tau",             "LLY,BIIB,ANAB"),
    ("psilocybin",                "COMP,ATAI,MNMD,CYBN"),
    ("long COVID",                "PFE,MRK,GILD"),
    ("CRISPR gene editing",       "CRSP,EDIT,BEAM,NTLA,VERV"),
]

LOOKBACK_DAYS = 14


def pubmed_count(term: str, mindate: str, maxdate: str,
                 sample_ids: bool = False) -> tuple[int, list[str]]:
    """Return (count, optional first-5 pmids) for a date-bounded query."""
    params = {
        "db": "pubmed",
        "term": term,
        "mindate": mindate,
        "maxdate": maxdate,
        "datetype": "pdat",
        "retmode": "json",
        "retmax": "5" if sample_ids else "0",
        "sort": "date",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"pubmed_biotech: {term!r} -> {e}")
        return 0, []
    res = body.get("esearchresult", {}) or {}
    cnt_s = res.get("count", "0")
    try:
        cnt = int(cnt_s)
    except (ValueError, TypeError):
        cnt = 0
    ids = res.get("idlist", []) if sample_ids else []
    return cnt, ids


def main() -> None:
    today = dt.date.today()
    cur_hi = today.strftime("%Y/%m/%d")
    cur_lo = (today - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y/%m/%d")
    prv_hi = (today - dt.timedelta(days=LOOKBACK_DAYS + 1)).strftime("%Y/%m/%d")
    prv_lo = (today - dt.timedelta(days=LOOKBACK_DAYS * 2)).strftime("%Y/%m/%d")

    rows: list[dict] = []
    for drug_class, tickers in CLASSES:
        cur_n, pmids = pubmed_count(drug_class, cur_lo, cur_hi,
                                    sample_ids=True)
        time.sleep(0.35)
        prv_n, _ = pubmed_count(drug_class, prv_lo, prv_hi)
        time.sleep(0.35)

        if prv_n > 0:
            vel = cur_n / prv_n
            delta = (cur_n - prv_n) / prv_n * 100.0
        else:
            vel = float("inf") if cur_n > 0 else 0.0
            delta = float("inf") if cur_n > 0 else 0.0

        rows.append({
            "drug_class": drug_class,
            "tickers": tickers,
            "hits_last14d": cur_n,
            "hits_prev14d": prv_n,
            "velocity_x": f"{vel:.2f}" if vel != float("inf") else "inf",
            "delta_pct": f"{delta:+.1f}" if delta != float("inf") else "inf",
            "latest_pmids": ",".join(pmids[:5]),
        })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"pubmed_biotech: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Sort by velocity descending (hottest acceleration first).
    def _vel_num(r):
        try:
            return float(r["velocity_x"])
        except ValueError:
            return 999.0
    rows.sort(key=_vel_num, reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["drug_class", "tickers", "hits_last14d",
                  "hits_prev14d", "velocity_x", "delta_pct",
                  "latest_pmids", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    hot = rows[:3]
    hot_s = " | ".join(f"{r['drug_class']}={r['velocity_x']}x "
                       f"({r['hits_last14d']} vs {r['hits_prev14d']})"
                       for r in hot)
    print(f"pubmed_biotech: {len(rows)} classes | top accel: {hot_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
