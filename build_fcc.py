#!/usr/bin/env python3
"""
build_fcc.py — Federal Communications Commission (FCC) tape.

Source: Federal Register API filtered on
  conditions[agencies][]=federal-communications-commission

FCC regulates interstate wireless, broadcast, satellite, cable, and
broadband. Every FCC order — spectrum auction, license transfer,
net-neutrality action, merger review, tower siting, 5G/6G rulemaking,
UHF incentive auction — moves telecom, media, and satellite equities.

Direct equity catalysts:
- Spectrum auction outcome → T/VZ/TMUS/DISH winning bidder impact.
- License transfer approval → M&A deal unlock (T-DTV historical).
- Net-neutrality / broadband classification → CMCSA/CHTR/VZ.
- Satellite licensing → VSAT/IRDM/MAXR + SPCE/RKLB/ASTR launch.
- Robocall / TRACED Act enforcement → VZ/T/CMCSA/CHTR carrier.
- Open RAN / 5G fund → CRWD/ANET/CSCO/JNPR + ERIC/NOK.
- FirstNet / public safety → T/VZ/LHX/LDOS.
- Rural Digital Opportunity Fund (RDOF) auction → TDS/LUMN/WIN.
- Huawei / ZTE / national-security blacklist → SWKS/QRVO/QCOM supply
  chain.
- Media ownership cap → Sinclair/Gray/TEGNA/NXST/CMCSA.
- Section 230 rulemaking → META/GOOG/AMZN/TWTR.

Output: fcc.csv — filed_utc, kind, title, link, summary.

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
OUT = ROOT / "fcc.csv"


def _classify(title: str, abstract: str) -> str:
    t = (title + " " + (abstract or "")).lower()

    if "spectrum" in t and ("auction" in t or "license" in t):
        return "spectrum_auction"
    if "open ran" in t or "5g fund" in t or "o-ran" in t:
        return "open_ran_5g"
    if "robocall" in t or "traced act" in t or "stir/shaken" in t:
        return "robocall_enforcement"
    if "net neutrality" in t or "title ii" in t and "broadband" in t:
        return "net_neutrality"
    if "broadband" in t and ("classif" in t or "infrastructure" in t):
        return "broadband_policy"
    if "satellite" in t and ("license" in t or "authorization" in t):
        return "satellite_license"
    if "earth station" in t or "mobile satellite" in t:
        return "satellite_other"
    if "tower" in t and ("siting" in t or "registration" in t):
        return "tower_siting"
    if "emergency alert" in t or "eas " in t.replace(",", " "):
        return "emergency_alert"
    if "media ownership" in t or "ownership cap" in t or "multiple ownership" in t:
        return "media_ownership"
    if "license transfer" in t or "assignment of license" in t:
        return "license_transfer"
    if "merger" in t and any(k in t for k in ("cellular", "wireless", "cable", "satellite", "broadcast")):
        return "merger_review"
    if "huawei" in t or "zte" in t or "covered equipment" in t:
        return "huawei_zte_security"
    if "section 230" in t:
        return "section_230"
    if "public safety" in t or "firstnet" in t or "9-1-1" in t or "next generation 911" in t:
        return "public_safety"
    if "rural digital" in t or " rdof " in t.replace(",", " "):
        return "rural_digital_rdof"
    if "universal service" in t or " usf " in t.replace(",", " "):
        return "universal_service"
    if "do-not-call" in t or "telemarketing" in t:
        return "telemarketing_fcc"
    if "tcpa" in t or "telephone consumer protection" in t:
        return "tcpa_rule"
    if "broadcasting" in t or "broadcast station" in t:
        return "broadcasting_rule"
    if "cable" in t and "rate" in t:
        return "cable_rate"
    if any(k in t for k in ("chairman", "commissioner", "nominat", "sworn", "acting")):
        return "leadership_fcc"
    if "final rule" in t:
        return "final_rule"
    if "proposed rule" in t:
        return "proposed_rule"
    return "fcc_general"


def _fetch_window():
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    params = [
        ("conditions[agencies][]", "federal-communications-commission"),
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
        print(f"[WARN] FCC fetch failed: {exc}", file=sys.stderr)
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
    print(f"fcc: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
