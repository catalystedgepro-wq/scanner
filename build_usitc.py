#!/usr/bin/env python3
"""
build_usitc.py — U.S. International Trade Commission (USITC) judicial trade tape.

Source: Federal Register API
  https://www.federalregister.gov/api/v1/documents?conditions[agencies][]=international-trade-commission

USITC is the **quasi-judicial agency** that adjudicates Section 337 IP
exclusion orders, Section 201 global safeguard petitions, AD/CVD (antidumping
& countervailing duty) investigations under Title VII, and Section 332
factfinding. Where USTR negotiates policy, USITC **rules** on specific cases —
a final affirmative AD determination moves the tariff rate the day Treasury
publishes it in the Federal Register.

Direct equity catalysts:
- AD/CVD on Chinese steel, aluminum, chemicals, solar cells, batteries,
  lithium salts → NUE/STLD/CLF/X/AA/CENX/ALB/LAC domestic primes bullish,
  JKS/CSIQ/PKX/MT Chinese/Korean producers bearish.
- Section 337 exclusion orders on semiconductors, pharma, consumer tech →
  complaint targets face import bans, complainants (AAPL/QCOM/MRVL/TSM
  historically) lock in durable IP moat.
- Sunset reviews (5-year) → revocation is a bearish shock to domestic producers.
- Critical-mineral petitions (lithium, graphite, rare earth, cobalt) →
  MP/ALB/LAC/SQM + FCX/TECK/ERRI.
- Textile/apparel ADs → HBI/GIL/PVH domestic floor.
- Chemical ADs (melamine, tris, formaldehyde, saccharin) →
  DOW/LYB/EMN/OLN/CE specialty flow.

Distinct from build_ustr.py (negotiation layer) — USITC is the **judicial**
arm that turns trade policy into enforceable duty rates.

Output: usitc.csv — filed_utc, kind, title, link, summary.

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
LOOKBACK_DAYS = 60
TIMEOUT = 20
USER_AGENT = "CerebroCatalystEdge/1.0 (admin@catalystedgescanner.com)"

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "usitc.csv"


def _classify(title: str, abstract: str) -> str:
    """Priority-ordered kind classifier for USITC Federal Register docs."""
    t = (title + " " + (abstract or "")).lower()

    # Section 337 IP exclusion — highest narrow-signal priority
    if "section 337" in t or "certain " in title.lower() and "investigation" in t:
        return "section_337_ip"

    # AD/CVD with China-specific routing (biggest single equity driver)
    china = any(k in t for k in (
        "from china", "from the people's republic of china", "from the prc",
        "from taiwan", "from hong kong",
    ))
    is_ad = "antidumping" in t or "dumping" in t
    is_cvd = "countervailing" in t
    if is_ad and china:
        return "ad_china"
    if is_cvd and china:
        return "cvd_china"
    if is_ad:
        return "ad_other"
    if is_cvd:
        return "cvd_other"

    # Section 201 global safeguard
    if "section 201" in t or "safeguard" in t:
        return "section_201_safeguard"

    # Section 332 factfinding
    if "section 332" in t:
        return "section_332_factfinding"

    # Sunset / 5-year review
    if "sunset review" in t or "five-year review" in t or "5-year review" in t:
        return "sunset_review"

    # Scope ruling / changed circumstances
    if "scope ruling" in t or "scope inquiry" in t:
        return "scope_ruling"
    if "changed circumstances" in t:
        return "changed_circumstances"

    # Determination outcomes
    if "final affirmative" in t or "affirmative determination" in t:
        return "determination_affirmative"
    if "final negative" in t or "negative determination" in t:
        return "determination_negative"

    # Public-interest pre-ruling
    if "public interest" in t and "comment" in t:
        return "public_interest_comment"

    # Preliminary / initiation
    if "preliminary" in t and ("determination" in t or "investigation" in t):
        return "preliminary_investigation"
    if "notice of institution" in t or "institution of investigation" in t:
        return "investigation_initiation"

    # Critical mineral petitions flagged for tracking
    minerals = ("lithium", "graphite", "cobalt", "nickel", "rare earth",
                "tungsten", "vanadium", "molybdenum", "magnesium", "gallium",
                "germanium", "polysilicon")
    if any(m in t for m in minerals):
        return "critical_mineral"

    # Steel / aluminum
    if "steel" in t or "aluminum" in t or "aluminium" in t:
        return "steel_aluminum"

    # Chemicals
    if any(k in t for k in ("chemical", "acid", "melamine", "tris ",
                             "saccharin", "formaldehyde")):
        return "chemical"

    return "itc_general"


def _fetch_window():
    """Fetch USITC docs over LOOKBACK_DAYS window via Federal Register API."""
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()

    params = {
        "conditions[agencies][]": "international-trade-commission",
        "conditions[publication_date][gte]": gte,
        "per_page": str(PER_PAGE),
        "order": "newest",
    }
    url = BASE + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"[WARN] USITC fetch failed: {exc}", file=sys.stderr)
        return {}


def _to_utc(pub_date: str) -> str:
    """Federal Register publication_date is YYYY-MM-DD (no tz). Anchor to 00:00Z."""
    if not pub_date:
        return ""
    try:
        d = dt.date.fromisoformat(pub_date)
        return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return pub_date


def _summary(abstract: str | None, excerpts: str | None, cap: int = 400) -> str:
    """Prefer abstract, fall back to excerpts, strip whitespace, cap length."""
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
    print(f"usitc: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
