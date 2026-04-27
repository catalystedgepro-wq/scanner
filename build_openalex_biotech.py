#!/usr/bin/env python3
"""build_openalex_biotech.py — OpenAlex biotech publication velocity.

Recent research velocity across high-signal biotech concepts. First-
mover bias: breakthrough papers in CRISPR, oncology, mRNA, gene
therapy, and ADC often precede Phase-1/Phase-2 announcements and
licensing deals for:
- Large pharma (PFE, MRK, BMY, ABBV, GILD, LLY)
- Mid-cap biotech (VRTX, REGN, MRNA, BNTX, SGEN, ILMN)
- CRISPR cohort (CRSP, EDIT, NTLA, BEAM, VERV)
- Oncology (EXEL, PDCE, JAZZ, IDYA, RVMD)

Signal: publication count per concept (30-day window) + mean citation
density flags where the research frontier is accelerating. Novel
compounds named in titles feed deal-radar sentiment.

Source: api.openalex.org/works (free, no key).
Output: openalex_biotech.csv
Columns: concept, work_count, avg_citations, top_title, top_date,
         top_citations, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "openalex_biotech.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.openalex.org/works"

CONCEPTS = {
    "drug_discovery": "C74187038",
    "crispr": "C54355233",
    "oncology": "C143998085",
    "immunotherapy": "C2778375690",
    "mrna_vaccine": "C2780801425",
    "gene_therapy": "C2780381497",
    "neurodegeneration": "C2779134260",
    "cardiology": "C164705383",
    "antibody_drug_conj": "C2779134260",
    "clinical_trial": "C535046485",
}

TAG_RE = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    return TAG_RE.sub("", s or "").strip()


def _fetch(concept_id: str, since: str) -> list:
    qs = urllib.parse.urlencode({
        "per-page": "25",
        "filter": f"from_publication_date:{since},concepts.id:{concept_id}",
        "select": "id,title,publication_date,cited_by_count",
        "sort": "cited_by_count:desc",
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
        return data.get("results") or []
    except Exception as e:
        print(f"openalex_biotech {concept_id}: {e}")
        return []


def main() -> None:
    since = (dt.date.today() - dt.timedelta(days=30)).isoformat()

    rows: list[dict] = []
    for label, cid in CONCEPTS.items():
        works = _fetch(cid, since)
        if not works:
            continue
        cites = [int(w.get("cited_by_count") or 0) for w in works]
        avg = sum(cites) / len(cites) if cites else 0
        top = works[0]
        rows.append({
            "concept": label,
            "work_count": str(len(works)),
            "avg_citations": f"{avg:.1f}",
            "top_title": _strip(top.get("title") or "")[:180],
            "top_date": str(top.get("publication_date") or "")[:10],
            "top_citations": str(top.get("cited_by_count") or 0),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"openalex_biotech: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: -int(r["work_count"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["concept", "work_count", "avg_citations", "top_title",
                  "top_date", "top_citations", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total_works = sum(int(r["work_count"]) for r in rows)
    hot = max(rows, key=lambda r: int(r["work_count"]))
    print(f"openalex_biotech: {len(rows)} concepts | {total_works} papers "
          f"30d | hottest: {hot['concept']}={hot['work_count']} (avg "
          f"{hot['avg_citations']} cites) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
