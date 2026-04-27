#!/usr/bin/env python3
"""
build_ferc.py — Federal Energy Regulatory Commission (FERC) tape.

Source: Federal Register API filtered on
  conditions[agencies][]=federal-energy-regulatory-commission

FERC regulates interstate electricity, natural gas, oil pipeline, and
hydroelectric power. Every FERC order — pipeline certificate, LNG export
authorization, wholesale-rate change, reliability standard, transmission
incentive — moves energy-sector equities the day it hits the Federal
Register. FERC also has independent enforcement authority with
multi-billion-dollar civil penalty power under FPA §222 and NGA §21C.

Direct equity catalysts:
- LNG export authorization / FTA non-FTA finding → CQP/LNG/NEXTDECADE/VNOM.
- Pipeline certificate (NGA §7) → KMI/WMB/OKE/EPD/ET midstream.
- Hydro license / relicense → BEPC/PGC/Brookfield renewables.
- Transmission incentive / ROE case → NEE/DUK/SO/EXC/SRE utilities.
- Wholesale-rate rulemaking / capacity auction → CEG/VST/NRG/PCG.
- Enforcement action (market manipulation) → individual firm landmine
  (historical: JP Morgan $410M, Deutsche Bank $1.5M, Barclays $487M).
- Reliability standard (NERC CIP) → grid-security vendor tape (CRWD,
  DRGN, PANW, FTNT).
- Interconnection queue reform → IBDRY/NEP/CEG/PCG/AEP renewable tie-in.
- Order 2222 DER aggregation → ENPH/SEDG/TSLA/EVGO/CHPT.

Output: ferc.csv — filed_utc, kind, title, link, summary.

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
LOOKBACK_DAYS = 30
TIMEOUT = 20
USER_AGENT = "CerebroCatalystEdge/1.0 (admin@catalystedgescanner.com)"

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "ferc.csv"


def _classify(title: str, abstract: str) -> str:
    t = (title + " " + (abstract or "")).lower()

    # LNG export / import
    if "lng" in t or "liquefied natural gas" in t or "sabine" in t or "freeport" in t:
        if "export" in t or "authorization" in t:
            return "lng_export_auth"
        return "lng_other"
    if "pipeline" in t and ("certificate" in t or "section 7" in t or "nga" in t):
        return "pipeline_certificate"
    if "pipeline" in t and ("abandon" in t or "cessation" in t):
        return "pipeline_abandon"
    if "pipeline" in t:
        return "pipeline_other"

    # Hydro
    if "hydro" in t or "hydroelectric" in t:
        if "license" in t:
            return "hydro_license"
        return "hydro_other"

    # Electric transmission / interconnection
    if "transmission" in t and ("rate" in t or "roe" in t or "incentive" in t):
        return "transmission_rate"
    if "interconnection" in t:
        return "interconnection_queue"
    if "order 2222" in t or "distributed energy resource" in t or " der " in t.replace(",", " "):
        return "der_order_2222"

    # Wholesale markets / capacity
    if "capacity market" in t or "capacity auction" in t or "rpm " in t:
        return "capacity_market"
    if "wholesale" in t and "rate" in t:
        return "wholesale_rate"

    # Environmental assessment / NEPA
    if "environmental assessment" in t or " ea " in t.replace(",", " "):
        return "environmental_assessment"
    if "environmental impact" in t or " eis " in t.replace(",", " "):
        return "environmental_impact"

    # Reliability
    if any(k in t for k in ("reliability standard", "nerc", "cip", "critical infrastructure")):
        return "reliability_nerc"

    # Market manipulation / enforcement
    if "market manipulation" in t or "civil penalty" in t:
        return "enforcement_action"
    if "compliance" in t or "show cause" in t:
        return "compliance_order"

    # Leadership
    if any(k in t for k in ("chairman", "commissioner", "confirm", "sworn",
                             "resign", "retire")) and "ferc" in t:
        return "leadership_ferc"

    # Rule-making
    if "final rule" in t:
        return "final_rule"
    if "proposed rule" in t or "notice of proposed" in t:
        return "proposed_rule"

    # Off-the-record communications / procedural
    if "off-the-record" in t or "off the record" in t:
        return "off_record_comm"
    if "notice of application" in t:
        return "notice_application"

    # Off-shore wind
    if "offshore wind" in t or "outer continental shelf" in t:
        return "offshore_wind"

    return "ferc_general"


def _fetch_window():
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    params = [
        ("conditions[agencies][]", "federal-energy-regulatory-commission"),
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
        print(f"[WARN] FERC fetch failed: {exc}", file=sys.stderr)
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
    print(f"ferc: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
