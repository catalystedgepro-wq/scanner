#!/usr/bin/env python3
"""
build_osha.py — Occupational Safety and Health Administration (OSHA) tape.

Source: Federal Register API filtered on
  conditions[agencies][]=occupational-safety-and-health-administration

OSHA penalties, standards, emphasis programs, and post-accident citations
are predictive of industrial-firm liability and quarterly earnings drag.
Severe-injury reporting + NEPs (national emphasis programs) pre-cursor
multi-million-dollar OSHA penalties that get disclosed in 10-Qs.

Direct equity catalysts:
- Fatal accident citations / egregious willful → BA/LMT/GD/NOC/HII/TXT
  + HD/LOW/WMT warehouse + RKT/PKG packaging.
- NEP (national emphasis program) launch → industry-wide inspection
  surge → AMZN/UPS/FDX/WMT logistics, food processing TSN/PPC/HRL.
- Process Safety Management (PSM) rule → refiners MPC/VLO/PSX/HFC.
- Silica / combustible-dust / heat-stress rules → construction,
  agriculture, textiles.
- Respiratory / chemical standard → chem DOW/LYB/EMN/OLN.
- Whistleblower retaliation order → individual firm reputational.
- Walking-Working Surfaces enforcement → FedEx/UPS/CHRW warehouse tape.

Output: osha.csv — filed_utc, kind, title, link, summary.

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
LOOKBACK_DAYS = 90
TIMEOUT = 20
USER_AGENT = "CerebroCatalystEdge/1.0 (admin@catalystedgescanner.com)"

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "osha.csv"


def _classify(title: str, abstract: str) -> str:
    t = (title + " " + (abstract or "")).lower()

    if "process safety management" in t or "psm " in t.replace(",", " "):
        return "process_safety_mgmt"
    if "heat" in t and ("indoor" in t or "outdoor" in t or "illness" in t):
        return "heat_standard"
    if "silica" in t:
        return "silica_standard"
    if "combustible dust" in t:
        return "combustible_dust"
    if "respirat" in t:
        return "respiratory_standard"
    if "walking" in t and "working surface" in t:
        return "walking_working"
    if "crystalline silica" in t or "beryllium" in t or "hexavalent chromium" in t:
        return "toxic_substance"
    if "hazard communication" in t or "hazcom" in t:
        return "hazard_comm"
    if "lockout" in t or "tagout" in t:
        return "lockout_tagout"
    if "confined space" in t:
        return "confined_space"
    if "fall protection" in t:
        return "fall_protection"
    if "construction" in t and ("standard" in t or "rule" in t):
        return "construction_standard"

    # NEP / emphasis program
    if "national emphasis program" in t or " nep " in t.replace(",", " "):
        return "national_emphasis"
    if "local emphasis" in t or " lep " in t.replace(",", " "):
        return "local_emphasis"

    # Whistleblower / retaliation
    if "whistleblower" in t or "retaliation" in t:
        return "whistleblower_osha"

    # Citation / penalty / enforcement
    if "citation" in t or "penalty" in t:
        return "citation_penalty"
    if "willful" in t and "violation" in t:
        return "willful_violation"
    if "severe injury" in t or "fatality" in t or "fatal accident" in t:
        return "severe_injury"

    # Variance / exemption
    if "variance" in t:
        return "variance_permit"

    # Recordkeeping
    if "recordkeeping" in t or "injury and illness" in t:
        return "recordkeeping_rule"

    # Leadership
    if any(k in t for k in ("assistant secretary", "deputy assistant",
                             "nominat", "sworn", "confirm")) and "osha" in t:
        return "leadership_osha"

    if "final rule" in t:
        return "final_rule"
    if "proposed rule" in t:
        return "proposed_rule"

    return "osha_general"


def _fetch_window():
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    params = [
        ("conditions[agencies][]", "occupational-safety-and-health-administration"),
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
        print(f"[WARN] OSHA fetch failed: {exc}", file=sys.stderr)
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
    print(f"osha: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
