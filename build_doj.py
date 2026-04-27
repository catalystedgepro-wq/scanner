#!/usr/bin/env python3
"""
build_doj.py — Department of Justice press & Antitrust Division tape.

Source: Federal Register API filtered on
  conditions[agencies][]=antitrust-division
  conditions[agencies][]=justice-department

DOJ's own RSS feeds were shuttered in their 2025 site redesign (every
`/feeds/*.xml` URL returns HTML). The Federal Register remains the
publication of record for all DOJ Antitrust Division decrees, Final
Judgments, Tunney Act comments, and consent decrees — which is where
the equity-moving news lives.

Direct equity catalysts:
- Antitrust enforcement / consent decree → target firm overhang cleared
  (GOOG Ad-Tech, MSFT-ATVI, JBLU-SAVE, UNH-AMED, KR-ACI historical).
- Merger challenge final judgment → binary deal outcome.
- FCPA / sanctions settlement → one-time cash hit + reputational drag
  (GSK, SIEGY, BAESY, WMT, UBER historical).
- False Claims Act / qui tam → healthcare margin (HCA, UNH, CVS).
- DPA/NPA corporate monitor appointments → multi-year cost drag.
- HSR early termination / clearance → M&A deal unlock.
- Civil Rights / ADA / Privacy settlement → social-media / ad-tech.
- Criminal charges against corporate actors → binary reputational.
- Drug-scheduling (DEA schedule changes) → pharma/cannabis.

Output: doj.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.federalregister.gov/api/v1/documents"
PER_PAGE = 100
LOOKBACK_DAYS = 45
TIMEOUT = 20
USER_AGENT = "CerebroCatalystEdge/1.0 (admin@catalystedgescanner.com)"

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "doj.csv"


def _classify(title: str, abstract: str) -> str:
    t = (title + " " + (abstract or "")).lower()

    # Antitrust first (most market-moving)
    if "tunney act" in t or "proposed final judgment" in t:
        return "antitrust_final_judgment"
    if "consent decree" in t and ("antitrust" in t or "sherman" in t or "clayton" in t):
        return "antitrust_consent"
    if "united states v" in t or "united states et al. v" in t:
        if any(k in t for k in ("merger", "acquisition", "acquire")):
            return "merger_enforcement"
        return "doj_litigation"
    if "antitrust" in t:
        return "antitrust_other"
    if "hart-scott-rodino" in t or "early termination" in t or "hsr " in t:
        return "hsr_clearance"

    # Fraud / foreign-corrupt / sanctions
    if "foreign corrupt practices" in t or "fcpa" in t:
        return "fcpa_settlement"
    if "false claims" in t or "qui tam" in t:
        return "false_claims_act"
    if "deferred prosecution" in t or "dpa" in t:
        return "dpa_nap"
    if "sanctions" in t and ("ofac" in t or "specially designated" in t):
        return "sanctions_designation"
    if "forfeiture" in t and ("millions" in t or "billions" in t or "$" in t):
        return "asset_forfeiture"

    # Drug / controlled substance scheduling
    if "controlled substances" in t and "schedul" in t:
        return "drug_scheduling"
    if "drug enforcement" in t or " dea " in t.replace(",", " "):
        return "dea_enforcement"

    # Healthcare fraud
    if "healthcare fraud" in t or "medicare fraud" in t or "medicaid fraud" in t:
        return "healthcare_fraud"

    # Bank / financial crime
    if "bank fraud" in t or "money laundering" in t or "securities fraud" in t:
        return "financial_fraud"

    # Civil rights / privacy / ADA / Title III
    if any(k in t for k in ("civil rights", "americans with disabilities",
                             "title iii", "fair housing", "voting rights")):
        return "civil_rights"
    if "privacy" in t or "surveillance" in t:
        return "privacy_enforcement"

    # Immigration / border
    if "immigration" in t or "deportation" in t:
        return "immigration_enforcement"

    # Corporate crime
    if "corporate" in t and any(k in t for k in ("charge", "indict", "guilty")):
        return "corporate_crime"

    # Leadership
    if any(k in t for k in ("attorney general", "associate attorney", "deputy attorney",
                             "assistant attorney", "confirmed", "sworn in", "resign")):
        return "leadership_doj"

    # Rule-making
    if "final rule" in t:
        return "final_rule"
    if "proposed rule" in t or "notice of proposed" in t:
        return "proposed_rule"

    return "doj_general"


def _fetch_window():
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    params = [
        ("conditions[agencies][]", "antitrust-division"),
        ("conditions[agencies][]", "justice-department"),
        ("conditions[publication_date][gte]", gte),
        ("per_page", str(PER_PAGE)),
        ("order", "newest"),
    ]
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"[WARN] DOJ fetch failed: {exc}", file=sys.stderr)
        return {}


def _to_utc(pub_date: str) -> str:
    if not pub_date:
        return ""
    try:
        d = dt.date.fromisoformat(pub_date)
        return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return pub_date


def _summary(abstract: str | None, excerpts: str | None, cap: int = 400) -> str:
    text = abstract or excerpts or ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0] + "..."
    return text


def main() -> int:
    data = _fetch_window()
    results = data.get("results", []) if isinstance(data, dict) else []

    rows = []
    kinds: dict[str, int] = {}
    for r in results:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        kind = _classify(title, r.get("abstract") or "")
        rows.append({
            "filed_utc": _to_utc(r.get("publication_date", "")),
            "kind": kind,
            "title": title,
            "link": r.get("html_url", "") or r.get("pdf_url", ""),
            "summary": _summary(r.get("abstract"), r.get("excerpts")),
        })
        kinds[kind] = kinds.get(kind, 0) + 1

    rows.sort(key=lambda x: x["filed_utc"], reverse=True)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filed_utc", "kind", "title", "link", "summary"])
        w.writeheader()
        w.writerows(rows)

    dist = ", ".join(f"{k}={v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:8])
    print(f"doj: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
