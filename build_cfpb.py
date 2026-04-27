#!/usr/bin/env python3
"""
build_cfpb.py — Consumer Financial Protection Bureau (CFPB) tape.

Source: Federal Register API filtered on
  conditions[agencies][]=consumer-financial-protection-bureau

CFPB Federal Register publications capture every final rule, proposed
rule, consent order, CID, UDAAP enforcement, CARD Act threshold, Reg Z
adjustment, and market-monitoring release. Direct equity catalyst flow
for consumer-finance lenders, credit cards, and BNPL.

Direct equity catalysts:
- UDAAP enforcement → firm-specific consent orders (WFC $3.7B, BAC
  $250M historical).
- Open banking / 1033 rule → PLAID/PYPL/FIS/FISV data-portability.
- Credit-card rewards / late-fee cap → COF/SYF/DFS/AXP/JPM card NIM.
- Buy-now-pay-later rule → AFRM/PYPL/SQ.
- Auto-lending disparate impact → ALLY/CACC.
- Medical-debt credit reporting → pharma + UNH/CVS/HCA exposure.
- Overdraft / NSF fee rule → JPM/BAC/USB/TFC retail banking.
- Junk-fee enforcement (coalition with FTC) → banks broadly.
- Cryptocurrency consumer-protection → COIN/HOOD/MSTR.

Output: cfpb.csv — filed_utc, kind, title, link, summary.

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
OUT = ROOT / "cfpb_rules.csv"


def _classify(title: str, abstract: str) -> str:
    t = (title + " " + (abstract or "")).lower()

    # Enforcement
    if "udaap" in t or "unfair, deceptive, or abusive" in t:
        return "udaap_enforcement"
    if "civil money penalty" in t or "consent order" in t:
        return "consent_order"
    if "civil investigative demand" in t or " cid " in t.replace(",", " "):
        return "cid_investigation"

    # Major rules
    if "open banking" in t or "section 1033" in t or "1033 rule" in t:
        return "open_banking_1033"
    if "credit card" in t and ("late fee" in t or "rewards" in t):
        return "credit_card_fee_rule"
    if "buy-now-pay-later" in t or "buy now pay later" in t or "bnpl" in t:
        return "bnpl_rule"
    if "overdraft" in t or "nsf fee" in t or "non-sufficient funds" in t:
        return "overdraft_rule"
    if "junk fee" in t or "hidden fee" in t:
        return "junk_fee_rule"
    if "medical debt" in t:
        return "medical_debt_rule"
    if "small business lending" in t or "section 1071" in t:
        return "small_business_1071"
    if "auto" in t and ("lending" in t or "loan" in t):
        return "auto_lending"
    if "mortgage" in t or "truth in lending" in t or "reg z" in t:
        return "mortgage_reg_z"
    if "fair credit reporting" in t or "fcra " in t.replace(",", " "):
        return "fcra_credit_report"
    if "debt collection" in t or "reg f" in t:
        return "debt_collection"
    if "payday loan" in t or "installment loan" in t:
        return "payday_loan"
    if "credit score" in t or "data broker" in t:
        return "data_broker_score"

    # Crypto / digital assets
    if any(k in t for k in ("crypto", "stablecoin", "digital asset",
                             "virtual currency")):
        return "crypto_consumer"

    # Fair lending / disparate impact
    if "fair lending" in t or "disparate impact" in t or "redlining" in t:
        return "fair_lending"
    if "equal credit" in t or "ecoa" in t:
        return "ecoa_rule"

    # Leadership
    if any(k in t for k in ("director", "acting director", "sworn",
                             "nominat", "resign")):
        return "leadership_cfpb"

    # Market monitoring
    if "request for information" in t or "market monitor" in t:
        return "market_monitoring"

    # Threshold / adjustment
    if "adjustment" in t and ("threshold" in t or "dollar amount" in t):
        return "threshold_adjustment"

    if "final rule" in t:
        return "final_rule"
    if "proposed rule" in t:
        return "proposed_rule"

    return "cfpb_general"


def _fetch_window():
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    params = [
        ("conditions[agencies][]", "consumer-financial-protection-bureau"),
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
        print(f"[WARN] CFPB fetch failed: {exc}", file=sys.stderr)
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
    print(f"cfpb_rules: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
